# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Add an optional file-attachment field to the Purchase Receipt (GRN), right below Trade Type.

Any file type, optional. The upload size cap (500 MB) is controlled by the site's
`max_file_size` setting, not the field. Idempotent."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Purchase Receipt": [
				{
					"fieldname": "custom_grn_attachment",
					"label": "Attachment",
					"fieldtype": "Attach",
					"insert_after": "custom_trade_type",
					"reqd": 0,
					"module": "pratap",
					"description": "Optional — attach any supporting file for this GRN.",
				}
			]
		},
		ignore_validate=True,
	)
	frappe.clear_cache(doctype="Purchase Receipt")
