# Copyright (c) 2026, pratap_dev contributors
# License: MIT

import frappe
from frappe import _


def set_grn_group_id_from_receipt(doc, method=None):
	"""Show the linked GRN's GRN Group ID on the Purchase Invoice.

	PIs auto-created from the GRN grouping flow already carry custom_grn_group_id; for
	PIs built manually via "Get Items From -> Purchase Receipt", derive it from the
	source GRN of the items so the field is populated there too.
	"""
	if not doc.meta.has_field("custom_grn_group_id"):
		return
	if doc.get("custom_grn_group_id"):
		return

	receipts = [
		row.get("purchase_receipt")
		for row in (doc.get("items") or [])
		if row.get("purchase_receipt")
	]
	if not receipts:
		return

	group_id = frappe.db.get_value("Purchase Receipt", receipts[0], "custom_grn_group_id")
	if group_id:
		doc.custom_grn_group_id = group_id


def copy_grn_attachment_from_receipt(doc, method=None):
	"""Carry the GRN's Attachment onto the Purchase Invoice.

	If the invoice has no attachment yet, pull it from the source GRN (the first linked
	Purchase Receipt that has one). If the GRN had no attachment, the invoice field stays empty
	and must be filled before submission (see require_grn_attachment_on_submit)."""
	if not doc.meta.has_field("custom_grn_attachment"):
		return
	if doc.get("custom_grn_attachment"):
		return

	receipts = [
		row.get("purchase_receipt")
		for row in (doc.get("items") or [])
		if row.get("purchase_receipt")
	]
	# De-dupe while preserving order.
	seen = set()
	for pr in receipts:
		if pr in seen:
			continue
		seen.add(pr)
		attachment = frappe.db.get_value("Purchase Receipt", pr, "custom_grn_attachment")
		if attachment:
			doc.custom_grn_attachment = attachment
			break


def require_grn_attachment_on_submit(doc, method=None):
	"""An Attachment is mandatory on the Purchase Invoice before submission. If the GRN carried
	one it is auto-filled; otherwise the user must upload it here."""
	if doc.meta.has_field("custom_grn_attachment") and not doc.get("custom_grn_attachment"):
		frappe.throw(
			_("Please attach a file in the <b>Attachment</b> field before submitting this Purchase Invoice."),
			title=_("Attachment Required"),
		)
