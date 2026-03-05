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
	"""Columns for Customer Product Health Index: satisfaction and product performance."""
	return [
		{"label": _("Customer Name"), "fieldname": "customer_name", "fieldtype": "Link", "options": "Customer", "width": 230},
		{"label": _("Product"), "fieldname": "product", "fieldtype": "Data", "width": 230},
		{"label": _("Total Orders"), "fieldname": "total_orders", "fieldtype": "Int", "width": 140},
		{"label": _("Complaint Count"), "fieldname": "complaint_count", "fieldtype": "Int", "width": 140},
		{"label": _("Rejection Count"), "fieldname": "rejection_count", "fieldtype": "Int", "width": 140},
		{"label": _("Trial Success Rate"), "fieldname": "trial_success_rate", "fieldtype": "Percent", "width": 170},
		{"label": _("Repeat Orders"), "fieldname": "repeat_orders", "fieldtype": "Int", "width": 140},
		{"label": _("Health Status"), "fieldname": "health_status", "fieldtype": "Data", "width": 140},
	]


def get_data(filters):
	"""Build health index per customer from Sales Order, Complaint CAPA, Product Trial (if present)."""
	if not filters.get("company"):
		return []

	company = filters["company"]
	from_date = filters.get("from_date")
	to_date = filters.get("to_date")

	# 1) Sales Order data: customer, order count, products, repeat orders
	so_filters = {"company": company, "docstatus": 1}
	if from_date and to_date:
		so_filters["transaction_date"] = ["between", [from_date, to_date]]

	so_list = frappe.get_all(
		"Sales Order",
		filters=so_filters,
		fields=["name", "customer", "customer_name"],
		order_by="customer, transaction_date asc",
	)
	if not so_list:
		return []

	# Total orders and repeat orders per customer
	customer_orders = {}
	for so in so_list:
		c = so.get("customer") or so.get("customer_name")
		if not c:
			continue
		customer_orders[c] = customer_orders.get(c, 0) + 1

	# Products per customer (from Sales Order Item)
	so_names = [s["name"] for s in so_list]
	so_items = frappe.get_all(
		"Sales Order Item",
		filters={"parent": ["in", so_names]},
		fields=["parent", "item_code", "item_name"],
	)
	# Map SO -> customer
	so_to_customer = {s["name"]: (s.get("customer") or s.get("customer_name")) for s in so_list}
	customer_products = {}
	for row in so_items:
		c = so_to_customer.get(row["parent"])
		if not c:
			continue
		if c not in customer_products:
			customer_products[c] = set()
		customer_products[c].add(row.get("item_name") or row.get("item_code") or "")

	# 2) Complaint CAPA count per customer (if doctype exists)
	complaint_by_customer = _get_complaint_count_by_customer(company, from_date, to_date)

	# 3) Rejection count (Quality Inspection or custom – if available)
	rejection_by_customer = _get_rejection_count_by_customer(company, from_date, to_date)

	# 4) Product Trial success rate per customer (if doctype exists)
	trial_rate_by_customer = _get_trial_success_rate_by_customer(from_date, to_date)

	# 5) Build rows: one per customer
	customers = sorted(customer_orders.keys())
	rows = []
	for customer in customers:
		total_orders = customer_orders[customer]
		repeat_orders = max(0, total_orders - 1)
		products = customer_products.get(customer) or set()
		product_str = ", ".join(sorted(p for p in products if p))[:200] or "—"
		complaint_count = complaint_by_customer.get(customer, 0)
		rejection_count = rejection_by_customer.get(customer, 0)
		trial_success_rate = trial_rate_by_customer.get(customer)  # None when no trials

		health_status = _calculate_health_status(
			complaint_count=complaint_count,
			rejection_count=rejection_count,
			trial_success_rate=trial_success_rate,
			total_orders=total_orders,
		)

		rows.append({
			"customer_name": customer,
			"product": product_str,
			"total_orders": total_orders,
			"complaint_count": complaint_count,
			"rejection_count": rejection_count,
			"trial_success_rate": flt(trial_success_rate, 2) if trial_success_rate is not None else None,
			"repeat_orders": repeat_orders,
			"health_status": health_status,
		})

	# Optional: filter by customer
	if filters.get("customer"):
		rows = [r for r in rows if r.get("customer_name") == filters["customer"]]

	return rows


def _get_complaint_count_by_customer(company, from_date, to_date):
	"""Return dict customer -> count of Complaint CAPA. Resolve via Opportunity when complain_from=Opportunity."""
	out = {}
	if not frappe.db.table_exists("Complaint CAPA"):
		return out
	filters_capa = {}
	if from_date and to_date:
		filters_capa["creation"] = ["between", [from_date, to_date]]
	fields = ["name", "complain_from", "party_name"]
	if frappe.get_meta("Complaint CAPA").has_field("customer"):
		fields.append("customer")
	complaints = frappe.get_all(
		"Complaint CAPA",
		filters=filters_capa,
		fields=fields,
	)
	for c in complaints:
		customer = None
		if c.get("customer"):
			customer = c["customer"]
		elif c.get("complain_from") == "Customer" and c.get("party_name"):
			customer = c["party_name"]
		elif c.get("complain_from") == "Opportunity" and c.get("party_name"):
			opp = frappe.db.get_value(
				"Opportunity",
				c["party_name"],
				["opportunity_from", "party_name", "customer_name"],
				as_dict=True,
			)
			if opp:
				if opp.get("opportunity_from") == "Customer" and opp.get("party_name"):
					customer = opp["party_name"]
				else:
					# Prospect/Lead: use customer_name as display; match by Customer.customer_name
					customer = opp.get("customer_name") or opp.get("party_name")
					if customer:
						# Resolve to Customer link if possible
						link = frappe.db.get_value("Customer", {"customer_name": customer}, "name")
						if link:
							customer = link
		if customer:
			out[customer] = out.get(customer, 0) + 1
	return out


def _get_rejection_count_by_customer(company, from_date, to_date):
	"""Return dict customer -> rejection count. Use Quality Inspection or custom CAPA if available."""
	out = {}
	# Optional: Quality Inspection linked to Delivery Note/Sales Invoice -> customer
	if frappe.db.table_exists("Quality Inspection"):
		filters_qi = {}
		if from_date and to_date:
			filters_qi["report_date"] = ["between", [from_date, to_date]]
		for qi in frappe.get_all(
			"Quality Inspection",
			filters=filters_qi,
			fields=["name", "reference_type", "reference_name", "status"],
		):
			if qi.get("status") != "Rejected":
				continue
			customer = None
			if qi.get("reference_type") == "Sales Invoice" and qi.get("reference_name"):
				customer = frappe.db.get_value("Sales Invoice", qi["reference_name"], "customer")
			elif qi.get("reference_type") == "Delivery Note" and qi.get("reference_name"):
				customer = frappe.db.get_value("Delivery Note", qi["reference_name"], "customer")
			if customer:
				out[customer] = out.get(customer, 0) + 1
	return out


def _get_trial_success_rate_by_customer(from_date, to_date):
	"""Return dict customer -> success rate (0-100). Product Trial has customer_name and trial_status."""
	out = {}
	if not frappe.db.table_exists("Product Trial"):
		return out
	filters_pt = {}
	if from_date and to_date:
		filters_pt["creation"] = ["between", [from_date, to_date]]
	trials = frappe.get_all(
		"Product Trial",
		filters=filters_pt,
		fields=["name", "customer_name", "trial_status"],
	)
	# Normalize customer key: use Customer name if customer_name matches a Customer
	customer_counts = {}
	for t in trials:
		cn = (t.get("customer_name") or "").strip()
		if not cn:
			continue
		# Resolve to Customer link so we match same key as Sales Order
		link = frappe.db.get_value("Customer", {"customer_name": cn}, "name")
		key = link or cn
		if key not in customer_counts:
			customer_counts[key] = {"success": 0, "total": 0}
		customer_counts[key]["total"] += 1
		if (t.get("trial_status") or "").lower() in ("successful", "success"):
			customer_counts[key]["success"] += 1
	for key, v in customer_counts.items():
		if v["total"] > 0:
			out[key] = 100.0 * v["success"] / v["total"]
	return out


def _calculate_health_status(complaint_count, rejection_count, trial_success_rate, total_orders):
	"""Return Green / Amber / Red based on complaints, rejections, trial success."""
	# Red: high complaints/rejections or low trial success
	if complaint_count >= 3 or rejection_count >= 3:
		return "Red"
	if trial_success_rate is not None and trial_success_rate < 50:
		return "Red"
	# Amber: some issues
	if complaint_count >= 1 or rejection_count >= 1:
		return "Amber"
	if trial_success_rate is not None and trial_success_rate < 80:
		return "Amber"
	# Green: no issues, good trial rate
	return "Green"
