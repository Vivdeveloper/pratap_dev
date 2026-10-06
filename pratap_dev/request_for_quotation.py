# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Helpers for the Request for Quotation form.

Auto-fetch a supplier's contact details for the RFQ Suppliers table. ERPNext's native
handler only fills the Contact when one is explicitly marked as the supplier's primary
(or billing) contact; when none is marked, the Contact/Email stay blank. This resolves
the primary contact and falls back to the first linked contact so the fields always fill.
"""

import frappe


@frappe.whitelist()
def get_supplier_primary_contact(supplier):
	"""Return {contact, email_id} for the supplier's primary contact, falling back to the
	first linked contact when none is marked primary. Empty dict if the supplier has none."""
	if not supplier:
		return {}

	from erpnext.accounts.party import get_default_contact

	# Prefer the primary/billing contact (same resolution ERPNext uses natively).
	contact = get_default_contact("Supplier", supplier)

	# Fall back to the first linked contact so the field never stays empty.
	if not contact:
		linked = frappe.get_all(
			"Contact",
			filters=[
				["Dynamic Link", "link_doctype", "=", "Supplier"],
				["Dynamic Link", "link_name", "=", supplier],
			],
			pluck="name",
			order_by="`tabContact`.creation asc",
			limit=1,
		)
		contact = linked[0] if linked else None

	if not contact:
		return {}

	email = frappe.db.get_value("Contact", contact, "email_id") or ""
	return {"contact": contact, "email_id": email}
