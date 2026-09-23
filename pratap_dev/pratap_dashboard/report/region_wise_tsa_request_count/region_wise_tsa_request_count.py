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
	from pratap_dev.pratap_dashboard.utils.period_filters import apply_period_filters

	if filters.get("date_based_on") not in DATE_FIELDS:
		frappe.throw(_("Please select a valid Date Based On value."))
	apply_period_filters(filters, require_limit=True)



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
	from pratap_dev.pratap_dashboard.utils.item_filters import get_parents_for_item_filters

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

	or_filters = []
	if filters.get("customer"):
		or_filters = [["customer_id", "=", filters.customer], ["stock_customer_id", "=", filters.customer]]
	if filters.get("customer_group"):
		or_filters = [["customer_group", "=", filters.customer_group], ["stock_customer_group", "=", filters.customer_group]]
	if filters.get("territory"):
		or_filters = [["territory", "=", filters.territory], ["stock_territory", "=", filters.territory]]
	if filters.get("region"):
		or_filters = [["region", "=", filters.region], ["stock_region", "=", filters.region]]

	matching = get_parents_for_item_filters(
		filters, child_doctype="TSA Item", parenttype="TSA Request", item_link_field="item_code"
	)
	if matching is not None:
		if not matching:
			return []
		request_filters["name"] = ["in", matching]

	rows = frappe.get_all(
		"TSA Request",
		filters=request_filters,
		or_filters=or_filters or None,
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
