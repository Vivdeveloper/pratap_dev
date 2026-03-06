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
	"""CRM flow: Customer Management → Enquiry Opportunity → Sample Request → Product Trial → Quotation."""
	return [
		# ---- Customer Management (Prospect) ----
		{"label": _("Prospect / Customer Mgmt"), "fieldname": "prospect_name", "fieldtype": "Link", "options": "Prospect", "width": 200},
		{"label": _("Company Name"), "fieldname": "company_name", "fieldtype": "Data", "width": 150},
		{"label": _("Customer Name"), "fieldname": "customer_name_cm", "fieldtype": "Data", "width": 140},
		{"label": _("Territory"), "fieldname": "territory", "fieldtype": "Link", "options": "Territory", "width": 110},
		{"label": _("Assigned Sales Person"), "fieldname": "assigned_sales_person", "fieldtype": "Data", "width": 140},
		{"label": _("Contact"), "fieldname": "contact_person", "fieldtype": "Data", "width": 110},
		{"label": _("Email"), "fieldname": "email", "fieldtype": "Data", "width": 150},
		{"label": _("Mobile"), "fieldname": "mobile", "fieldtype": "Data", "width": 110},
		# ---- Enquiry Opportunity ----
		{"label": _("Enquiry / Opportunity"), "fieldname": "opportunity", "fieldtype": "Link", "options": "Opportunity", "width": 200},
		{"label": _("Opportunity Status"), "fieldname": "opportunity_status", "fieldtype": "Data", "width": 180},
		{"label": _("Sales Stage"), "fieldname": "sales_stage", "fieldtype": "Data", "width": 110},
		{"label": _("Opportunity Amount"), "fieldname": "opportunity_amount", "fieldtype": "Currency", "options": "currency", "width": 170},
		{"label": _("Opportunity Total"), "fieldname": "opportunity_total", "fieldtype": "Currency", "options": "currency", "width": 170},
		{"label": _("Expected Closing"), "fieldname": "expected_closing", "fieldtype": "Date", "width": 170},
		{"fieldname": "currency", "hidden": 1},
		# ---- Sample Request ----
		{"label": _("Sample Request"), "fieldname": "sample_request", "fieldtype": "Link", "options": "Sample Request", "width": 150},
		{"label": _("Sample Request Amount"), "fieldname": "sample_request_amount", "fieldtype": "Currency", "options": "currency", "width": 200},
		{"label": _("Sample Dispatch Date"), "fieldname": "sample_dispatch_date", "fieldtype": "Date", "width": 180},
		{"label": _("Sample Request Status"), "fieldname": "sample_request_status", "fieldtype": "Data", "width": 180},
		# ---- Product Trial ----
		{"label": _("Product Trial"), "fieldname": "product_trial", "fieldtype": "Link", "options": "Product Trial", "width": 200},
		{"label": _("Trial Status"), "fieldname": "trial_status", "fieldtype": "Data", "width": 100},
		{"label": _("Trial Quantity"), "fieldname": "trial_quantity", "fieldtype": "Float", "width": 150},
		# ---- Quotation ----
		{"label": _("Quotation"), "fieldname": "quotation", "fieldtype": "Link", "options": "Quotation", "width": 200},
		{"label": _("Quotation Amount"), "fieldname": "quotation_amount", "fieldtype": "Currency", "options": "currency", "width": 160},
		{"label": _("Quotation Rate"), "fieldname": "quotation_rate", "fieldtype": "Currency", "options": "currency", "width": 160},
		{"label": _("Quotation Date"), "fieldname": "quotation_date", "fieldtype": "Date", "width": 160},
		{"label": _("Customer Mgmt to Quotation Conversion"), "fieldname": "conversion_done", "fieldtype": "Data", "width": 200},
	]


def get_data(filters):
	"""
	Build rows for full flow: Prospect → Opportunity → Sample Request → Product Trial → Quotation.
	One row per Prospect–Opportunity; fill Sample Request, Product Trial, Quotation when present.
	"""
	company = filters.get("company")
	from_date = filters.get("from_date")
	to_date = filters.get("to_date")
	prospect_filter = filters.get("prospect")
	territory_filter = filters.get("territory")

	# 1) Prospects (Customer Management)
	prospect_filters = {}
	if company:
		prospect_filters["company"] = company
	if prospect_filter:
		prospect_filters["name"] = prospect_filter
	if territory_filter:
		prospect_filters["territory"] = territory_filter

	prospect_meta = frappe.get_meta("Prospect")
	prospect_fields = ["name", "company_name", "territory", "prospect_owner"]
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
	prospect_map = {p["name"]: p for p in prospects}

	# 2) Prospect Opportunity → Opportunity
	po_list = frappe.get_all(
		"Prospect Opportunity",
		filters={"parent": ["in", prospect_names]},
		fields=["parent", "opportunity", "amount", "expected_closing", "currency"],
	)
	if not po_list:
		return _rows_no_opportunities(prospects, filters)

	opp_names = list({r["opportunity"] for r in po_list if r.get("opportunity")})
	if not opp_names:
		return _rows_no_opportunities(prospects, filters)

	opp_filters = {"name": ["in", opp_names]}
	if from_date and to_date:
		opp_filters["transaction_date"] = ["between", [from_date, to_date]]

	opp_list = frappe.get_all(
		"Opportunity",
		filters=opp_filters,
		fields=["name", "status", "sales_stage", "opportunity_amount", "total", "expected_closing", "currency", "transaction_date"],
	)
	opp_map = {o["name"]: o for o in opp_list}

	# 3) Sample Request (sample_request_id = Opportunity)
	sr_by_opp = {}
	sr_amount_by_name = {}
	if frappe.db.table_exists("Sample Request"):
		sr_list = frappe.get_all(
			"Sample Request",
			filters={"sample_request_id": ["in", opp_names]},
			fields=["name", "sample_request_id", "dispatch_date", "workflow_state", "docstatus"],
		)
		for sr in sr_list:
			opp = sr.get("sample_request_id")
			if opp and opp in opp_names:
				# First SR per opportunity (or append; we take first for one row per Opp)
				if opp not in sr_by_opp:
					sr_by_opp[opp] = sr
		# Amount from product_table (Quotation Item child)
		sr_names = [s["name"] for s in sr_list]
		if sr_names:
			items = frappe.get_all(
				"Quotation Item",
				filters={"parent": ["in", sr_names], "parenttype": "Sample Request"},
				fields=["parent", "amount", "rate"],
			)
			for it in items:
				sr_amount_by_name[it["parent"]] = sr_amount_by_name.get(it["parent"], 0) + flt(it.get("amount") or (flt(it.get("rate")) * 1), 2)

	# 4) Product Trial (enquiry_opportunity = Opportunity, trial_id = Sample Request)
	pt_by_opp = {}
	if frappe.db.table_exists("Product Trial"):
		pt_list = frappe.get_all(
			"Product Trial",
			filters={"enquiry_opportunity": ["in", opp_names]},
			fields=["name", "enquiry_opportunity", "trial_id", "trial_status", "trial_quantity"],
			order_by="creation desc",
		)   
		for pt in pt_list:
			opp = pt.get("enquiry_opportunity")
			if opp and opp in opp_names and opp not in pt_by_opp:
				pt_by_opp[opp] = pt

	# 5) Quotation: opportunity = Opportunity, or custom_product_trial = Product Trial
	quotation_by_opp = {}
	quotation_rate_by_name = {}
	quo_list = frappe.get_all(
		"Quotation",
		filters=[["opportunity", "in", opp_names], ["docstatus", "<", 2]],
		fields=["name", "opportunity", "transaction_date", "grand_total", "total", "currency"],
	)
	for q in quo_list:
		opp = q.get("opportunity")
		if opp and opp not in quotation_by_opp:
			quotation_by_opp[opp] = q
	# Quotations linked only via Product Trial (custom_product_trial)
	pt_names = [pt_by_opp[o]["name"] for o in pt_by_opp if pt_by_opp[o].get("name")]
	if pt_names and frappe.get_meta("Quotation").has_field("custom_product_trial"):
		quo_by_pt = frappe.get_all(
			"Quotation",
			filters=[["custom_product_trial", "in", pt_names], ["docstatus", "<", 2]],
			fields=["name", "opportunity", "custom_product_trial", "transaction_date", "grand_total", "total", "currency"],
		)
		pt_to_opp = {pt_by_opp[o]["name"]: o for o in pt_by_opp if pt_by_opp[o].get("name")}
		for q in quo_by_pt:
			opp = q.get("opportunity") or pt_to_opp.get(q.get("custom_product_trial"))
			if opp and opp not in quotation_by_opp:
				quotation_by_opp[opp] = q
		quo_list = quo_list + [q for q in quo_by_pt if q["name"] not in [x["name"] for x in quo_list]]
	if quo_list:
		quo_names = [q["name"] for q in quo_list]
		items = frappe.get_all(
			"Quotation Item",
			filters={"parent": ["in", quo_names], "parenttype": "Quotation"},
			fields=["parent", "rate"],
			order_by="parent, idx asc",
		)
		for it in items:
			if it["parent"] not in quotation_rate_by_name:
				quotation_rate_by_name[it["parent"]] = flt(it.get("rate"), 2)

	# 6) Build one row per Prospect–Opportunity
	company_currency = frappe.get_cached_value("Company", company, "default_currency") if company else "INR"
	rows = []
	for po in po_list:
		parent_prospect = po.get("parent")
		opp_name = po.get("opportunity")
		if not opp_name or opp_name not in opp_map:
			continue
		opp = opp_map[opp_name]
		prospect_doc = prospect_map.get(parent_prospect)
		if not prospect_doc:
			continue

		sr_doc = sr_by_opp.get(opp_name)
		pt_doc = pt_by_opp.get(opp_name)
		quo_doc = quotation_by_opp.get(opp_name)

		sr_amount = None
		if sr_doc:
			sr_amount = sr_amount_by_name.get(sr_doc["name"])
		quo_rate = quotation_rate_by_name.get(quo_doc["name"]) if quo_doc else None
		currency = (quo_doc or po or opp or {}).get("currency") or company_currency

		row = _prospect_row(prospect_doc)
		row.update({
			"opportunity": opp_name,
			"opportunity_status": opp.get("status"),
			"sales_stage": opp.get("sales_stage"),
			"opportunity_amount": flt(po.get("amount") or opp.get("opportunity_amount"), 2),
			"opportunity_total": flt(opp.get("total"), 2),
			"expected_closing": po.get("expected_closing") or opp.get("expected_closing"),
			"currency": currency,
			"sample_request": sr_doc.get("name") if sr_doc else None,
			"sample_request_amount": flt(sr_amount, 2) if sr_amount is not None else None,
			"sample_dispatch_date": sr_doc.get("dispatch_date") if sr_doc else None,
			"sample_request_status": sr_doc.get("workflow_state") or (_("Submitted") if sr_doc and sr_doc.get("docstatus") == 1 else None) if sr_doc else None,
			"product_trial": pt_doc.get("name") if pt_doc else None,
			"trial_status": pt_doc.get("trial_status") if pt_doc else None,
			"trial_quantity": flt(pt_doc.get("trial_quantity"), 2) if pt_doc else None,
			"quotation": quo_doc.get("name") if quo_doc else None,
			"quotation_amount": flt(quo_doc.get("grand_total") or quo_doc.get("total"), 2) if quo_doc else None,
			"quotation_rate": quo_rate,
			"quotation_date": quo_doc.get("transaction_date") if quo_doc else None,
			"conversion_done": _("Done") if quo_doc else _("Not Done"),
		}) 
		rows.append(row)

	return rows


def _prospect_row(prospect_doc):
	"""Base row from Prospect (Customer Management)."""
	return {
		"prospect_name": prospect_doc.get("name"),
		"company_name": prospect_doc.get("company_name"),
		"customer_name_cm": prospect_doc.get("custom_customer_name"),
		"territory": prospect_doc.get("territory"),
		"assigned_sales_person": prospect_doc.get("custom_assigned_sales_person") or prospect_doc.get("prospect_owner"),
		"contact_person": prospect_doc.get("custom_contact_person"),
		"email": prospect_doc.get("custom_email"),
		"mobile": prospect_doc.get("custom_mobile_no"),
	}


def _rows_no_opportunities(prospects, filters):
	"""Prospects with no linked opportunities: show only Customer Management columns."""
	company = filters.get("company")
	company_currency = frappe.get_cached_value("Company", company, "default_currency") if company else "INR"
	rows = []
	empty = {
		"opportunity": None, "opportunity_status": None, "sales_stage": None,
		"opportunity_amount": None, "opportunity_total": None, "expected_closing": None, "currency": company_currency,
		"sample_request": None, "sample_request_amount": None, "sample_dispatch_date": None, "sample_request_status": None,
		"product_trial": None, "trial_status": None, "trial_quantity": None,
		"quotation": None, "quotation_amount": None, "quotation_rate": None, "quotation_date": None,
		"conversion_done": _("Not Done"),
	}
	for p in prospects:
		row = _prospect_row(p)
		row.update(empty)
		rows.append(row)
	return rows
