# Copyright (c) 2026, pratap_dev contributors
# License: MIT

import json

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt

from pratap_dev.purchase_receipt_batch import _get_or_create_grn_batch
from pratap_dev.purchase_receipt_batch_qc import _update_item_bundle


def _parse_batch_payload(batches):
	if isinstance(batches, str):
		batches = json.loads(batches)

	if not isinstance(batches, list):
		frappe.throw(_("Batch rows must be a list."))

	return batches


def _get_grn_item_row(grn_doc, purchase_receipt_item):
	for row in grn_doc.items:
		if row.name == purchase_receipt_item:
			return row
	return None


def _item_is_batch_tracked(item_code):
	return bool(cint(frappe.db.get_value("Item", item_code, "has_batch_no")))


def _normalize_batch_row(batch_row, default_pkg_qty):
	standard_pkg_qty = flt(batch_row.get("standard_pkg_qty")) or flt(default_pkg_qty) or 1
	no_of_unit = flt(batch_row.get("no_of_unit"))
	total_qty = flt(batch_row.get("total_qty")) or (standard_pkg_qty * no_of_unit)

	return {
		"batch_no": cstr(batch_row.get("batch_no")).strip(),
		"standard_pkg_qty": standard_pkg_qty,
		"no_of_unit": no_of_unit,
		"total_qty": total_qty,
	}


@frappe.whitelist()
def enable_item_batch_tracking(item_code):
	"""Enable batch tracking on item when user adds batches from GRN UI."""
	if not item_code or not frappe.db.exists("Item", item_code):
		frappe.throw(_("Item {0} does not exist.").format(item_code))

	frappe.db.set_value("Item", item_code, "has_batch_no", 1, update_modified=True)
	return {"item_code": item_code, "has_batch_no": 1}


@frappe.whitelist()
def get_item_batches(item_code, search_text=None, limit=50):
	"""Return batches for an item to populate batch selector in GRN UI."""
	if not item_code:
		return []

	filters = {"item": item_code}
	if search_text:
		filters["name"] = ["like", f"%{search_text}%"]

	return frappe.get_all(
		"Batch",
		filters=filters,
		fields=["name", "batch_id", "item"],
		order_by="creation desc",
		limit=cint(limit) or 50,
	)


@frappe.whitelist()
def create_grn_batch(batch_id, item_code, purchase_receipt=None):
	"""Create a batch for GRN item from the batch entry dialog."""
	batch_id = cstr(batch_id).strip()
	if not batch_id:
		frappe.throw(_("Batch No is required."))

	if not item_code or not frappe.db.exists("Item", item_code):
		frappe.throw(_("Item {0} does not exist.").format(item_code))

	if not _item_is_batch_tracked(item_code):
		enable_item_batch_tracking(item_code)

	grn = None
	if purchase_receipt and frappe.db.exists("Purchase Receipt", purchase_receipt):
		grn = frappe.get_doc("Purchase Receipt", purchase_receipt)

	purchase_receipt_doc = grn or frappe._dict(posting_date=frappe.utils.today())
	batch_no = _get_or_create_grn_batch(batch_id, item_code, purchase_receipt_doc)

	return {
		"batch_no": batch_no,
		"batch_id": batch_id,
		"item_code": item_code,
	}


@frappe.whitelist()
def get_grn_batch_entry_context(purchase_receipt, purchase_receipt_item=None):
	"""Return eligible GRN items and existing batch rows for the batch entry dialog."""
	if not purchase_receipt or not frappe.db.exists("Purchase Receipt", purchase_receipt):
		frappe.throw(_("Purchase Receipt {0} does not exist.").format(purchase_receipt))

	grn = frappe.get_doc("Purchase Receipt", purchase_receipt)
	eligible_items = []

	for row in grn.items:
		if not row.item_code or not _item_is_batch_tracked(row.item_code):
			continue

		eligible_items.append(
			{
				"name": row.name,
				"item_code": row.item_code,
				"item_name": row.item_name,
				"custom_packing_qty": flt(row.get("custom_packing_qty")) or 1,
				"custom_total_qty": flt(row.get("custom_total_qty")),
				"qty": flt(row.qty),
				"received_qty": flt(row.get("received_qty")),
				"uom": row.uom,
			}
		)

	selected_item = None
	if purchase_receipt_item:
		for grn_row in grn.items:
			if grn_row.name == purchase_receipt_item:
				selected_item = {
					"name": grn_row.name,
					"item_code": grn_row.item_code,
					"item_name": grn_row.item_name,
					"custom_packing_qty": flt(grn_row.get("custom_packing_qty")) or 1,
					"custom_total_qty": flt(grn_row.get("custom_total_qty")),
					"qty": flt(grn_row.qty),
					"received_qty": flt(grn_row.get("received_qty")),
					"uom": grn_row.uom,
					"has_batch_no": _item_is_batch_tracked(grn_row.item_code),
				}
				break
		if not selected_item:
			selected_item = next(
				(item for item in eligible_items if item["name"] == purchase_receipt_item),
				None,
			)
	elif len(eligible_items) == 1:
		selected_item = eligible_items[0]

	batch_rows = []
	item_batches = []
	if selected_item:
		from pratap_dev.pratap.doctype.pratap_quality_inspection.pratap_quality_inspection import (
			get_grn_batch_list,
		)

		item_batches = get_item_batches(selected_item["item_code"], limit=100)

		for batch in get_grn_batch_list(
			purchase_receipt,
			selected_item["item_code"],
			selected_item["name"],
		):
			batch_rows.append(
				{
					"batch_no": batch.get("batch_no"),
					"standard_pkg_qty": flt(batch.get("standard_pkg_qty"))
					or selected_item["custom_packing_qty"],
					"no_of_unit": flt(batch.get("no_of_unit")),
					"total_qty": flt(batch.get("batch_qty")),
				}
			)

	return {
		"eligible_items": eligible_items,
		"selected_item": selected_item,
		"batch_rows": batch_rows,
		"item_batches": item_batches,
	}


def _update_batch_packaging_fields(batch_no, standard_pkg_qty, batch_qty):
	"""Write Standard Pkg Qty and No of Unit (= batch qty / standard pkg qty) onto the Batch."""
	if not batch_no or not frappe.db.exists("Batch", batch_no):
		return

	meta = frappe.get_meta("Batch")
	values = {}
	pkg = flt(standard_pkg_qty)
	if meta.has_field("custom_standard_pkg_qty"):
		values["custom_standard_pkg_qty"] = pkg
	if meta.has_field("custom_no_of_unit"):
		values["custom_no_of_unit"] = (flt(batch_qty) / pkg) if pkg else 0

	if values:
		frappe.db.set_value("Batch", batch_no, values, update_modified=False)


@frappe.whitelist()
def add_batches_to_grn_item(purchase_receipt, purchase_receipt_item, batches):
	"""Create batches and Serial and Batch Bundle from custom batch entry rows."""
	batch_rows = _parse_batch_payload(batches)
	if not batch_rows:
		frappe.throw(_("Add at least one batch row."))

	if not purchase_receipt or not frappe.db.exists("Purchase Receipt", purchase_receipt):
		frappe.throw(_("Purchase Receipt {0} does not exist.").format(purchase_receipt))

	grn = frappe.get_doc("Purchase Receipt", purchase_receipt)
	if grn.docstatus != 0:
		frappe.throw(_("Purchase Receipt must be in draft to add batch numbers."))

	item_row = _get_grn_item_row(grn, purchase_receipt_item)
	if not item_row:
		frappe.throw(_("Purchase Receipt Item not found."))

	if not item_row.item_code:
		frappe.throw(_("Row {0}: Item Code is required.").format(item_row.idx))

	if not _item_is_batch_tracked(item_row.item_code):
		enable_item_batch_tracking(item_row.item_code)

	if not item_row.warehouse:
		frappe.throw(_("Row {0}: Accepted Warehouse is required.").format(item_row.idx))

	default_pkg_qty = flt(item_row.get("custom_packing_qty")) or 1
	expected_no_of_unit = flt(item_row.get("custom_total_qty"))
	if expected_no_of_unit <= 0:
		frappe.throw(_("Row {0}: Set No of Unit on the item row before adding batches.").format(item_row.idx))

	batch_map = {}
	batch_pkg_map = {}
	total_no_of_unit = 0
	standard_pkg_qty = default_pkg_qty

	for idx, raw_row in enumerate(batch_rows, start=1):
		row = _normalize_batch_row(raw_row, default_pkg_qty)
		if not row["batch_no"]:
			frappe.throw(_("Row {0}: Batch No is required.").format(idx))

		if row["no_of_unit"] <= 0:
			frappe.throw(_("Row {0}: No of Unit must be greater than 0.").format(idx))

		if row["total_qty"] <= 0:
			frappe.throw(_("Row {0}: Total Qty must be greater than 0.").format(idx))

		batch_no = _get_or_create_grn_batch(row["batch_no"], item_row.item_code, grn)
		batch_map[batch_no] = batch_map.get(batch_no, 0) + row["total_qty"]
		batch_pkg_map[batch_no] = row["standard_pkg_qty"]
		total_no_of_unit += row["no_of_unit"]
		standard_pkg_qty = row["standard_pkg_qty"]

	if abs(total_no_of_unit - expected_no_of_unit) > 0.0001:
		difference = abs(total_no_of_unit - expected_no_of_unit)
		frappe.throw(
			_(
				"Batch units mismatch: batch rows total {0} units, but this item row requires {1} units (difference: {2}). Adjust batch No of Unit values so both totals match."
			).format(total_no_of_unit, expected_no_of_unit, difference)
		)

	total_qty = sum(batch_map.values())
	_update_item_bundle(grn, item_row, batch_map, total_qty, is_rejected=False)

	# Save Standard Pkg Qty and No of Unit (= batch qty / standard pkg qty) on each Batch.
	for batch_no, batch_qty in batch_map.items():
		_update_batch_packaging_fields(
			batch_no, batch_pkg_map.get(batch_no) or standard_pkg_qty, batch_qty
		)

	item_row.qty = total_qty
	item_row.received_qty = total_qty
	item_row.stock_qty = total_qty * flt(item_row.conversion_factor or 1)
	item_row.custom_packing_qty = standard_pkg_qty
	item_row.use_serial_batch_fields = 0

	grn.save()

	return {
		"purchase_receipt_item": item_row.name,
		"item_code": item_row.item_code,
		"qty": item_row.qty,
		"received_qty": item_row.received_qty,
		"stock_qty": item_row.stock_qty,
		"custom_packing_qty": item_row.custom_packing_qty,
		"serial_and_batch_bundle": item_row.serial_and_batch_bundle,
	}
