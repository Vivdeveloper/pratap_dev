# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Add a read-only 'Sample Qty' (Float) field to Purchase Receipt Item.

Captures the per-item sample quantity entered in the PO "Create GRN" dialog's batch
table. It is written programmatically when the GRN is created and also flows to the
linked Pratap Quality Inspection's "Sample Issued Qty for QC" (inspected_qty). Idempotent."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Purchase Receipt Item": [
				{
					"fieldname": "custom_sample_qty",
					"label": "Sample Qty",
					"fieldtype": "Float",
					"read_only": 1,
					"insert_after": "custom_total_qty",
					"module": "pratap",
				}
			]
		},
		ignore_validate=True,
	)
	frappe.clear_cache(doctype="Purchase Receipt Item")
