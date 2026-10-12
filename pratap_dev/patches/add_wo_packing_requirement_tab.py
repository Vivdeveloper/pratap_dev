# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Add a 'Packing Requirement' tab (Tab Break + HTML) to Work Order.

Mirrors the Forecast Club "Packing Material Requirement" table for the WO's item to
manufacture. The table is rendered client-side into the HTML field. Idempotent."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Work Order": [
				{
					"fieldname": "custom_packing_requirement_tab",
					"label": "Packing Requirement",
					"fieldtype": "Tab Break",
					"insert_after": "custom_time_log_html",
					"module": "pratap",
				},
				{
					"fieldname": "custom_packing_requirement_html",
					"label": "Packing Material Requirement",
					"fieldtype": "HTML",
					"insert_after": "custom_packing_requirement_tab",
					"module": "pratap",
				},
			]
		},
		ignore_validate=True,
	)
	frappe.clear_cache(doctype="Work Order")
