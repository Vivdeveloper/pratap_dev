# Copyright (c) 2026, saurabh@exacuer.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, today


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	"""Columns for Receivable Aging: unpaid invoices and overdue tracking."""
	return [
		{
			"label": _("Invoice Number"),
			"fieldname": "invoice_number",
			"fieldtype": "Link",
			"options": "Sales Invoice",
			"width": 200,
		},
		{"label": _("Customer Name"), "fieldname": "customer_name", "fieldtype": "Link", "options": "Customer", "width": 160},
		{"label": _("Invoice Date"), "fieldname": "invoice_date", "fieldtype": "Date", "width": 100},
		{"label": _("Due Date"), "fieldname": "due_date", "fieldtype": "Date", "width": 100},
		{
			"label": _("Total Amount"),
			"fieldname": "total_amount",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 120,
		},
		{
			"label": _("Paid Amount"),
			"fieldname": "paid_amount",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 120,
		},
		{
			"label": _("Outstanding Amount"),
			"fieldname": "outstanding_amount",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 130,
		},
		{"label": _("Aging Days"), "fieldname": "aging_days", "fieldtype": "Int", "width": 100},
		{"label": _("Aging Bucket"), "fieldname": "aging_bucket", "fieldtype": "Data", "width": 100},
		{"fieldname": "currency", "hidden": 1},
	]


def get_data(filters):
	"""Build aging rows from Sales Invoice (outstanding); paid amount from SI / Payment Entry."""
	if not filters.get("company"):
		return []

	# Sales Invoices with outstanding > 0 (or all and filter after)
	si_filters = {"company": filters["company"], "docstatus": 1}
	if filters.get("from_date") and filters.get("to_date"):
		si_filters["posting_date"] = ["between", [filters["from_date"], filters["to_date"]]]
	if filters.get("customer"):
		si_filters["customer"] = filters["customer"]

	invoices = frappe.get_all(
		"Sales Invoice",
		filters=si_filters,
		fields=[
			"name",
			"customer",
			"customer_name",
			"posting_date",
			"due_date",
			"grand_total",
			"base_grand_total",
			"paid_amount",
			"base_paid_amount",
			"outstanding_amount",
			"currency",
		],
		order_by="due_date asc",
	)
	# Only show with outstanding (receivable)
	if filters.get("show_only_outstanding", True):
		invoices = [i for i in invoices if flt(i.get("outstanding_amount")) > 0]
	else:
		invoices = [i for i in invoices if flt(i.get("grand_total")) > 0]

	company_currency = frappe.get_cached_value("Company", filters["company"], "default_currency")
	as_on_date = getdate(filters.get("as_on_date") or today())
	rows = []
	for inv in invoices:
		due = inv.get("due_date")
		# Aging days: days overdue (positive if past due)
		if due:
			aging_days = (as_on_date - getdate(due)).days
		else:
			aging_days = 0
		aging_bucket = _aging_bucket(aging_days)

		# Use base amounts for consistent company currency when needed
		total = flt(inv.get("base_grand_total") or inv.get("grand_total"))
		paid = flt(inv.get("base_paid_amount") or inv.get("paid_amount"))
		outstanding = flt(inv.get("outstanding_amount"))
		currency = inv.get("currency") or company_currency

		rows.append({
			"invoice_number": inv["name"],
			"customer_name": inv.get("customer_name") or inv.get("customer"),
			"invoice_date": inv.get("posting_date"),
			"due_date": due,
			"total_amount": total,
			"paid_amount": paid,
			"outstanding_amount": outstanding,
			"aging_days": aging_days if aging_days > 0 else 0,
			"aging_bucket": aging_bucket,
			"currency": currency,
		})

	# Optional filter by aging bucket
	if filters.get("aging_bucket"):
		rows = [r for r in rows if r.get("aging_bucket") == filters["aging_bucket"]]

	return rows


def _aging_bucket(aging_days):
	"""Return bucket 0-30 / 30-60 / 60-90 / 90+ (or Not Due)."""
	if aging_days <= 0:
		return "Not Due"
	if aging_days <= 30:
		return "0-30"
	if aging_days <= 60:
		return "30-60"
	if aging_days <= 90:
		return "60-90"
	return "90+"
