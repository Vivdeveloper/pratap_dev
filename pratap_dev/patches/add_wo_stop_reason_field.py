# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Add a read-only 'Stop Reason' (Small Text) field to Work Order.

Captured in a mandatory dialog when the user Stops a Work Order, and shown on the form
so the reason is visible against the WO. allow_on_submit so it can be set after submit.
Idempotent."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Work Order": [
				{
					"fieldname": "custom_stop_reason",
					"label": "Stop Reason",
					"fieldtype": "Small Text",
					"read_only": 1,
					"allow_on_submit": 1,
					"insert_after": "status",
					"module": "pratap",
				}
			]
		},
		ignore_validate=True,
	)
	frappe.clear_cache(doctype="Work Order")
