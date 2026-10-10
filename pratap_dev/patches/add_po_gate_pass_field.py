# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Add a read-only 'Gate Pass' (No/Yes) field to the Purchase Order, below GRN Created.

Auto-set to Yes when at least one Gate Pass references this PO (Gate Pass.purchase_order_po_no),
else No. Not user-editable. Idempotent."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Purchase Order": [
				{
					"fieldname": "custom_gate_pass_available",
					"label": "Gate Pass",
					"fieldtype": "Select",
					"options": "No\nYes",
					"default": "No",
					"read_only": 1,
					"allow_on_submit": 1,
					"in_standard_filter": 1,
					"insert_after": "custom_grn_created",
					"module": "pratap",
				}
			]
		},
		ignore_validate=True,
	)
	frappe.clear_cache(doctype="Purchase Order")

	# Backfill existing POs so the flag is correct right away.
	frappe.db.sql(
		"""
		update `tabPurchase Order` po
		set po.custom_gate_pass_available = case
			when exists (
				select 1 from `tabGate Pass` gp
				where gp.purchase_order_po_no = po.name
			) then 'Yes' else 'No' end
		"""
	)
