# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Helpers for the Request for Quotation form.

Auto-fetch a supplier's PRIMARY contact for the RFQ Suppliers table. We only autofill when
the supplier has a contact explicitly marked as primary (is_primary_contact = 1): if exactly
one is primary we use it, if more than one we use the first. When no contact is marked
primary we leave Contact/Email blank (no autofill) — the user picks manually.
"""

import frappe


@frappe.whitelist()
def get_default_contact(doctype, name):
	"""Whitelisted wrapper around frappe's (un-whitelisted) get_default_contact, wired via
	hooks.override_whitelisted_methods so the RFQ / Address-&-Contact render stops throwing
	'Method Not Allowed'. Pure read-only lookup."""
	from frappe.contacts.doctype.contact.contact import (
		get_default_contact as _get_default_contact,
	)

	return _get_default_contact(doctype, name)


@frappe.whitelist()
def get_supplier_primary_contact(supplier):
	"""Return {contact, email_id} for the supplier's PRIMARY contact only.

	We autofill only from a contact explicitly marked primary (is_primary_contact = 1).
	If more than one primary contact exists we take the first (by creation). If NO contact
	is marked primary we return an empty dict so the fields stay blank (no autofill)."""
	if not supplier:
		return {}

	# Only consider contacts of this supplier that are marked as primary.
	primary = frappe.get_all(
		"Contact",
		filters=[
			["Dynamic Link", "link_doctype", "=", "Supplier"],
			["Dynamic Link", "link_name", "=", supplier],
			["Contact", "is_primary_contact", "=", 1],
		],
		pluck="name",
		order_by="`tabContact`.creation asc",
		limit=1,
	)
	contact = primary[0] if primary else None

	if not contact:
		return {}

	email = frappe.db.get_value("Contact", contact, "email_id") or ""
	return {"contact": contact, "email_id": email}
