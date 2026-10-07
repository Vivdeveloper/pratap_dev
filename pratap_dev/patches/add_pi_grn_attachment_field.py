# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Add the Attachment field to the Purchase Invoice (below Trade Type).

Mirrors the GRN (Purchase Receipt) attachment: it is carried over from the source GRN if one
was uploaded there, otherwise it must be uploaded on the invoice before submission
(enforced in pratap_dev.purchase_invoice). Idempotent."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Purchase Invoice": [
				{
					"fieldname": "custom_grn_attachment",
					"label": "Attachment",
					"fieldtype": "Attach",
					"insert_after": "custom_trade_type",
					"reqd": 0,
					"module": "pratap",
					"description": "Carried over from the GRN if attached there; otherwise required before submitting.",
				}
			]
		},
		ignore_validate=True,
	)
	frappe.clear_cache(doctype="Purchase Invoice")
