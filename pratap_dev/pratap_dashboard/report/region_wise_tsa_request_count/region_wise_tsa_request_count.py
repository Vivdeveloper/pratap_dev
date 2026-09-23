# Copyright (c) 2026, saurabh@exacuer.com and contributors
# For license information, please see license.txt

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate


DATE_FIELDS = {
	"Created Date": "created_date",
	"Dispatch Date": "dispatch_date",
	"Document Creation": "creation",
}

CHART_COLORS = [
	"#2490EF",
	"#0CA678",
	"#F6A623",
	"#E8625A",
	"#7C5CFC",
	"#15AABF",
	"#E67700",
	"#4263EB",
	"#12B886",
	"#FA5252",
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
		{"fieldname": "region", "label": _("Region"), "fieldtype": "Data", "width": 180},
		{"fieldname": "request_count", "label": _("TSA Requests"), "fieldtype": "Int", "width": 140},
		{"fieldname": "percentage", "label": _("Percentage"), "fieldtype": "Percent", "precision": 2, "width": 120},
	]


def coalesce_value(*values):
	for value in values:
		if value and str(value).strip():
			return str(value).strip()
	return _("Not Set")


def get_data(filters):
	date_field = DATE_FIELDS[filters.date_based_on]
	request_filters = {
		date_field: ["between", [filters.from_date, filters.to_date]],
	}
	if filters.get("tsa_request_type"):
		request_filters["tsa_request_type"] = filters.tsa_request_type
	if filters.get("workflow_state"):
		request_filters["workflow_state"] = filters.workflow_state
	if filters.get("creator"):
		request_filters["creator_id"] = filters.creator
	if filters.get("courier_details"):
		request_filters["courier_details"] = filters.courier_details

	rows = frappe.get_all(
		"TSA Request",
		filters=request_filters,
		fields=["region", "stock_region"],
	)

	totals = defaultdict(int)
	for row in rows:
		region = coalesce_value(row.stock_region, row.region)
		totals[region] += 1

	grand_total = sum(totals.values())
	data = []
	for region, count in sorted(totals.items(), key=lambda item: item[1], reverse=True):
		data.append(
			{
				"region": region,
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
			"labels": [row["region"] for row in data],
			"datasets": [{"name": _("TSA Requests"), "values": [row["request_count"] for row in data]}],
		},
		"type": "donut",
		"colors": CHART_COLORS,
	}
