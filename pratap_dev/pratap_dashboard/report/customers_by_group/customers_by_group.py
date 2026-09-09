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
			"fieldname": "customer_group",
			"label": _("Customer Group"),
			"fieldtype": "Data",
			"width": 240,
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
		.select(Customer.customer_group, customer_count.as_("customer_count"))
		.groupby(Customer.customer_group)
		.orderby(customer_count, order=frappe.qb.desc)
		.run(as_dict=True)
	)
	count_by_group = {}
	for row in rows:
		customer_group = row.customer_group or _("Not Set")
		count_by_group[customer_group] = count_by_group.get(customer_group, 0) + row.customer_count

	total_customers = sum(count_by_group.values())
	return [
		{
			"customer_group": customer_group,
			"customer_count": count,
			"percentage": (count / total_customers * 100) if total_customers else 0,
		}
		for customer_group, count in sorted(
			count_by_group.items(), key=lambda item: item[1], reverse=True
		)
	]


def get_chart(data):
	return {
		"data": {
			"labels": [row["customer_group"] for row in data],
			"datasets": [
				{
					"name": _("Customers"),
					"values": [row["customer_count"] for row in data],
				}
			],
		},
		"type": "bar",
		"colors": ["#5e64ff"],
	}
