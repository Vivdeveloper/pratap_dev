# Copyright (c) 2026, pratap_dev contributors
# License: MIT

import json

import frappe
from frappe import _
from frappe.utils import flt

from erpnext.stock.serial_batch_bundle import SerialBatchCreation
from erpnext.stock.utils import get_combine_datetime


def parse_batch_qc_json(value):
	if not value:
		return []

	if isinstance(value, str):
		try:
			value = json.loads(value)
		except json.JSONDecodeError:
			return []

	if not isinstance(value, list):
		return []

	rows = []
	for row in value:
		if not row.get("batch_no"):
			continue

		batch_qty = flt(row.get("batch_qty"))
		accepted_qty = min(max(flt(row.get("accepted_qty")), 0), batch_qty)
		rejected_qty = batch_qty - accepted_qty
		standard_pkg_qty = flt(row.get("standard_pkg_qty")) or 1
		no_of_unit = flt(row.get("no_of_unit"))
		if not no_of_unit and standard_pkg_qty:
			no_of_unit = flt(batch_qty / standard_pkg_qty, 3)

		accepted_unit = flt(row.get("accepted_unit"))
		if not accepted_unit and standard_pkg_qty:
			accepted_unit = flt(accepted_qty / standard_pkg_qty, 3)

		rejected_unit = flt(row.get("rejected_unit"))
		if not rejected_unit and no_of_unit:
			rejected_unit = flt(no_of_unit - accepted_unit, 3)

		rows.append(
			{
				"batch_no": row.get("batch_no"),
				# owning GRN row: keeps the same batch on two GRN rows independent
				"purchase_receipt_item": row.get("purchase_receipt_item"),
				"batch_qty": batch_qty,
				"standard_pkg_qty": standard_pkg_qty,
				"no_of_unit": no_of_unit,
				"accepted_unit": accepted_unit,
				"rejected_unit": rejected_unit,
				"accepted_qty": accepted_qty,
				"rejected_qty": rejected_qty,
				# Per-batch density and the density-converted accepted/rejected qty.
				"density": flt(row.get("density")),
				"accepted_density_qty": flt(row.get("accepted_density_qty")),
				"rejected_density_qty": flt(row.get("rejected_density_qty")),
			}
		)

	return rows


def apply_density_to_batch_qc_rows(rows):
	"""Recompute accepted_density_qty / rejected_density_qty = qty / (per-batch) density.

	Falls back to the raw qty when a batch's density is 0 (nothing to convert by).
	"""
	for row in rows or []:
		density = flt(row.get("density"))
		if density:
			row["accepted_density_qty"] = flt(row.get("accepted_qty")) / density
			row["rejected_density_qty"] = flt(row.get("rejected_qty")) / density
		else:
			row["accepted_density_qty"] = flt(row.get("accepted_qty"))
			row["rejected_density_qty"] = flt(row.get("rejected_qty"))
	return rows


def _row_converted_qty(row, base_key, converted_key, fallback_density):
	"""Density-converted (stock UOM) qty for a batch row.

	Prefers the frozen *_density_qty value; otherwise divides the raw qty by the
	batch's own density (or the fallback), matching apply_density_to_batch_qc_rows.
	"""
	converted = flt(row.get(converted_key))
	if converted:
		return converted

	base = flt(row.get(base_key))
	density = flt(row.get("density")) or flt(fallback_density)
	return base / density if density > 0 else base


def update_grn_from_batch_qc(grn_doc, item_row, batch_rows, custom_density=None):
	"""Update GRN item qty and Serial and Batch Bundles from QC batch rows.

	Density converts purchase-UOM batch qtys into stock-UOM qtys. The GRN row keeps
	its accepted/rejected/received qty in purchase UOM and carries conversion_factor
	= 1 / density; stock_qty and both Serial and Batch Bundles (always stock UOM) use
	the density-converted qtys so ERPNext's bundle-vs-stock_qty check passes.
	"""
	if not batch_rows:
		return

	# Purchase-UOM totals (what the GRN row's qty / rejected_qty / received_qty hold).
	total_accepted = sum(flt(row["accepted_qty"]) for row in batch_rows)
	total_rejected = sum(flt(row["rejected_qty"]) for row in batch_rows)
	total_received = total_accepted + total_rejected

	# Stock-UOM totals (density-converted) for stock_qty and the bundles.
	total_accepted_stock = sum(
		_row_converted_qty(row, "accepted_qty", "accepted_density_qty", custom_density)
		for row in batch_rows
	)
	total_rejected_stock = sum(
		_row_converted_qty(row, "rejected_qty", "rejected_density_qty", custom_density)
		for row in batch_rows
	)

	# Serial and Batch Bundle entries are in stock UOM, so use the converted qtys.
	accepted_batches = {
		row["batch_no"]: _row_converted_qty(row, "accepted_qty", "accepted_density_qty", custom_density)
		for row in batch_rows
		if flt(row["accepted_qty"]) > 0
	}
	rejected_batches = {
		row["batch_no"]: _row_converted_qty(row, "rejected_qty", "rejected_density_qty", custom_density)
		for row in batch_rows
		if flt(row["rejected_qty"]) > 0
	}

	# Per-batch density means each batch converts by its own factor, so a single
	# item-level conversion_factor can't reproduce the summed bundle total (and for
	# NOS/NOS items ERPNext forces conversion_factor = 1 anyway). Instead the
	# density-converted qty *becomes* the received qty: qty == stock_qty == bundle
	# total, with conversion_factor = 1, so ERPNext's bundle-vs-stock_qty check passes.
	density = flt(custom_density)
	if density > 0:
		item_row.custom_density = density
	item_row.conversion_factor = 1

	item_row.qty = total_accepted_stock
	item_row.rejected_qty = total_rejected_stock
	item_row.received_qty = total_accepted_stock + total_rejected_stock
	item_row.stock_qty = total_accepted_stock

	if total_rejected > 0:
		rejected_warehouse = item_row.rejected_warehouse or grn_doc.rejected_warehouse
		if not rejected_warehouse:
			frappe.throw(
				_("Rejected Warehouse is required on GRN when rejected quantity is present.")
			)
		item_row.rejected_warehouse = rejected_warehouse

	_update_item_bundle(
		grn_doc,
		item_row,
		accepted_batches,
		total_accepted_stock,
		is_rejected=False,
	)
	_update_item_bundle(
		grn_doc,
		item_row,
		rejected_batches,
		total_rejected_stock,
		is_rejected=True,
	)

	_write_batch_packages_json(grn_doc, item_row, batch_rows)

	_update_batch_density_from_qc(batch_rows, custom_density)


def _write_batch_packages_json(grn_doc, item_row, batch_rows):
	"""Rebuild the GRN row's pack breakdown so the Batch Package Ledger reflects the
	QC accept/reject split.

	Batch entry originally stamps custom_batch_packages_json with the WHOLE receipt
	pointed at the accepted warehouse. Once QC splits accepted vs rejected, the Package
	Ledger (built on GRN submit) must show accepted units in the accepted warehouse and
	rejected units in the rejected warehouse — otherwise it double-counts everything as
	accepted. Each row now carries its own warehouse; the submit hook honours it.
	"""
	if not item_row.meta.has_field("custom_batch_packages_json"):
		return

	accepted_warehouse = item_row.warehouse
	rejected_warehouse = item_row.rejected_warehouse or grn_doc.rejected_warehouse

	package_rows = []
	for row in batch_rows:
		batch_no = (row.get("batch_no") or "").strip()
		if not batch_no:
			continue

		standard_pkg_qty = flt(row.get("standard_pkg_qty")) or 1

		accepted_unit = flt(row.get("accepted_unit"))
		accepted_qty = flt(row.get("accepted_qty"))
		if accepted_unit > 0 or accepted_qty > 0:
			package_rows.append(
				{
					"batch_no": batch_no,
					"warehouse": accepted_warehouse,
					"standard_pkg_qty": standard_pkg_qty,
					"no_of_unit": accepted_unit,
					"total_qty": accepted_qty or (standard_pkg_qty * accepted_unit),
				}
			)

		rejected_unit = flt(row.get("rejected_unit"))
		rejected_qty = flt(row.get("rejected_qty"))
		if rejected_unit > 0 or rejected_qty > 0:
			package_rows.append(
				{
					"batch_no": batch_no,
					"warehouse": rejected_warehouse,
					"standard_pkg_qty": standard_pkg_qty,
					"no_of_unit": rejected_unit,
					"total_qty": rejected_qty or (standard_pkg_qty * rejected_unit),
				}
			)

	item_row.custom_batch_packages_json = json.dumps(package_rows)


def _update_item_bundle(grn_doc, item_row, batch_map, total_qty, is_rejected=False):
	field = "rejected_serial_and_batch_bundle" if is_rejected else "serial_and_batch_bundle"
	bundle_name = item_row.get(field)

	if not batch_map or total_qty <= 0:
		if bundle_name:
			_cancel_linked_bundle(bundle_name)
			item_row.set(field, None)
		return

	warehouse = item_row.rejected_warehouse if is_rejected else item_row.warehouse
	if not warehouse:
		frappe.throw(_("Warehouse is required to update Serial and Batch Bundle."))

	incoming_rate = _get_incoming_rate(bundle_name, item_row)

	if bundle_name and frappe.db.exists("Serial and Batch Bundle", bundle_name):
		docstatus = frappe.db.get_value("Serial and Batch Bundle", bundle_name, "docstatus")
		if docstatus == 0:
			_rebuild_draft_bundle(
				bundle_name,
				batch_map,
				warehouse,
				incoming_rate,
				total_qty,
			)
			return

		_cancel_linked_bundle(bundle_name)

	bundle_doc = _create_bundle(
		grn_doc=grn_doc,
		item_row=item_row,
		batch_map=batch_map,
		total_qty=total_qty,
		warehouse=warehouse,
		is_rejected=is_rejected,
		incoming_rate=incoming_rate,
	)
	item_row.set(field, bundle_doc.name)


def _rebuild_draft_bundle(bundle_name, batch_map, warehouse, incoming_rate, total_qty):
	bundle = frappe.get_doc("Serial and Batch Bundle", bundle_name)
	bundle.set("entries", [])

	for batch_no, qty in batch_map.items():
		bundle.append(
			"entries",
			{
				"batch_no": batch_no,
				"qty": qty,
				"warehouse": warehouse,
				"incoming_rate": incoming_rate,
			},
		)

	bundle.warehouse = warehouse
	bundle.flags.ignore_voucher_validation = True
	bundle.save()

	if flt(bundle.total_qty) != flt(total_qty):
		frappe.db.set_value(
			"Serial and Batch Bundle",
			bundle.name,
			"total_qty",
			total_qty,
			update_modified=False,
		)


def _create_bundle(grn_doc, item_row, batch_map, total_qty, warehouse, is_rejected, incoming_rate):
	posting_datetime = get_combine_datetime(grn_doc.posting_date, grn_doc.posting_time)

	bundle_details = {
		"item_code": item_row.item_code,
		"posting_datetime": posting_datetime,
		"voucher_type": grn_doc.doctype,
		"voucher_no": grn_doc.name,
		"voucher_detail_no": item_row.name,
		"company": grn_doc.company,
		"is_rejected": 1 if is_rejected else 0,
		"type_of_transaction": "Inward",
		"warehouse": warehouse,
		"qty": total_qty,
		"actual_qty": total_qty,
		"batches": frappe._dict(batch_map),
		"do_not_submit": True,
	}

	if incoming_rate:
		bundle_details["batches_valuation"] = frappe._dict(
			{batch_no: incoming_rate for batch_no in batch_map}
		)

	bundle_doc = SerialBatchCreation(bundle_details).make_serial_and_batch_bundle()
	if not bundle_doc or not bundle_doc.get("name"):
		frappe.throw(_("Could not create Serial and Batch Bundle for {0}.").format(item_row.item_code))

	return bundle_doc


def _get_incoming_rate(bundle_name, item_row):
	if bundle_name and frappe.db.exists("Serial and Batch Bundle", bundle_name):
		rate = frappe.db.get_value(
			"Serial and Batch Entry",
			{"parent": bundle_name},
			"incoming_rate",
		)
		if rate:
			return flt(rate)

	return flt(item_row.rate)


def _cancel_draft_bundle(bundle_name):
	if not bundle_name or not frappe.db.exists("Serial and Batch Bundle", bundle_name):
		return

	if frappe.db.get_value("Serial and Batch Bundle", bundle_name, "docstatus") == 0:
		frappe.delete_doc("Serial and Batch Bundle", bundle_name, force=1, ignore_permissions=True)


def _cancel_linked_bundle(bundle_name):
	if not bundle_name or not frappe.db.exists("Serial and Batch Bundle", bundle_name):
		return

	bundle = frappe.get_doc("Serial and Batch Bundle", bundle_name)
	if bundle.docstatus == 1:
		bundle.flags.ignore_voucher_validation = True
		bundle.cancel()

	if bundle.docstatus == 0:
		frappe.delete_doc("Serial and Batch Bundle", bundle_name, force=1, ignore_permissions=True)


def _update_batch_density_from_qc(batch_rows, custom_density):
	"""Write each batch's density onto its Batch record (per-batch, else the fallback)."""
	for row in batch_rows:
		batch_no = row.get("batch_no")
		density = flt(row.get("density")) or flt(custom_density)
		if not batch_no or density <= 0 or not frappe.db.exists("Batch", batch_no):
			continue

		frappe.db.set_value(
			"Batch",
			batch_no,
			"custom_density",
			density,
			update_modified=False,
		)
