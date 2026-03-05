# Copyright (c) 2026, saurabh@exacuer.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder.functions import Concat_ws, Date


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	"""Same structure as CRM Lead Details report, adapted for Prospect (Customer Management)."""
	columns = [
		{
			"label": _("Prospect"),
			"fieldname": "name",
			"fieldtype": "Link",
			"options": "Prospect",
			"width": 200,
		},
		{"label": _("Company Name"), "fieldname": "company_name", "fieldtype": "Data", "width": 200},
		{
			"fieldname": "prospect_owner",
			"label": _("Prospect Owner"),
			"fieldtype": "Link",
			"options": "User",
			"width": 200,
		},
		{
			"label": _("Territory"),
			"fieldname": "territory",
			"fieldtype": "Link",
			"options": "Territory",
			"width": 150,
		},
		{"label": _("Industry"), "fieldname": "industry", "fieldtype": "Link", "options": "Industry Type", "width": 100},
		{"label": _("Email"), "fieldname": "email_id", "fieldtype": "Data", "width": 120},
		{"label": _("Mobile"), "fieldname": "mobile_no", "fieldtype": "Data", "width": 120},
		{"label": _("Phone"), "fieldname": "phone", "fieldtype": "Data", "width": 120},
		{
			"label": _("Owner"),
			"fieldname": "owner",
			"fieldtype": "Link",
			"options": "User",
			"width": 120,
		},
		{
			"label": _("Company"),
			"fieldname": "company",
			"fieldtype": "Link",
			"options": "Company",
			"width": 200,
		},
		{"label": _("Address"), "fieldname": "address", "fieldtype": "Data", "width": 130},
		{"label": _("Postal Code"), "fieldname": "pincode", "fieldtype": "Data", "width": 90},
		{"label": _("City"), "fieldname": "city", "fieldtype": "Data", "width": 100},
		{"label": _("State"), "fieldname": "state", "fieldtype": "Data", "width": 100},
		{
			"label": _("Country"),
			"fieldname": "country",
			"fieldtype": "Link",
			"options": "Country",
			"width": 100,
		},
	]
	# Append custom Prospect columns (e.g. custom_customer_name, custom_email) if they exist
	for df in frappe.get_meta("Prospect").get("fields", []):
		if (df.get("fieldname") or "").startswith("custom_") and df.fieldtype in (
			"Data", "Link", "Select", "Small Text", "Read Only"
		):
			col = {"label": _(df.label or df.fieldname), "fieldname": df.fieldname, "fieldtype": df.fieldtype, "width": 100}
			if df.get("options"):
				col["options"] = df.options
			columns.append(col)
	return columns


def get_data(filters):
	prospect = frappe.qb.DocType("Prospect")
	address = frappe.qb.DocType("Address")
	dynamic_link = frappe.qb.DocType("Dynamic Link")

	select_fields = [
		prospect.name,
		prospect.company_name,
		prospect.prospect_owner,
		prospect.territory,
		prospect.industry,
		prospect.owner,
		prospect.company,
		(Concat_ws(", ", address.address_line1, address.address_line2)).as_("address"),
		address.pincode,
		address.city,
		address.state,
		address.country,
	]
	# Add custom Prospect fields to select if they exist
	for df in frappe.get_meta("Prospect").get("fields", []):
		if (df.get("fieldname") or "").startswith("custom_") and df.fieldtype in (
			"Data", "Link", "Select", "Small Text", "Read Only"
		):
			if hasattr(prospect, df.fieldname):
				select_fields.append(getattr(prospect, df.fieldname))

	query = (
		frappe.qb.from_(prospect)
		.left_join(dynamic_link)
		.on(
			(prospect.name == dynamic_link.link_name)
			& (dynamic_link.link_doctype == "Prospect")
			& (dynamic_link.parenttype == "Address")
		)
		.left_join(address)
		.on(address.name == dynamic_link.parent)
		.select(*select_fields)
		.where(prospect.company == filters.company)
		.where(Date(prospect.creation).between(filters.from_date, filters.to_date))
	)

	if filters.get("territory"):
		query = query.where(prospect.territory == filters.get("territory"))
	if filters.get("prospect_owner"):
		query = query.where(prospect.prospect_owner == filters.get("prospect_owner"))

	data = query.run(as_dict=1)
	_fill_contact_details(data)
	return data


def _fill_contact_details(data):
	"""Fill email_id, mobile_no, phone from Contact linked to each Prospect via Dynamic Link."""
	if not data:
		return
	prospect_names = [d.get("name") for d in data if d.get("name")]
	if not prospect_names:
		return

	dl = frappe.qb.DocType("Dynamic Link")
	contact = frappe.qb.DocType("Contact")

	try:
		results = (
			frappe.qb.from_(contact)
			.join(dl)
			.on(
				(contact.name == dl.parent)
				& (dl.parenttype == "Contact")
				& (dl.link_doctype == "Prospect")
				& (dl.link_name.isin(prospect_names))
			)
			.select(dl.link_name, contact.email_id, contact.mobile_no, contact.phone)
		).run(as_dict=1)

		contact_map = {}
		for r in results:
			if r.get("link_name") and r["link_name"] not in contact_map:
				contact_map[r["link_name"]] = {
					"email_id": r.get("email_id") or "",
					"mobile_no": r.get("mobile_no") or "",
					"phone": r.get("phone") or "",
				}
	except Exception:
		contact_map = {}

	for row in data:
		contact_row = contact_map.get(row.get("name")) or {}
		row["email_id"] = contact_row.get("email_id") or ""
		row["mobile_no"] = contact_row.get("mobile_no") or ""
		row["phone"] = contact_row.get("phone") or ""
