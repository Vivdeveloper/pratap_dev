# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Add the 'Allow Access Order' override checkbox to the Sales Order, right below
Has Dispatch Intimation. When ticked it overrides the credit-limit save block and
ungates the Delivery Note button. See pratap_dev.sales_order_financials. Idempotent."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Sales Order": [
				{
					"fieldname": "custom_allow_access_order",
					"label": "Allow Access Order",
					"fieldtype": "Check",
					"default": "0",
					"allow_on_submit": 1,
					"insert_after": "custom_has_dispatch_intimation",
					"module": "pratap",
					"description": (
						"Override: allow saving / delivery even when this order plus the customer's "
						"current outstanding exceeds their credit limit."
					),
				}
			]
		},
		ignore_validate=True,
	)
	frappe.clear_cache(doctype="Sales Order")
