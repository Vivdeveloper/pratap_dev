# Copyright (c) 2026, pratap_dev contributors
# License: MIT

import frappe
from frappe import _
from frappe.utils import cint, cstr


def create_batch_before_grn_save(doc, method=None):
	"""Create Batch from custom_insert_batch_number before Purchase Receipt is saved."""
	if doc.doctype != "Purchase Receipt":
		return

	for row in doc.items:
		_set_batch_from_insert_batch_number(doc, row)


def _set_batch_from_insert_batch_number(purchase_receipt, row):
	batch_number = cstr(row.get("custom_insert_batch_number")).strip()
	if not batch_number:
		return

	if not row.item_code:
		frappe.throw(_("Row {0}: Item is required to create a batch.").format(row.idx))

	has_batch_no = frappe.db.get_value("Item", row.item_code, "has_batch_no")
	if not cint(has_batch_no):
		return

	row.batch_no = _get_or_create_grn_batch(batch_number, row.item_code, purchase_receipt)


def _get_or_create_grn_batch(batch_id, item_code, purchase_receipt, expiry_date=None):
	existing_item = frappe.db.get_value("Batch", batch_id, "item")

	if existing_item:
		if existing_item != item_code:
			frappe.throw(
				_(
					"Batch {0} already exists for Item {1}. It cannot be used for Item {2}."
				).format(batch_id, existing_item, item_code)
			)
		# Existing batch: still flow expiry + GRN details if they aren't set yet.
		_apply_grn_batch_details(batch_id, purchase_receipt, expiry_date)
		return batch_id

	batch = frappe.new_doc("Batch")
	batch.batch_id = batch_id
	batch.item = item_code
	if purchase_receipt.posting_date:
		batch.manufacturing_date = purchase_receipt.posting_date
	if expiry_date:
		batch.expiry_date = expiry_date
	# Flow GRN details onto the batch (supplier + GRN identifiers).
	_set_grn_batch_fields(batch, purchase_receipt)
	batch.insert(ignore_permissions=True)
	return batch.name


def _set_grn_batch_fields(batch, purchase_receipt):
	"""Populate the Batch's GRN-detail custom fields from the Purchase Receipt."""
	meta = batch.meta
	mapping = {
		"custom_supplier_id": purchase_receipt.get("supplier"),
		"custom_supplier_name": purchase_receipt.get("supplier_name"),
		"custom_grn_number": purchase_receipt.get("name"),
		"custom_grn_group_id": purchase_receipt.get("custom_grn_group_id"),
	}
	# standard Batch.supplier too, so it's consistent with ERPNext
	if meta.has_field("supplier") and purchase_receipt.get("supplier"):
		batch.supplier = purchase_receipt.get("supplier")
	for fieldname, value in mapping.items():
		if value and meta.has_field(fieldname):
			batch.set(fieldname, value)


def _apply_grn_batch_details(batch_id, purchase_receipt, expiry_date=None):
	"""For an existing batch, fill expiry + GRN detail fields only where still blank."""
	if not frappe.db.exists("Batch", batch_id):
		return
	meta = frappe.get_meta("Batch")
	values = {}
	if expiry_date and meta.has_field("expiry_date"):
		if not frappe.db.get_value("Batch", batch_id, "expiry_date"):
			values["expiry_date"] = expiry_date
	detail_map = {
		"custom_supplier_id": purchase_receipt.get("supplier"),
		"custom_supplier_name": purchase_receipt.get("supplier_name"),
		"custom_grn_number": purchase_receipt.get("name"),
		"custom_grn_group_id": purchase_receipt.get("custom_grn_group_id"),
	}
	for fieldname, value in detail_map.items():
		if value and meta.has_field(fieldname) and not frappe.db.get_value("Batch", batch_id, fieldname):
			values[fieldname] = value
	if values:
		frappe.db.set_value("Batch", batch_id, values, update_modified=False)
