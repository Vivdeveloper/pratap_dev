# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Add a "Sales Person Brand Mapping" child table to the Customer, placed right below the
standard Sales Team table (Sales Team tab). Each row maps a Sales Person to a Brand they
sell for this customer. Idempotent."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Customer": [
				{
					"fieldname": "custom_sales_person_brand_mapping",
					"label": "Sales Person Brand Mapping",
					"fieldtype": "Table",
					"options": "Customer Sales Person Brand",
					"insert_after": "sales_team",
					"module": "pratap",
				}
			]
		},
		ignore_validate=True,
	)
	frappe.clear_cache(doctype="Customer")
