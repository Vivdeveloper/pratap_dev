# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Turn the dormant Material Request Item field ``custom_wip_rm_qty`` into the visible
"Source Warehouse" stock column (it was hidden and never computed). It now shows live stock
at the Material Transfer MR's Set Source Warehouse — see
material_request_stock.set_transfer_stock_columns. Idempotent."""

import frappe

DT = "Material Request Item"
FIELD = "custom_wip_rm_qty"


def execute():
	name = frappe.db.get_value("Custom Field", {"dt": DT, "fieldname": FIELD}, "name")
	if not name:
		return
	frappe.db.set_value(
		"Custom Field",
		name,
		{"label": "Source Warehouse", "hidden": 0},
		update_modified=False,
	)
	frappe.clear_cache(doctype=DT)
