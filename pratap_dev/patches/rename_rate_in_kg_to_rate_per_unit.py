# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Rename the "Rate in KG" custom field to "Rate Per Unit" on Sales Order Item and
Sales Invoice Item, and show it in the Sales Invoice item grid. The field fieldname
(custom_rate_in_kg) is unchanged — only the label / list-view flag. Idempotent.

Fixture import skips already-existing Custom Fields, so property changes to an existing
field don't propagate that way; this patch applies them on every environment on migrate.
"""

import frappe


def execute():
	for dt in ("Sales Order Item", "Sales Invoice Item"):
		name = frappe.db.get_value("Custom Field", {"dt": dt, "fieldname": "custom_rate_in_kg"})
		if not name:
			continue
		cf = frappe.get_doc("Custom Field", name)
		changed = False
		if cf.label != "Rate Per Unit":
			cf.label = "Rate Per Unit"
			changed = True
		# Show the Rate Per Unit column in the Sales Invoice item grid (Sales Order already shows it).
		if dt == "Sales Invoice Item" and not cf.in_list_view:
			cf.in_list_view = 1
			changed = True
		# Tag with the app module so it ships in fixtures for fresh installs too.
		if (cf.module or "") != "pratap":
			cf.module = "pratap"
			changed = True
		if changed:
			cf.save(ignore_permissions=True)

	frappe.clear_cache(doctype="Sales Order Item")
	frappe.clear_cache(doctype="Sales Invoice Item")
