# Copyright (c) 2026, saurabh@exacuer.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	"""Columns for Overall Sales Dashboard: CRM enquiry + ERP sales data."""
	return [
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 180},
		{
			"label": _("Sales Person"),
			"fieldname": "sales_person",
			"fieldtype": "Link",
			"options": "Sales Person",
			"width": 130,
		},
		{
			"label": _("Enquiry ID"),
			"fieldname": "enquiry_id",
			"fieldtype": "Link",
			"options": "Opportunity",
			"width": 130,
		},
		{
			"label": _("Sales Order ID"),
			"fieldname": "sales_order_id",
			"fieldtype": "Link",
			"options": "Sales Order",
			"width": 130,
		},
		{
			"label": _("Invoice ID"),
			"fieldname": "invoice_id",
			"fieldtype": "Link",
			"options": "Sales Invoice",
			"width": 130,
		},
		{"label": _("Order Date"), "fieldname": "order_date", "fieldtype": "Date", "width": 100},
		{"label": _("Invoice Date"), "fieldname": "invoice_date", "fieldtype": "Date", "width": 100},
		{
			"label": _("Revenue"),
			"fieldname": "revenue",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 120,
		},
		{"fieldname": "currency", "hidden": 1},
		{"label": _("Order Count"), "fieldname": "order_count", "fieldtype": "Int", "width": 100},
		{"label": _("Target Sales"), "fieldname": "target", "fieldtype": "Currency", "options": "currency", "width": 120},
		{"label": _("Achieved Sales"), "fieldname": "achieved", "fieldtype": "Currency", "options": "currency", "width": 120},
	]


def get_data(filters):
	"""Build dashboard rows from Sales Invoice, Sales Order, and optional Opportunity (Enquiry)."""
	if not filters.get("company"):
		return []

	# 1) All Sales Invoices in date range and company
	si_list = frappe.get_all(
		"Sales Invoice",
		filters={
			"company": filters["company"],
			"posting_date": ["between", [filters.get("from_date"), filters.get("to_date")]],
			"docstatus": 1,
		},
		fields=["name", "customer", "customer_name", "posting_date", "base_grand_total", "currency"],
		order_by="posting_date asc",
	)
	if not si_list:
		# Still return summary row with target and achieved = 0
		return _build_summary_rows([], filters)

	si_names = [d["name"] for d in si_list]

	# 2) First Sales Order per Sales Invoice (from items)
	si_items = frappe.get_all(
		"Sales Invoice Item",
		filters={"parent": ["in", si_names], "sales_order": ["!=", ""]},
		fields=["parent", "sales_order"],
		order_by="parent, idx asc",
	)
	si_to_so = {}
	for row in si_items:
		if row["parent"] not in si_to_so:
			si_to_so[row["parent"]] = row["sales_order"]

	# 3) First Sales Person per Sales Invoice (from sales_team)
	si_team = frappe.get_all(
		"Sales Team",
		filters={"parent": ["in", si_names], "parenttype": "Sales Invoice"},
		fields=["parent", "sales_person"],
		order_by="parent, idx asc",
	)
	si_to_sales_person = {}
	for row in si_team:
		if row["parent"] not in si_to_sales_person:
			si_to_sales_person[row["parent"]] = row["sales_person"]

	# If no sales team on SI, fallback to Sales Order's sales team
	so_names = list(set(si_to_so.values()))
	so_team = []
	if so_names:
		so_team = frappe.get_all(
			"Sales Team",
			filters={"parent": ["in", so_names], "parenttype": "Sales Order"},
			fields=["parent", "sales_person"],
			order_by="parent, idx asc",
		)
	so_to_sales_person = {}
	for row in so_team:
		if row["parent"] not in so_to_sales_person:
			so_to_sales_person[row["parent"]] = row["sales_person"]

	# 4) Sales Order details (order date, custom enquiry/opportunity if present)
	so_details = {}
	enquiry_field = _get_opportunity_field_on_so()
	if so_names:
		fields = ["name", "transaction_date"]
		if enquiry_field:
			fields.append(enquiry_field)
		for so in frappe.get_all("Sales Order", filters={"name": ["in", so_names]}, fields=fields):
			so_details[so["name"]] = {
				"order_date": so.get("transaction_date"),
				"enquiry_id": so.get(enquiry_field) if enquiry_field else None,
			}

	# 5) Build detail rows (one per Sales Invoice)
	order_ids_seen = set()
	rows = []
	for si in si_list:
		so_id = si_to_so.get(si["name"])
		sales_person = si_to_sales_person.get(si["name"]) or (so_to_sales_person.get(so_id) if so_id else None)
		details = so_details.get(so_id, {}) if so_id else {}
		if so_id:
			order_ids_seen.add(so_id)

		rows.append({
			"customer": si.get("customer_name") or si.get("customer"),
			"sales_person": sales_person or "",
			"enquiry_id": details.get("enquiry_id") or "",
			"sales_order_id": so_id or "",
			"invoice_id": si["name"],
			"order_date": details.get("order_date"),
			"invoice_date": si.get("posting_date"),
			"revenue": flt(si.get("base_grand_total"), 2),
			"currency": si.get("currency") or frappe.get_cached_value("Company", filters["company"], "default_currency"),
		})

	# Apply sales person filter if set
	if filters.get("sales_person"):
		rows = [r for r in rows if r.get("sales_person") == filters["sales_person"]]
		order_ids_seen = {r.get("sales_order_id") for r in rows if r.get("sales_order_id")}

	# 6) Add summary row: Order Count, Target, Achieved
	achieved = sum(flt(r.get("revenue")) for r in rows)
	summary = _build_summary_rows(rows, filters, order_count=len(order_ids_seen), achieved=achieved)
	return rows + summary


def _get_opportunity_field_on_so():
	"""Return custom field name on Sales Order that links to Opportunity (Enquiry), if any."""
	try:
		meta = frappe.get_meta("Sales Order")
		for df in meta.get("fields", []):
			if df.get("fieldname") and df.get("options") == "Opportunity":
				return df.fieldname
		for df in meta.get("fields", []):
			if (df.get("fieldname") or "").lower() in ("custom_opportunity", "custom_enquiry_id", "opportunity", "enquiry_id"):
				return df.fieldname
	except Exception:
		pass
	return None


def _build_summary_rows(detail_rows, filters, order_count=0, achieved=0):
	"""Append a summary row with Order Count, Target, Achieved."""
	company_currency = frappe.get_cached_value("Company", filters.get("company"), "default_currency") or "INR"

	# Target: from Target Detail (Sales Person targets) for the fiscal year
	sales_persons = list({r.get("sales_person") for r in detail_rows if r.get("sales_person")})
	target = 0
	if sales_persons and filters.get("fiscal_year"):
		target_result = frappe.get_all(
			"Target Detail",
			filters={
				"parent": ["in", sales_persons],
				"parenttype": "Sales Person",
				"fiscal_year": filters["fiscal_year"],
			},
			fields=["target_amount"],
		)
		target = sum(flt(t["target_amount"]) for t in target_result)
	# If no fiscal year or no sales person filter, get total target for all sales persons for the year
	if not target and filters.get("fiscal_year"):
		target_result = frappe.get_all(
			"Target Detail",
			filters={"parenttype": "Sales Person", "fiscal_year": filters["fiscal_year"]},
			fields=["target_amount"],
		)
		target = sum(flt(t["target_amount"]) for t in target_result)

	summary_row = {
		"customer": _("Total"),
		"sales_person": "",
		"enquiry_id": "",
		"sales_order_id": "",
		"invoice_id": "",
		"order_date": None,
		"invoice_date": None,
		"revenue": None,
		"currency": company_currency,
		"order_count": order_count,
		"target": flt(target, 2),
		"achieved": flt(achieved, 2),
	}
	return [summary_row]
