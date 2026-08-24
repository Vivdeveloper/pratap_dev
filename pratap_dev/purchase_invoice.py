# Copyright (c) 2026, pratap_dev contributors
# License: MIT

import frappe


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
