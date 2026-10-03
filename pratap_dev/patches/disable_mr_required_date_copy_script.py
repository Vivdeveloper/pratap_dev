# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Disable the "Fetching Required date from prent to child table" Client Script on Material
Request. It blindly copied the header Required By onto every item; that behaviour is now
replaced by pratap_dev.material_request_stock.set_item_required_by_from_lead_time (per-item
Required By = Transaction Date + Lead Time in Days, else header Required By). Idempotent."""

import frappe

SCRIPT = "Fetching Required date from prent to child table"


def execute():
	if frappe.db.exists("Client Script", SCRIPT):
		frappe.db.set_value("Client Script", SCRIPT, "enabled", 0)
		frappe.clear_cache(doctype="Material Request")
