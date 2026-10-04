# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Add a permanent 'Filling Capacity' field to Stock Entry Detail (Stock Entry item row).

The value is fetched from the Item master (Item.custom_filling_capacity). The field
always exists on the row (and shows in the row's edit popup); JS on the Stock Entry form
shows it as a GRID COLUMN only when Stock Entry Type = 'Finished Goods Material Transfer'.
Idempotent."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Stock Entry Detail": [
				{
					"fieldname": "custom_filling_capacity",
					"label": "Filling Capacity",
					"fieldtype": "Float",
					"fetch_from": "item_code.custom_filling_capacity",
					"fetch_if_empty": 0,
					"read_only": 1,
					"in_list_view": 0,
					"insert_after": "item_code",
					"module": "pratap",
				}
			]
		},
		ignore_validate=True,
	)
	frappe.clear_cache(doctype="Stock Entry Detail")
