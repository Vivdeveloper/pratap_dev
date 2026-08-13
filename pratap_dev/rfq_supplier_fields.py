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
