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

CHART_COLORS = [
	"#0CA678",
	"#2490EF",
	"#F6A623",
	"#E8625A",
	"#7C5CFC",
	"#15AABF",
	"#E67700",
	"#4263EB",
]


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)
	data = get_data(filters)
	return get_columns(), data, None, get_chart(data)


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
		{"fieldname": "workflow_state", "label": _("Status"), "fieldtype": "Data", "width": 180},
		{"fieldname": "request_count", "label": _("TSA Requests"), "fieldtype": "Int", "width": 140},
		{"fieldname": "percentage", "label": _("Percentage"), "fieldtype": "Percent", "precision": 2, "width": 120},
	]


def get_data(filters):
	TSA = frappe.qb.DocType("TSA Request")
	date_field = TSA[DATE_FIELDS[filters.date_based_on]]
	request_count = Count(TSA.name)
	query = (
		frappe.qb.from_(TSA)
		.select(TSA.workflow_state.as_("workflow_state"), request_count.as_("request_count"))
		.where(date_field >= filters.from_date)
		.where(date_field < add_days(filters.to_date, 1))
		.groupby(TSA.workflow_state)
		.orderby(request_count, order=frappe.qb.desc)
	)
	if filters.get("tsa_request_type"):
		query = query.where(TSA.tsa_request_type == filters.tsa_request_type)
	if filters.get("creator"):
		query = query.where(TSA.creator_id == filters.creator)
	if filters.get("workflow_state"):
		query = query.where(TSA.workflow_state == filters.workflow_state)
	if filters.get("courier_details"):
		query = query.where(TSA.courier_details == filters.courier_details)

	rows = query.run(as_dict=True)
	grand_total = sum(cint(r.request_count) for r in rows)
	data = []
	for row in rows:
		count = cint(row.request_count)
		if not count:
			continue
		data.append(
			{
				"workflow_state": row.workflow_state or _("Not Set"),
				"request_count": count,
				"percentage": (count / grand_total * 100) if grand_total else 0,
			}
		)
		if len(data) >= filters.limit:
			break
	return data


def get_chart(data):
	return {
		"data": {
			"labels": [row["workflow_state"] for row in data],
			"datasets": [{"name": _("TSA Requests"), "values": [row["request_count"] for row in data]}],
		},
		"type": "donut",
		"colors": CHART_COLORS,
	}
