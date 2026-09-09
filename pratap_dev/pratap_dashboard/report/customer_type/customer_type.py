# Copyright (c) 2026, exacuer and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder.functions import Count


def execute(filters=None):
	columns = get_columns()
	data = get_data()
	chart = get_chart(data)

	return columns, data, None, chart


def get_columns():
	return [
		{
			"fieldname": "customer_type",
			"label": _("Customer Type"),
			"fieldtype": "Data",
			"width": 220,
		},
		{
			"fieldname": "customer_count",
			"label": _("Number of Customers"),
			"fieldtype": "Int",
			"width": 180,
		},
		{
			"fieldname": "percentage",
			"label": _("Percentage"),
			"fieldtype": "Percent",
			"precision": 2,
			"width": 130,
		},
	]


def get_data():
	Customer = frappe.qb.DocType("Customer")
	customer_count = Count(Customer.name)

	rows = (
		frappe.qb.from_(Customer)
		.select(Customer.customer_type, customer_count.as_("customer_count"))
		.groupby(Customer.customer_type)
		.orderby(customer_count, order=frappe.qb.desc)
		.run(as_dict=True)
	)
	total_customers = sum(row.customer_count for row in rows)

	return [
		{
			"customer_type": row.customer_type or _("Not Set"),
			"customer_count": row.customer_count,
			"percentage": (row.customer_count / total_customers * 100) if total_customers else 0,
		}
		for row in rows
	]


def get_chart(data):
	return {
		"data": {
			"labels": [row["customer_type"] for row in data],
			"datasets": [
				{
					"name": _("Customers"),
					"values": [row["customer_count"] for row in data],
				}
			],
		},
		"type": "donut",
	}
