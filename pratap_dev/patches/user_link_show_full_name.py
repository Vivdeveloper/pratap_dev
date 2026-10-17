# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Show the User's full NAME (not the login email) in every User link field — in the
dropdown's selected value AND after selection — while search works on the name too.

The User doctype already has title_field = full_name and search_fields = full_name; this
just turns ON show_title_field_in_link (a doctype-level flag) so link controls render the
title (full name). Global by design — User is linked widely (Owner, Assigned To, Requested
by user, Tested By, …). Applied via a Property Setter so it is clean and reversible.
Idempotent."""

import frappe


def execute():
	# Make sure the title/search fields are set (should already be, but be safe).
	title = frappe.db.get_value("DocType", "User", "title_field")
	if title != "full_name":
		frappe.db.set_value("DocType", "User", "title_field", "full_name", update_modified=False)

	existing = frappe.db.get_value(
		"Property Setter",
		{"doc_type": "User", "property": "show_title_field_in_link", "doctype_or_field": "DocType"},
		"name",
	)
	if existing:
		frappe.db.set_value("Property Setter", existing, "value", "1")
	else:
		frappe.make_property_setter(
			{
				"doctype": "User",
				"doctype_or_field": "DocType",
				"property": "show_title_field_in_link",
				"value": "1",
				"property_type": "Check",
			}
		)
	frappe.clear_cache(doctype="User")
