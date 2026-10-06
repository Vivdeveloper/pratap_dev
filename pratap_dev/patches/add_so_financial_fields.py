# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Add three read-only credit/payment fields to the Sales Order, below the Stock
Reservation Status field. Populated by pratap_dev.sales_order_financials. Idempotent."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Sales Order": [
				{
					"fieldname": "custom_credit_limit",
					"label": "Credit Limit",
					"fieldtype": "Currency",
					"read_only": 1,
					"allow_on_submit": 1,
					"insert_after": "custom_stock_reservation_status",
					"module": "pratap",
				},
				{
					"fieldname": "custom_current_outstanding",
					"label": "Current Outstanding (Unpaid Invoices)",
					"fieldtype": "Currency",
					"read_only": 1,
					"allow_on_submit": 1,
					"insert_after": "custom_credit_limit",
					"module": "pratap",
				},
				{
					"fieldname": "custom_payment_received_against_order",
					"label": "Payment Received Against Order",
					"fieldtype": "Currency",
					"read_only": 1,
					"allow_on_submit": 1,
					"insert_after": "custom_current_outstanding",
					"module": "pratap",
				},
			]
		},
		ignore_validate=True,
	)
	frappe.clear_cache(doctype="Sales Order")
