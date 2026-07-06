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
			no_of_unit = batch_qty / standard_pkg_qty

		accepted_unit = flt(row.get("accepted_unit"))
		if not accepted_unit and standard_pkg_qty:
			accepted_unit = accepted_qty / standard_pkg_qty

		rejected_unit = flt(row.get("rejected_unit"))
		if not rejected_unit and no_of_unit:
			rejected_unit = no_of_unit - accepted_unit

		rows.append(
			{
				"batch_no": row.get("batch_no"),
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


def update_grn_from_batch_qc(grn_doc, item_row, batch_rows, custom_density=None):
	"""Update GRN item qty and Serial and Batch Bundles from QC batch rows."""
	if not batch_rows:
		return

	total_accepted = sum(flt(row["accepted_qty"]) for row in batch_rows)
	total_rejected = sum(flt(row["rejected_qty"]) for row in batch_rows)
	total_received = total_accepted + total_rejected

	accepted_batches = {
		row["batch_no"]: flt(row["accepted_qty"])
		for row in batch_rows
		if flt(row["accepted_qty"]) > 0
	}
	rejected_batches = {
		row["batch_no"]: flt(row["rejected_qty"])
		for row in batch_rows
		if flt(row["rejected_qty"]) > 0
	}

	item_row.qty = total_accepted
	item_row.rejected_qty = total_rejected
	item_row.received_qty = total_received
	item_row.stock_qty = flt(total_accepted) * flt(item_row.conversion_factor or 1)

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
		total_accepted,
		is_rejected=False,
	)
	_update_item_bundle(
		grn_doc,
		item_row,
		rejected_batches,
		total_rejected,
		is_rejected=True,
	)

	_update_batch_density_from_qc(batch_rows, custom_density)


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
