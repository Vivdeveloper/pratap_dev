# Copyright (c) 2026, saurabh@exacuer.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate, today


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	"""Columns for Customer Complaints Summary: complaints and corrective actions."""
	return [
		{
			"label": _("Complaint ID"),
			"fieldname": "complaint_id",
			"fieldtype": "Link",
			"options": "Complaint CAPA",
			"width": 150,
		},
		{"label": _("Customer Name"), "fieldname": "customer_name", "fieldtype": "Data", "width": 160},
		{"label": _("Product"), "fieldname": "product", "fieldtype": "Data", "width": 180},
		{"label": _("Complaint Type"), "fieldname": "complaint_type", "fieldtype": "Data", "width": 120},
		{"label": _("Risk Level"), "fieldname": "risk_level", "fieldtype": "Data", "width": 100},
		{"label": _("Root Cause"), "fieldname": "root_cause", "fieldtype": "Data", "width": 150},
		{"label": _("Corrective Action"), "fieldname": "corrective_action", "fieldtype": "Data", "width": 150},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
		{"label": _("Created Date"), "fieldname": "created_date", "fieldtype": "Date", "width": 110},
		{"label": _("Closure Date"), "fieldname": "closure_date", "fieldtype": "Date", "width": 110},
		{"label": _("Aging Days"), "fieldname": "aging_days", "fieldtype": "Int", "width": 100},
	]


def get_data(filters):
	"""Build rows from Complaint CAPA; resolve customer from party/Opportunity; product from child table."""
	if not frappe.db.table_exists("Complaint CAPA"):
		return []

	meta = frappe.get_meta("Complaint CAPA")
	fields = ["name", "complain_from", "party_name", "status", "closure_date", "creation"]
	optional = ["complaint_type", "risk_level", "root_cause", "corrective_action", "customer"]
	for f in optional:
		if meta.has_field(f):
			fields.append(f)

	cap_filters = {}
	if filters.get("from_date") and filters.get("to_date"):
		cap_filters["creation"] = ["between", [filters["from_date"], filters["to_date"]]]
	if filters.get("status"):
		cap_filters["status"] = filters["status"]
	if filters.get("company") and meta.has_field("company"):
		cap_filters["company"] = filters["company"]

	complaints = frappe.get_all(
		"Complaint CAPA",
		filters=cap_filters,
		fields=fields,
		order_by="creation desc",
	)
	if not complaints:
		return []

	cap_names = [c["name"] for c in complaints]

	# Product from child table (Quotation Item, parenttype=Complaint CAPA, parentfield=product)
	product_by_cap = {}
	for cap_name in cap_names:
		items = frappe.get_all(
			"Quotation Item",
			filters={"parent": cap_name, "parenttype": "Complaint CAPA", "parentfield": "product"},
			fields=["item_code", "item_name"],
			limit=1,
		)
		if items:
			product_by_cap[cap_name] = items[0].get("item_name") or items[0].get("item_code") or ""
		else:
			product_by_cap[cap_name] = ""

	# Resolve customer for each complaint (party or via Opportunity)
	customer_by_cap = _resolve_customers(complaints)

	# Build rows
	rows = []
	for c in complaints:
		cap_name = c["name"]
		created = c.get("creation")
		closure = c.get("closure_date")
		# Aging days: resolution duration (creation to closure), or days open if not closed
		if closure and created:
			aging_days = (getdate(closure) - getdate(created)).days
		elif created:
			aging_days = (getdate(today()) - getdate(created)).days
		else:
			aging_days = None

		rows.append({
			"complaint_id": cap_name,
			"customer_name": customer_by_cap.get(cap_name) or "—",
			"product": product_by_cap.get(cap_name) or "—",
			"complaint_type": c.get("complaint_type") or "—",
			"risk_level": c.get("risk_level") or "—",
			"root_cause": c.get("root_cause") or "—",
			"corrective_action": c.get("corrective_action") or "—",
			"status": c.get("status") or "—",
			"created_date": getdate(created) if created else None,
			"closure_date": getdate(closure) if closure else None,
			"aging_days": aging_days,
		})

	if filters.get("customer"):
		cust_name = frappe.db.get_value("Customer", filters["customer"], "customer_name") or filters["customer"]
		rows = [
			r for r in rows
			if (r.get("customer_name") == cust_name or r.get("customer_name") == filters["customer"])
		]

	return rows


def _resolve_customers(complaints):
	"""Resolve customer name for each Complaint CAPA from party or Opportunity."""
	out = {}
	for c in complaints:
		cap_name = c["name"]
		customer = c.get("customer")
		if customer:
			out[cap_name] = customer
			continue
		if c.get("complain_from") == "Customer" and c.get("party_name"):
			# party_name is customer ID; get customer_name for display
			name = frappe.db.get_value("Customer", c["party_name"], "customer_name")
			out[cap_name] = name or c["party_name"]
			continue
		if c.get("complain_from") == "Opportunity" and c.get("party_name"):
			opp = frappe.db.get_value(
				"Opportunity",
				c["party_name"],
				["opportunity_from", "party_name", "customer_name"],
				as_dict=True,
			)
			if opp:
				if opp.get("opportunity_from") == "Customer" and opp.get("party_name"):
					name = frappe.db.get_value("Customer", opp["party_name"], "customer_name")
					out[cap_name] = name or opp["party_name"]
				else:
					out[cap_name] = opp.get("customer_name") or opp.get("party_name") or ""
			else:
				out[cap_name] = ""
		else:
			out[cap_name] = c.get("party_name") or ""
	return out
