# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Add a read-only "Stock Reservation Status" field to the Sales Order.

Auto-updated on submit by pratap_dev.sales_order_reservation. Idempotent."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Sales Order": [
				{
					"fieldname": "custom_stock_reservation_status",
					"label": "Stock Reservation Status",
					"fieldtype": "Select",
					"options": "Not Reserved\nPartially Reserved\nReserved",
					"default": "Not Reserved",
					"read_only": 1,
					"allow_on_submit": 1,
					"in_standard_filter": 1,
					"insert_after": "custom_order_confirmation_date",
					"module": "pratap",
				}
			]
		},
		ignore_validate=True,
	)
	frappe.clear_cache(doctype="Sales Order")
