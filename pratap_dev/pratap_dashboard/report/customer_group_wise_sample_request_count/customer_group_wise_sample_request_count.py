# Copyright (c) 2026, saurabh@exacuer.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder.functions import Count
from frappe.utils import add_days, cint, getdate


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

	limit = cint(filters.get("limit") or 10)
	if limit < 1:
		frappe.throw(_("Limit must be at least 1."))
	filters.limit = limit


def get_columns():
	return [
		{
			"fieldname": "customer_group",
			"label": _("Customer Group"),
			"fieldtype": "Link",
			"options": "Customer Group",
			"width": 200,
		},
		{
			"fieldname": "request_count",
			"label": _("Sample Requests"),
			"fieldtype": "Int",
			"width": 150,
		},
		{
			"fieldname": "percentage",
			"label": _("Percentage"),
			"fieldtype": "Percent",
			"precision": 2,
			"width": 130,
		},
	]


def get_data(filters):
	SampleRequest = frappe.qb.DocType("Sample Request")
	date_field = SampleRequest[DATE_FIELDS[filters.date_based_on]]
	request_count = Count(SampleRequest.name)

	query = (
		frappe.qb.from_(SampleRequest)
		.select(
			SampleRequest.customer_group.as_("customer_group"),
			request_count.as_("request_count"),
		)
		.where(date_field >= filters.from_date)
		.where(date_field < add_days(filters.to_date, 1))
		.groupby(SampleRequest.customer_group)
		.orderby(request_count, order=frappe.qb.desc)
	)
	query = apply_optional_filters(query, SampleRequest, filters)

	if filters.get("item_code"):
		matching_requests = get_requests_for_item(filters.item_code)
		if not matching_requests:
			return []
		query = query.where(SampleRequest.name.isin(matching_requests))

	rows = query.run(as_dict=True)
	grand_total = sum(cint(row.request_count) for row in rows)

	data = []
	for row in rows:
		count = cint(row.request_count)
		if not count:
			continue
		data.append(
			{
				"customer_group": row.customer_group or _("Not Set"),
				"request_count": count,
				"percentage": (count / grand_total * 100) if grand_total else 0,
			}
		)
		if len(data) >= filters.limit:
			break

	return data


def apply_optional_filters(query, SampleRequest, filters):
	field_map = {
		"customer": SampleRequest.customer_id,
		"customer_group": SampleRequest.customer_group,
		"sample_type": SampleRequest.sample_type,
		"approval_status": SampleRequest.approval_status,
		"region": SampleRequest.region,
		"territory": SampleRequest.territory,
		"city": SampleRequest.city,
		"creator": SampleRequest.creator,
	}
	for filter_name, field in field_map.items():
		if filters.get(filter_name):
			query = query.where(field == filters[filter_name])

	return query


def get_requests_for_item(item_code):
	return frappe.get_all(
		"Sample CRM Item",
		filters={
			"parenttype": "Sample Request",
			"parentfield": "sample_crm_item",
			"item_code": item_code,
		},
		pluck="parent",
	)


def get_chart(data):
	return {
		"data": {
			"labels": [row["customer_group"] for row in data],
			"datasets": [
				{
					"name": _("Sample Requests"),
					"values": [row["request_count"] for row in data],
				}
			],
		},
		"type": "donut",
		"colors": [
			"#E8625A",
			"#2490EF",
			"#0CA678",
			"#F6A623",
			"#7C5CFC",
			"#15AABF",
			"#E67700",
			"#12B886",
		],
	}
