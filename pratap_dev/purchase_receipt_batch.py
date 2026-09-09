# Copyright (c) 2026, pratap_dev contributors
# License: MIT

import frappe
from frappe import _
from frappe.utils import cint, cstr, get_first_day, get_last_day, getdate, today


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


def _get_or_create_grn_batch(supplier_batch, item_code, purchase_receipt, expiry_date=None):
	"""Return the internal Batch for a GRN row, creating it with an auto nomenclature.

	`supplier_batch` is the value the user types (e.g. "ABC45") — the supplier's own
	batch reference. The Batch we create/return is named per the nomenclature:

	    <ITEM NAME>-<YY><MM>/<ITEM-GRN-SEQ-OF-MONTH>-<BATCH-COUNT-IN-GRN>

	Rules:
	  * Same supplier_batch within the SAME GRN (item) -> the SAME batch (dedup).
	  * A different supplier_batch in the GRN -> next batch-count (-1, -2, ...).
	  * A new GRN for the item in the month -> next item-GRN-seq (001, 002, ...).
	The typed value is stored on the batch as custom_supplier_batch.
	"""
	value = cstr(supplier_batch).strip()
	if not value:
		return None

	# 1) Already an existing Batch by this exact name (e.g. re-save with the
	#    nomenclature id, or a legacy/pre-existing batch): reuse it as-is.
	existing_item = frappe.db.get_value("Batch", value, "item")
	if existing_item:
		if existing_item != item_code:
			frappe.throw(
				_(
					"Batch {0} already exists for Item {1}. It cannot be used for Item {2}."
				).format(value, existing_item, item_code)
			)
		_apply_grn_batch_details(value, purchase_receipt, expiry_date)
		return value

	grn_name = purchase_receipt.get("name")

	# 2) Same supplier batch already mapped in THIS GRN (item) -> reuse that batch.
	if grn_name and frappe.get_meta("Batch").has_field("custom_supplier_batch"):
		mapped = frappe.db.get_value(
			"Batch",
			{
				"custom_grn_number": grn_name,
				"item": item_code,
				"custom_supplier_batch": value,
			},
			"name",
		)
		if mapped:
			_apply_grn_batch_details(mapped, purchase_receipt, expiry_date)
			return mapped

	# 3) New supplier batch -> create a Batch with the auto nomenclature.
	batch = frappe.new_doc("Batch")
	batch.batch_id = _generate_grn_batch_name(item_code, purchase_receipt)
	batch.item = item_code
	if frappe.get_meta("Batch").has_field("custom_supplier_batch"):
		batch.custom_supplier_batch = value
	if purchase_receipt.get("posting_date"):
		batch.manufacturing_date = purchase_receipt.get("posting_date")
	if expiry_date:
		batch.expiry_date = expiry_date
	_set_grn_batch_fields(batch, purchase_receipt)
	batch.insert(ignore_permissions=True)
	return batch.name


def _generate_grn_batch_name(item_code, purchase_receipt):
	"""Build the batch nomenclature:
	<ITEM CODE>-<YY><MM>/<ITEM-GRN-SEQ-OF-MONTH:03d>-<BATCH-COUNT-IN-GRN>.
	Falls back to a simple hash-free id only if the GRN has no name (shouldn't happen).
	"""
	posting = getdate(purchase_receipt.get("posting_date") or today())
	yymm = "%02d%02d" % (posting.year % 100, posting.month)
	grn_name = purchase_receipt.get("name")

	# ITEM-GRN-SEQ: rank of this GRN among all GRNs (draft+submitted) that received
	# this item in this calendar month, ordered by creation.
	grn_seq = 1
	if grn_name:
		month_start = get_first_day(posting)
		month_end = get_last_day(posting)
		rows = frappe.db.sql(
			"""
			SELECT pri.parent AS grn, MIN(pr.creation) AS created
			FROM `tabPurchase Receipt Item` pri
			INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
			WHERE pri.item_code = %(item)s AND pr.docstatus < 2
			  AND pr.posting_date BETWEEN %(start)s AND %(end)s
			GROUP BY pri.parent
			ORDER BY created ASC
			""",
			{"item": item_code, "start": month_start, "end": month_end},
			as_dict=True,
		)
		names = [r.grn for r in rows]
		grn_seq = (names.index(grn_name) + 1) if grn_name in names else (len(names) + 1)

	# BATCH-COUNT-IN-GRN: how manieth distinct batch for this (GRN, item).
	batch_count = 1
	if grn_name:
		existing = frappe.db.count(
			"Batch", {"custom_grn_number": grn_name, "item": item_code}
		)
		batch_count = existing + 1

	return "%s-%s/%03d-%d" % (item_code, yymm, grn_seq, batch_count)


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
