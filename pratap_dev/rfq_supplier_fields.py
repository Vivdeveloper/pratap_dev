import frappe


def set_supplier_fields(doc, method=None):
	"""Mirror the FIRST supplier's code and name from the Suppliers child table into
	header fields (custom_supplier_code / custom_supplier_name), so they can be shown as
	columns in the Request for Quotation list view.

	Only the first supplier row is used; if there are no suppliers, the fields stay blank.
	"""
	suppliers = doc.get("suppliers") or []
	first = suppliers[0] if suppliers else None

	if first and first.supplier:
		doc.custom_supplier_code = first.supplier
		doc.custom_supplier_name = first.supplier_name or frappe.db.get_value(
			"Supplier", first.supplier, "supplier_name"
		)
	else:
		doc.custom_supplier_code = None
		doc.custom_supplier_name = None

	# Server-side safety net for the Contact / Email auto-fill: if the client race (native
	# get_party_details clearing it) left a supplier row's Contact blank, fill it from the
	# supplier's PRIMARY contact on save. Fills nothing when no contact is marked primary.
	from pratap_dev.request_for_quotation import get_supplier_primary_contact

	for row in suppliers:
		if row.supplier and not row.contact:
			info = get_supplier_primary_contact(row.supplier)
			if info.get("contact"):
				row.contact = info["contact"]
				if info.get("email_id") and not row.email_id:
					row.email_id = info["email_id"]
