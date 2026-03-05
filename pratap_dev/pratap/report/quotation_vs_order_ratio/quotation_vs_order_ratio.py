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
	"""Columns for Quotation vs Order Ratio: conversion of quotations into orders."""
	return [
		{
			"label": _("Enquiry ID"),
			"fieldname": "enquiry_id",
			"fieldtype": "Link",
			"options": "Opportunity",
			"width": 200,
		},
		{"label": _("Customer Name"), "fieldname": "customer_name", "fieldtype": "Data", "width": 240},
		{
			"label": _("Quotation ID"),
			"fieldname": "quotation_id",
			"fieldtype": "Link",
			"options": "Quotation",
			"width": 200,
		},
		{"label": _("Quotation Date"), "fieldname": "quotation_date", "fieldtype": "Date", "width": 110},
		{
			"label": _("Quotation Value"),
			"fieldname": "quotation_value",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 160,
		},
		{
			"label": _("Sales Order ID"),
			"fieldname": "sales_order_id",
			"fieldtype": "Link",
			"options": "Sales Order",
			"width": 200,
		},
		{"label": _("Order Date"), "fieldname": "order_date", "fieldtype": "Date", "width": 110},
		{
			"label": _("Order Value"),
			"fieldname": "order_value",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 120,
		},
		{
			"label": _("Sales Person"),
			"fieldname": "sales_person",
			"fieldtype": "Link",
			"options": "Sales Person",
			"width": 190,
		},
		{"fieldname": "currency", "hidden": 1},
	]


def get_data(filters):
	"""Build rows from Quotation, linked Opportunity (Enquiry), and Sales Order if converted."""
	if not filters.get("company"):
		return []

	# 1) All Quotations in date range and company
	quotation_list = frappe.get_all(
		"Quotation",
		filters={
			"company": filters["company"],
			"transaction_date": ["between", [filters.get("from_date"), filters.get("to_date")]],
		},
		fields=[
			"name",
			"opportunity",
			"party_name",
			"customer_name",
			"transaction_date",
			"base_grand_total",
			"grand_total",
			"currency",
		],
		order_by="transaction_date asc",
	)
	if not quotation_list:
		return []

	qtn_names = [q["name"] for q in quotation_list]

	# 2) First Sales Person per Quotation (from sales_team)
	sales_team_list = frappe.get_all(
		"Sales Team",
		filters={"parent": ["in", qtn_names], "parenttype": "Quotation"},
		fields=["parent", "sales_person"],
		order_by="parent, idx asc",
	)
	qtn_to_sales_person = {}
	for row in sales_team_list:
		if row["parent"] not in qtn_to_sales_person:
			qtn_to_sales_person[row["parent"]] = row["sales_person"]

	# 3) Sales Orders created from these Quotations (SO Item has prevdoc_docname = Quotation name)
	so_item_list = frappe.get_all(
		"Sales Order Item",
		filters={"prevdoc_docname": ["in", qtn_names]},
		fields=["parent", "prevdoc_docname"],
		order_by="prevdoc_docname, parent asc",
	)
	# One quotation can have multiple SOs (e.g. partial); take first SO per quotation
	qtn_to_so = {}
	for row in so_item_list:
		if row["prevdoc_docname"] and row["prevdoc_docname"] not in qtn_to_so:
			qtn_to_so[row["prevdoc_docname"]] = row["parent"]

	so_names = list(set(qtn_to_so.values()))
	so_details = {}
	if so_names:
		for so in frappe.get_all(
			"Sales Order",
			filters={"name": ["in", so_names]},
			fields=["name", "transaction_date", "base_grand_total", "grand_total", "currency"],
		):
			so_details[so["name"]] = so

	company_currency = frappe.get_cached_value("Company", filters["company"], "default_currency") or "INR"
	rows = []
	for q in quotation_list:
		so_name = qtn_to_so.get(q["name"])
		so_data = so_details.get(so_name) if so_name else None
		currency = q.get("currency") or company_currency
		rows.append({
			"enquiry_id": q.get("opportunity") or "",
			"customer_name": q.get("customer_name") or q.get("party_name") or "",
			"quotation_id": q["name"],
			"quotation_date": q.get("transaction_date"),
			"quotation_value": flt(q.get("base_grand_total") or q.get("grand_total"), 2),
			"sales_order_id": so_name or "",
			"order_date": so_data.get("transaction_date") if so_data else None,
			"order_value": flt(so_data.get("base_grand_total") or so_data.get("grand_total"), 2) if so_data else None,
			"sales_person": qtn_to_sales_person.get(q["name"]) or "",
			"currency": currency,
		})

	# Apply sales person filter if set
	if filters.get("sales_person"):
		rows = [r for r in rows if r.get("sales_person") == filters["sales_person"]]

	return rows
