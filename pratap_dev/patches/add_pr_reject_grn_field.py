# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Add a 'Reject GRN' checkbox to the Purchase Receipt, right above 'Apply Putaway Rule'.

When ticked, the whole receipt is treated as rejected: each item's Accepted Quantity is moved
to Rejected Quantity (Accepted = 0), and the Pratap Quality Inspection requirement is skipped on
submit (nothing is accepted into stock, so there is nothing to inspect). Idempotent.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Purchase Receipt": [
				{
					"fieldname": "custom_reject_grn",
					"label": "Reject GRN",
					"fieldtype": "Check",
					"default": "0",
					"insert_after": "company",
					"module": "pratap",
					"description": (
						"Reject the entire receipt: moves all Accepted Qty to Rejected Qty and lets "
						"the GRN be submitted without a Pratap Quality Inspection."
					),
				}
			]
		},
		ignore_validate=True,
	)
	frappe.clear_cache(doctype="Purchase Receipt")
