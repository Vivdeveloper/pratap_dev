# Copyright (c) 2026, exacuer and contributors
# For license information, please see license.txt

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_months, add_years, flt, getdate


DATE_FIELDS = {
	"Created Date": "created_date",
	"Dispatch Date": "dispatch_date",
	"Document Creation": "creation",
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)

	columns = get_columns()
	data = get_data(filters)
	chart = get_chart(data)

	return columns, data, None, chart


def validate_filters(filters):
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw(_("From Date and To Date are required."))

	if getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be after To Date."))

	if filters.get("date_based_on") not in DATE_FIELDS:
		frappe.throw(_("Please select a valid Date Based On value."))

	if filters.get("periodicity") not in ("Monthly", "Quarterly", "Yearly"):
		frappe.throw(_("Please select a valid Periodicity."))


def get_columns():
	return [
		{
			"fieldname": "period",
			"label": _("Period"),
			"fieldtype": "Data",
			"width": 160,
		},
		{
			"fieldname": "request_count",
			"label": _("Sample Requests"),
			"fieldtype": "Int",
			"width": 150,
		},
		{
			"fieldname": "total_quantity",
			"label": _("Total Quantity"),
			"fieldtype": "Float",
			"width": 150,
		},
		{
			"fieldname": "average_quantity",
			"label": _("Average Quantity"),
			"fieldtype": "Float",
			"width": 160,
		},
	]


def get_data(filters):
	date_field = DATE_FIELDS[filters.date_based_on]
	request_filters = {
		date_field: ["between", [filters.from_date, filters.to_date]],
	}
	add_optional_filters(request_filters, filters)

	if filters.get("item_code"):
		request_names = get_requests_for_item(filters.item_code)
		if not request_names:
			return []
		request_filters["name"] = ["in", request_names]

	requests = frappe.get_all(
		"Sample Request",
		filters=request_filters,
		fields=[date_field, "total_quantity", "total_qty"],
		order_by=f"{date_field} asc",
	)

	grouped_data = defaultdict(lambda: {"request_count": 0, "total_quantity": 0})
	period_labels = {}
	for period_date in get_period_dates(filters.from_date, filters.to_date, filters.periodicity):
		period_key, period_label = get_period(period_date, filters.periodicity)
		grouped_data[period_key]
		period_labels[period_key] = period_label

	for request in requests:
		request_date = request.get(date_field)
		if not request_date:
			continue

		period_key, period_label = get_period(request_date, filters.periodicity)
		period_labels[period_key] = period_label
		group = grouped_data[period_key]
		group["request_count"] += 1
		group["total_quantity"] += flt(request.get("total_quantity") or request.get("total_qty"))

	data = []
	for period_key, values in sorted(grouped_data.items()):
		request_count = values["request_count"]
		total_quantity = values["total_quantity"]
		data.append(
			{
				"period": period_labels[period_key],
				"request_count": request_count,
				"total_quantity": total_quantity,
				"average_quantity": total_quantity / request_count if request_count else 0,
			}
		)

	return data


def add_optional_filters(request_filters, filters):
	field_map = {
		"customer": "customer_id",
		"customer_group": "customer_group",
		"sample_type": "sample_type",
		"approval_status": "approval_status",
		"region": "region",
		"territory": "territory",
		"city": "city",
		"creator": "creator",
	}
	for filter_name, field_name in field_map.items():
		if filters.get(filter_name):
			request_filters[field_name] = filters[filter_name]


def get_requests_for_item(item_code):
	return frappe.get_all(
		"Quotation Item",
		filters={
			"parenttype": "Sample Request",
			"parentfield": "product_table",
			"item_code": item_code,
		},
		pluck="parent",
	)


def get_period(value, periodicity):
	date = getdate(value)

	if periodicity == "Yearly":
		return (date.year,), str(date.year)

	if periodicity == "Quarterly":
		quarter = ((date.month - 1) // 3) + 1
		return (date.year, quarter), _("Q{0} {1}").format(quarter, date.year)

	return (date.year, date.month), date.strftime("%b %Y")


def get_period_dates(from_date, to_date, periodicity):
	current_date = getdate(from_date)
	end_date = getdate(to_date)

	if periodicity == "Yearly":
		current_date = current_date.replace(month=1, day=1)
		increment = add_years
	elif periodicity == "Quarterly":
		quarter_start_month = ((current_date.month - 1) // 3) * 3 + 1
		current_date = current_date.replace(month=quarter_start_month, day=1)
		increment = lambda value, _years: add_months(value, 3)
	else:
		current_date = current_date.replace(day=1)
		increment = add_months

	while current_date <= end_date:
		yield current_date
		current_date = increment(current_date, 1)


def get_chart(data):
	return {
		"data": {
			"labels": [row["period"] for row in data],
			"datasets": [
				{
					"name": _("Sample Requests"),
					"values": [row["request_count"] for row in data],
					"chartType": "bar",
				},
				{
					"name": _("Total Quantity"),
					"values": [row["total_quantity"] for row in data],
					"chartType": "line",
				},
			],
		},
		"type": "axis-mixed",
		"colors": ["#5e64ff", "#28a745"],
	}
