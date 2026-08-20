# Copyright (c) 2026, pratap_dev contributors
# License: MIT
"""Batch Package Ledger — a warehouse-aware, package-level sub-ledger per Batch.

ERPNext's stock ledger tracks qty per (item, batch, warehouse) but has no concept
of package size / number of units. This layer records that packaging dimension on
the Batch itself (child table `custom_package_ledger`) and keeps it in step with the
two vouchers in scope:

  * Purchase Receipt (GRN)  -> inflow  (+ rows, entry_type "Receipt")
  * Stock Entry             -> movement (reduce source rows, add target rows)

Every change is keyed by (reference_doctype, reference_name) so cancel/amend can
remove-and-re-add cleanly and the ledger never silently drifts for these vouchers.
Real stock is always driven by ERPNext's standard Serial and Batch Bundle — this
layer is purely additive tracking, so it can't break stock or valuation.
"""

import json

import frappe
from frappe.utils import flt, getdate

LEDGER_FIELD = "custom_package_ledger"


# --------------------------------------------------------------------------- #
# Low-level ledger helpers
# --------------------------------------------------------------------------- #
def add_ledger_rows(batch_no, rows, entry_type, reference_doctype, reference_name, posting_date):
	"""Append package rows to a Batch's ledger. `rows` = list of dicts with
	standard_pkg_qty / no_of_unit / total_qty / warehouse."""
	if not batch_no or not frappe.db.exists("Batch", batch_no):
		return
	if not rows:
		return

	batch = frappe.get_doc("Batch", batch_no)
	for r in rows:
		pkg = flt(r.get("standard_pkg_qty"))
		units = flt(r.get("no_of_unit"))
		total = flt(r.get("total_qty")) or (pkg * units)
		# Outflow rows (Transfer Out / Consumed) carry negative amounts, so only
		# skip a genuinely empty row.
		if total == 0 and units == 0:
			continue
		batch.append(
			LEDGER_FIELD,
			{
				"warehouse": r.get("warehouse"),
				"standard_pkg_qty": pkg,
				"no_of_unit": units,
				"total_qty": total,
				"entry_type": entry_type,
				"posting_date": getdate(posting_date) if posting_date else None,
				"reference_doctype": reference_doctype,
				"reference_name": reference_name,
			},
		)
	batch.save(ignore_permissions=True)


def remove_ledger_rows_for_reference(reference_doctype, reference_name):
	"""Drop every ledger row created by a given voucher, across all batches."""
	if not reference_name:
		return

	parents = frappe.get_all(
		"Batch Package Ledger",
		filters={
			"parenttype": "Batch",
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
		},
		fields=["parent"],
		distinct=True,
	)
	for p in parents:
		batch = frappe.get_doc("Batch", p.parent)
		keep = [
			row
			for row in batch.get(LEDGER_FIELD)
			if not (
				row.reference_doctype == reference_doctype
				and row.reference_name == reference_name
			)
		]
		if len(keep) != len(batch.get(LEDGER_FIELD)):
			batch.set(LEDGER_FIELD, keep)
			batch.save(ignore_permissions=True)


def get_available_rows(batch_no, warehouse):
	"""Current package rows for a batch in a warehouse, as running balances.

	Collapses the ledger into net (pack_qty -> {units, total}) balances so callers
	(e.g. the Stock Entry dialog / FIFO reducer) see what is actually available.
	Transfer Out / Consumed rows carry negative amounts, so summing nets them out.
	"""
	rows = frappe.get_all(
		"Batch Package Ledger",
		filters={"parenttype": "Batch", "parent": batch_no, "warehouse": warehouse},
		fields=["standard_pkg_qty", "no_of_unit", "total_qty"],
		order_by="idx asc",
	)
	balances = {}
	for r in rows:
		pkg = flt(r.standard_pkg_qty)
		b = balances.setdefault(pkg, {"standard_pkg_qty": pkg, "no_of_unit": 0.0, "total_qty": 0.0})
		b["no_of_unit"] += flt(r.no_of_unit)
		b["total_qty"] += flt(r.total_qty)
	# only positive balances, largest pack first
	return [b for b in sorted(balances.values(), key=lambda x: -x["standard_pkg_qty"]) if b["total_qty"] > 0.0001]


# --------------------------------------------------------------------------- #
# Purchase Receipt (GRN) — inflow
# --------------------------------------------------------------------------- #
def purchase_receipt_on_submit(doc, method=None):
	"""Add Receipt rows to each received batch from the pack breakdown captured
	by the custom GRN batch-entry dialog."""
	for item in doc.items:
		raw = item.get("custom_batch_packages_json")
		if not raw:
			continue
		try:
			package_rows = json.loads(raw)
		except (ValueError, TypeError):
			continue
		if not isinstance(package_rows, list):
			continue

		by_batch = {}
		for pr in package_rows:
			batch_no = (pr.get("batch_no") or "").strip()
			if not batch_no:
				continue
			by_batch.setdefault(batch_no, []).append(
				{
					"warehouse": item.warehouse,
					"standard_pkg_qty": flt(pr.get("standard_pkg_qty")),
					"no_of_unit": flt(pr.get("no_of_unit")),
					"total_qty": flt(pr.get("total_qty")),
				}
			)

		for batch_no, rows in by_batch.items():
			add_ledger_rows(
				batch_no,
				rows,
				entry_type="Receipt",
				reference_doctype="Purchase Receipt",
				reference_name=doc.name,
				posting_date=doc.posting_date,
			)


def purchase_receipt_on_cancel(doc, method=None):
	remove_ledger_rows_for_reference("Purchase Receipt", doc.name)


# --------------------------------------------------------------------------- #
# Stock Entry — movement (reduce source rows, add target rows)
# --------------------------------------------------------------------------- #
@frappe.whitelist()
def get_batch_package_options(batch_no, warehouse):
	"""Available pack balances of a batch in a warehouse (for the SE dialog)."""
	if not batch_no or not warehouse:
		return []
	return get_available_rows(batch_no, warehouse)


@frappe.whitelist()
def get_item_package_options(item_code, warehouse):
	"""Every (batch, pack size) with a positive package balance for `item_code` in
	`warehouse`, in FIFO order (oldest batch first) — like the standard batch
	selector, but at pack-size granularity. Used to auto-fill the SE dialog.
	"""
	if not item_code or not warehouse:
		return []

	# FIFO: oldest manufacturing date first, then creation.
	batches = frappe.get_all(
		"Batch",
		filters={"item": item_code, "disabled": 0},
		fields=["name"],
		order_by="manufacturing_date asc, creation asc",
	)

	options = []
	for b in batches:
		for bal in get_available_rows(b.name, warehouse):
			options.append(
				{
					"batch_no": b.name,
					"standard_pkg_qty": bal["standard_pkg_qty"],
					"no_of_unit": bal["no_of_unit"],
					"total_qty": bal["total_qty"],
				}
			)
	return options


def stock_entry_on_submit(doc, method=None):
	"""Post ledger movement from each item's pack allocation:
	  - reduce the source warehouse (Transfer Out, or Consumed if no target)
	  - add the target warehouse (Transfer In)  -> the "new row" on move to WIP
	"""
	for item in doc.items:
		raw = item.get("custom_batch_packages_json")
		if not raw:
			continue
		try:
			alloc = json.loads(raw)
		except (ValueError, TypeError):
			continue
		if not isinstance(alloc, list) or not alloc:
			continue

		s_wh = item.get("s_warehouse")
		t_wh = item.get("t_warehouse")
		out_type = "Transfer Out" if t_wh else "Consumed"

		out_by_batch = {}
		in_by_batch = {}
		for a in alloc:
			batch_no = (a.get("batch_no") or "").strip()
			if not batch_no:
				continue
			pkg = flt(a.get("standard_pkg_qty"))
			units = flt(a.get("no_of_unit"))
			total = flt(a.get("total_qty")) or (pkg * units)
			if total == 0 and units == 0:
				continue
			if s_wh:
				out_by_batch.setdefault(batch_no, []).append(
					{"warehouse": s_wh, "standard_pkg_qty": pkg, "no_of_unit": -units, "total_qty": -total}
				)
			if t_wh:
				in_by_batch.setdefault(batch_no, []).append(
					{"warehouse": t_wh, "standard_pkg_qty": pkg, "no_of_unit": units, "total_qty": total}
				)

		for batch_no, rows in out_by_batch.items():
			add_ledger_rows(batch_no, rows, out_type, "Stock Entry", doc.name, doc.posting_date)
		for batch_no, rows in in_by_batch.items():
			add_ledger_rows(batch_no, rows, "Transfer In", "Stock Entry", doc.name, doc.posting_date)


def stock_entry_on_cancel(doc, method=None):
	remove_ledger_rows_for_reference("Stock Entry", doc.name)


@frappe.whitelist()
def apply_stock_entry_batches(stock_entry, se_item, allocation):
	"""Create OR update a Stock Entry row's Serial and Batch Bundle from the Batch
	Packages allocation, using ERPNext's own standard API, and set the row's qty +
	pack breakdown to match — all server-side (so the client just reloads).

	This lets the Batch Packages modal fully stand in for the standard "Add Batch
	Nos" dialog: the bundle is built exactly the way ERPNext does (via
	add_serial_batch_ledgers, which sets Outward/Inward and the sign automatically).

	`allocation` = list of pack rows [{batch_no, standard_pkg_qty, no_of_unit,
	total_qty}, ...].
	"""
	from erpnext.stock.doctype.serial_and_batch_bundle.serial_and_batch_bundle import (
		add_serial_batch_ledgers,
	)

	if isinstance(allocation, str):
		allocation = json.loads(allocation)
	if not allocation:
		frappe.throw(_("No batch allocation to apply."))

	se = frappe.get_doc("Stock Entry", stock_entry)
	se.check_permission("write")
	if se.docstatus != 0:
		frappe.throw(_("Stock Entry {0} is not a draft.").format(stock_entry))

	row = next((r for r in se.items if r.name == se_item), None)
	if not row:
		frappe.throw(_("Stock Entry row not found."))

	warehouse = row.get("s_warehouse") or row.get("t_warehouse")

	# Sum qty per batch for the bundle (batch-level); positive magnitudes —
	# add_serial_batch_ledgers applies the sign (Outward = negative for a source row).
	batch_qty_map = {}
	total_abs = 0.0
	for a in allocation:
		batch_no = (a.get("batch_no") or "").strip()
		qty = abs(flt(a.get("total_qty")) or flt(a.get("standard_pkg_qty")) * flt(a.get("no_of_unit")))
		if not batch_no or qty == 0:
			continue
		batch_qty_map[batch_no] = batch_qty_map.get(batch_no, 0.0) + qty
		total_abs += qty

	if not batch_qty_map:
		frappe.throw(_("No batch allocation to apply."))

	entries = [{"batch_no": bn, "qty": q, "warehouse": warehouse} for bn, q in batch_qty_map.items()]

	# Standard create-or-update. add_serial_batch_ledgers uses ATTRIBUTE access on
	# child_row (e.g. child_row.serial_and_batch_bundle), so these must be frappe._dict
	# (plain dicts raise AttributeError).
	child_row = frappe._dict(
		{
			"doctype": row.doctype,
			"name": row.name,
			"item_code": row.item_code,
			"warehouse": warehouse,
			"s_warehouse": row.get("s_warehouse"),
			"t_warehouse": row.get("t_warehouse"),
			"parenttype": "Stock Entry",
			"is_rejected": 0,
			"serial_and_batch_bundle": row.get("serial_and_batch_bundle"),
		}
	)
	parent_doc = frappe._dict(
		{
			"doctype": "Stock Entry",
			"name": se.name,
			"company": se.company,
			"posting_date": se.posting_date,
			"posting_time": se.posting_time,
		}
	)

	sb_doc = add_serial_batch_ledgers(entries, child_row, parent_doc, warehouse)

	# Set the row: bundle link, qty (= allocated total), pack breakdown, and clear
	# the manual-fields flag — mirroring what the standard dialog leaves behind.
	cf = flt(row.get("conversion_factor")) or 1
	frappe.db.set_value(
		row.doctype,
		row.name,
		{
			"serial_and_batch_bundle": sb_doc.name,
			"use_serial_batch_fields": 0,
			"qty": total_abs,
			"transfer_qty": total_abs * cf,
			"basic_amount": total_abs * flt(row.get("basic_rate")),
			"custom_batch_packages_json": json.dumps(allocation),
		},
		update_modified=False,
	)

	return {"bundle": sb_doc.name, "total_qty": total_abs}
