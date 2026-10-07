# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Add a hidden 'Required Date Overridden' flag to Material Request Item.

When the planner manually edits a row's Required By (schedule_date), this flag is set so the
lead-time / header auto-fill (client + server) stops recomputing that row's date — the entered
date becomes final. Rows that were never manually edited keep the automatic logic. Idempotent.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Material Request Item": [
				{
					"fieldname": "custom_required_date_overridden",
					"label": "Required Date Overridden",
					"fieldtype": "Check",
					"default": "0",
					"hidden": 1,
					"no_copy": 1,
					"print_hide": 1,
					"allow_on_submit": 1,
					"insert_after": "custom_lead_time_in_days",
					"module": "pratap",
				}
			]
		},
		ignore_validate=True,
	)
	frappe.clear_cache(doctype="Material Request Item")
