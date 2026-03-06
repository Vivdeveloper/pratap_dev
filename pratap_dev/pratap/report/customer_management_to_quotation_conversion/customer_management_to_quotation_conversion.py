# Copyright (c) 2026, saurabh@exacuer.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	"""Columns: Customer Management (Prospect) → Enquiry (Opportunity) → Quotation (converted or not), amount, rate."""
	cols = [
		# Customer Management (Prospect)
		{"label": _("Prospect Name"), "fieldname": "prospect_name", "fieldtype": "Link", "options": "Prospect", "width": 180},
		{"label": _("Company Name"), "fieldname": "company_name", "fieldtype": "Data", "width": 180},
		{"label": _("Customer Name"), "fieldname": "customer_name", "fieldtype": "Data", "width": 150},
		{"label": _("Territory"), "fieldname": "territory", "fieldtype": "Link", "options": "Territory", "width": 120},
		{"label": _("Assigned Sales Person"), "fieldname": "assigned_sales_person", "fieldtype": "Data", "width": 150},
		{"label": _("Contact Person"), "fieldname": "contact_person", "fieldtype": "Data", "width": 130},
		{"label": _("Email"), "fieldname": "email", "fieldtype": "Data", "width": 160},
		{"label": _("Mobile"), "fieldname": "mobile", "fieldtype": "Data", "width": 120},
		# Enquiry Opportunity
		{"label": _("Enquiry / Opportunity"), "fieldname": "opportunity", "fieldtype": "Link", "options": "Opportunity", "width": 150},
		{"label": _("Opportunity Status"), "fieldname": "opportunity_status", "fieldtype": "Data", "width": 120},
		{"label": _("Sales Stage"), "fieldname": "sales_stage", "fieldtype": "Data", "width": 120},
		{"label": _("Opportunity Amount"), "fieldname": "opportunity_amount", "fieldtype": "Currency", "options": "currency", "width": 120},
		{"fieldname": "currency", "hidden": 1},
		{"label": _("Expected Closing"), "fieldname": "expected_closing", "fieldtype": "Date", "width": 110},
		# Quotation conversion
		{"label": _("Converted to Quotation"), "fieldname": "converted_to_quotation", "fieldtype": "Data", "width": 140},
		{"label": _("Quotation ID"), "fieldname": "quotation_id", "fieldtype": "Link", "options": "Quotation", "width": 150},
		{"label": _("Quotation Date"), "fieldname": "quotation_date", "fieldtype": "Date", "width": 110},
		{"label": _("Quotation Amount"), "fieldname": "quotation_amount", "fieldtype": "Currency", "options": "currency", "width": 130},
		{"label": _("Quotation Rate"), "fieldname": "quotation_rate", "fieldtype": "Currency", "options": "currency", "width": 120},
	]
	return cols


def get_data(filters):
	"""
	Build rows: Prospect (Customer Management) → Opportunity (Enquiry) → Quotation.
	Shows whether each Enquiry was converted to Quotation and quotation amount + rate.
	"""
	company = filters.get("company")
	from_date = filters.get("from_date")
	to_date = filters.get("to_date")
	prospect_filter = filters.get("prospect")
	territory_filter = filters.get("territory")

	# 1) All Prospects (Customer Management) with optional filters
	prospect_filters = {}
	if company:
		prospect_filters["company"] = company
	if prospect_filter:
		prospect_filters["name"] = prospect_filter
	if territory_filter:
		prospect_filters["territory"] = territory_filter

	prospect_fields = ["name", "company_name", "territory", "prospect_owner"]
	prospect_meta = frappe.get_meta("Prospect")
	for f in ("custom_customer_name", "custom_assigned_sales_person", "custom_contact_person", "custom_email", "custom_mobile_no"):
		if prospect_meta.has_field(f):
			prospect_fields.append(f)

	prospects = frappe.get_all(
		"Prospect",
		filters=prospect_filters,
		fields=prospect_fields,
		order_by="modified desc",
	)
	if not prospects:
		return []

	prospect_names = [p["name"] for p in prospects]

	# 2) Prospect Opportunity child table: Prospect → Opportunity link
	po_list = frappe.get_all(
		"Prospect Opportunity",
		filters={"parent": ["in", prospect_names]},
		fields=["parent", "opportunity", "amount", "stage", "expected_closing", "currency"],
	)
	if not po_list:
		# No opportunities: still show prospects with empty opportunity columns
		return _build_rows_without_opportunities(prospects, filters)

	opp_names = list({r["opportunity"] for r in po_list if r.get("opportunity")})
	if not opp_names:
		return _build_rows_without_opportunities(prospects, filters)

	# 3) Opportunity details (Enquiry)
	opp_filters = {"name": ["in", opp_names]}
	if from_date and to_date:
		opp_filters["transaction_date"] = ["between", [from_date, to_date]]

	opp_list = frappe.get_all(
		"Opportunity",
		filters=opp_filters,
		fields=["name", "status", "sales_stage", "opportunity_amount", "total", "expected_closing", "currency", "transaction_date"],
	)
	opp_map = {o["name"]: o for o in opp_list}

	# 4) Quotations linked to these opportunities
	quotation_list = frappe.get_all(
		"Quotation",
		filters={"opportunity": ["in", opp_names], "docstatus": ["<", 2]},
		fields=["name", "opportunity", "transaction_date", "grand_total", "total", "net_total", "currency"],
	)
	quotation_by_opp = {q["opportunity"]: q for q in quotation_list}

	# 5) Quotation Item: get rate (e.g. first item rate or avg) per quotation
	quotation_names = [q["name"] for q in quotation_list]
	qt_item_rate = {}
	if quotation_names:
		items = frappe.get_all(
			"Quotation Item",
			filters={"parent": ["in", quotation_names]},
			fields=["parent", "rate", "qty", "amount"],
			order_by="parent, idx asc",
		)
		for it in items:
			if it["parent"] not in qt_item_rate:
				qt_item_rate[it["parent"]] = flt(it.get("rate"), 2)

	# 6) Build one row per Prospect-Opportunity
	rows = []
	for po in po_list:
		parent_prospect = po.get("parent")
		opp_name = po.get("opportunity")
		if not opp_name or opp_name not in opp_map:
			continue
		opp = opp_map[opp_name]
		prospect_doc = next((p for p in prospects if p["name"] == parent_prospect), None)
		if not prospect_doc:
			continue

		quo_doc = quotation_by_opp.get(opp_name)
		converted = _("Yes") if quo_doc else _("No")
		quotation_id = quo_doc.get("name") if quo_doc else None
		quotation_date = quo_doc.get("transaction_date") if quo_doc else None
		quotation_amount = flt(quo_doc.get("grand_total") or quo_doc.get("total"), 2) if quo_doc else None
		quotation_rate = qt_item_rate.get(quo_doc["name"]) if quo_doc else None
		currency = (quo_doc or po or {}).get("currency") or (frappe.get_cached_value("Company", company, "default_currency") if company else "INR")

		row = _prospect_row(prospect_doc, company)
		row.update({
			"opportunity": opp_name,
			"opportunity_status": opp.get("status"),
			"sales_stage": opp.get("sales_stage"),
			"opportunity_amount": flt(po.get("amount") or opp.get("opportunity_amount") or opp.get("total"), 2),
			"currency": currency,
			"expected_closing": po.get("expected_closing") or opp.get("expected_closing"),
			"converted_to_quotation": converted,
			"quotation_id": quotation_id,
			"quotation_date": quotation_date,
			"quotation_amount": quotation_amount,
			"quotation_rate": quotation_rate,
		})
		rows.append(row)

	return rows


def _prospect_row(prospect_doc, company):
	"""Build base row from Prospect (Customer Management); custom fields already in prospect_doc if present."""
	row = {
		"prospect_name": prospect_doc.get("name"),
		"company_name": prospect_doc.get("company_name"),
		"customer_name": prospect_doc.get("custom_customer_name"),
		"territory": prospect_doc.get("territory"),
		"assigned_sales_person": prospect_doc.get("custom_assigned_sales_person") or prospect_doc.get("prospect_owner"),
		"contact_person": prospect_doc.get("custom_contact_person"),
		"email": prospect_doc.get("custom_email"),
		"mobile": prospect_doc.get("custom_mobile_no"),
	}
	return row


def _build_rows_without_opportunities(prospects, filters):
	"""Prospects with no linked opportunities: show Customer Management columns only, rest empty."""
	company = filters.get("company")
	rows = []
	for p in prospects:
		row = _prospect_row(p, company)
		row.update({
			"opportunity": None,
			"opportunity_status": None,
			"sales_stage": None,
			"opportunity_amount": None,
			"currency": frappe.get_cached_value("Company", company, "default_currency") if company else "INR",
			"expected_closing": None,
			"converted_to_quotation": _("No"),
			"quotation_id": None,
			"quotation_date": None,
			"quotation_amount": None,
			"quotation_rate": None,
		})
		rows.append(row)
	return rows
