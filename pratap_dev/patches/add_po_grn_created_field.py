# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Add a read-only 'GRN Created' (No/Yes) field to the Purchase Order, below Required By.

Auto-set to Yes when at least one submitted GRN (Purchase Receipt) exists against the PO,
else No. Not user-editable. Idempotent."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Purchase Order": [
				{
					"fieldname": "custom_grn_created",
					"label": "GRN Created",
					"fieldtype": "Select",
					"options": "No\nYes",
					"default": "No",
					"read_only": 1,
					"allow_on_submit": 1,
					"in_standard_filter": 1,
					"insert_after": "schedule_date",
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
		set po.custom_grn_created = case
			when exists (
				select 1 from `tabPurchase Receipt Item` pri
				where pri.purchase_order = po.name and pri.docstatus = 1
			) then 'Yes' else 'No' end
		"""
	)
