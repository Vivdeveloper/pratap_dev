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
			"fieldname": "territory",
			"label": _("Territory"),
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
		.select(Customer.territory, customer_count.as_("customer_count"))
		.groupby(Customer.territory)
		.orderby(customer_count, order=frappe.qb.desc)
		.run(as_dict=True)
	)
	count_by_territory = {}
	for row in rows:
		territory = row.territory or _("Not Set")
		count_by_territory[territory] = count_by_territory.get(territory, 0) + row.customer_count

	total_customers = sum(count_by_territory.values())
	return [
		{
			"territory": territory,
			"customer_count": count,
			"percentage": (count / total_customers * 100) if total_customers else 0,
		}
		for territory, count in sorted(
			count_by_territory.items(), key=lambda item: item[1], reverse=True
		)
	]


def get_chart(data):
	return {
		"data": {
			"labels": [row["territory"] for row in data],
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
