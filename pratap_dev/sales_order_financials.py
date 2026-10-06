# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Credit / payment info shown (read-only) on the Sales Order:

- custom_credit_limit                  -> the customer's credit limit for the company
- custom_current_outstanding           -> total outstanding of the customer's unpaid Sales Invoices
- custom_payment_received_against_order -> amount of submitted Payment Entries allocated to THIS order

These are computed live on the form (see public/js/sales_order.js) and also snapshotted
on save so they are available in list view / reports.
"""

import frappe
from frappe.utils import flt


def get_financials(customer, company, sales_order=None):
	"""Return {credit_limit, current_outstanding, payment_received} for the given customer."""

	from erpnext.selling.doctype.customer.customer import get_credit_limit

	credit_limit = get_credit_limit(customer, company) if (customer and company) else 0

	current_outstanding = 0
	if customer and company:
		current_outstanding = frappe.db.sql(
			"""
			select coalesce(sum(outstanding_amount), 0)
			from `tabSales Invoice`
			where customer = %s and company = %s and docstatus = 1 and outstanding_amount > 0
			""",
			(customer, company),
		)[0][0]

	payment_received = 0
	if sales_order and frappe.db.exists("Sales Order", sales_order):
		payment_received = frappe.db.sql(
			"""
			select coalesce(sum(per.allocated_amount), 0)
			from `tabPayment Entry Reference` per
			inner join `tabPayment Entry` pe on pe.name = per.parent
			where per.reference_doctype = 'Sales Order'
			  and per.reference_name = %s
			  and pe.docstatus = 1
			""",
			sales_order,
		)[0][0]

	return {
		"credit_limit": flt(credit_limit),
		"current_outstanding": flt(current_outstanding),
		"payment_received": flt(payment_received),
	}


@frappe.whitelist()
def get_sales_order_financials(customer, company, sales_order=None):
	"""Whitelisted wrapper for the client script (live refresh on the form)."""
	return get_financials(customer, company, sales_order)


def set_financials_snapshot(doc, method=None):
	"""Persist a snapshot of the three values on save (validate hook)."""
	data = get_financials(doc.customer, doc.company, doc.name)
	doc.custom_credit_limit = data["credit_limit"]
	doc.custom_current_outstanding = data["current_outstanding"]
	doc.custom_payment_received_against_order = data["payment_received"]
