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


def _get_or_create_grn_batch(batch_id, item_code, purchase_receipt):
	existing_item = frappe.db.get_value("Batch", batch_id, "item")

	if existing_item:
		if existing_item != item_code:
			frappe.throw(
				_(
					"Batch {0} already exists for Item {1}. It cannot be used for Item {2}."
				).format(batch_id, existing_item, item_code)
			)
		return batch_id

	batch = frappe.new_doc("Batch")
	batch.batch_id = batch_id
	batch.item = item_code
	if purchase_receipt.posting_date:
		batch.manufacturing_date = purchase_receipt.posting_date
	batch.insert(ignore_permissions=True)
	return batch.name
