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
	columns = get_columns()
	data = get_data(filters)
	return columns, data, None, get_chart(data)


def validate_filters(filters):
	from pratap_dev.pratap_dashboard.utils.period_filters import apply_period_filters

	if filters.get("date_based_on") not in DATE_FIELDS:
		frappe.throw(_("Please select a valid Date Based On value."))
	apply_period_filters(filters, require_limit=True)



def get_columns():
	return [
		{"fieldname": "tsa_request_type", "label": _("Request Type"), "fieldtype": "Data", "width": 160},
		{"fieldname": "request_count", "label": _("TSA Requests"), "fieldtype": "Int", "width": 140},
		{"fieldname": "percentage", "label": _("Percentage"), "fieldtype": "Percent", "precision": 2, "width": 120},
	]


def get_data(filters):
	TSA = frappe.qb.DocType("TSA Request")
	date_field = TSA[DATE_FIELDS[filters.date_based_on]]
	request_count = Count(TSA.name)
	query = (
		frappe.qb.from_(TSA)
		.select(TSA.tsa_request_type.as_("tsa_request_type"), request_count.as_("request_count"))
		.where(date_field >= filters.from_date)
		.where(date_field < add_days(filters.to_date, 1))
		.groupby(TSA.tsa_request_type)
		.orderby(request_count, order=frappe.qb.desc)
	)
	query = apply_optional_filters(query, TSA, filters)
	rows = query.run(as_dict=True)
	grand_total = sum(cint(r.request_count) for r in rows)
	data = []
	for row in rows:
		count = cint(row.request_count)
		if not count:
			continue
		data.append(
			{
				"tsa_request_type": row.tsa_request_type or _("Not Set"),
				"request_count": count,
				"percentage": (count / grand_total * 100) if grand_total else 0,
			}
		)
		if len(data) >= filters.limit:
			break
	return data



def apply_optional_filters(query, TSA, filters):
	from frappe.query_builder import Criterion

	field_map = {
		"tsa_request_type": TSA.tsa_request_type,
		"workflow_state": TSA.workflow_state,
		"creator": TSA.creator_id,
		"courier_details": TSA.courier_details,
	}
	for name, field in field_map.items():
		if filters.get(name):
			query = query.where(field == filters[name])

	if filters.get("customer"):
		query = query.where(
			Criterion.any([TSA.customer_id == filters.customer, TSA.stock_customer_id == filters.customer])
		)
	if filters.get("customer_group"):
		query = query.where(
			Criterion.any(
				[TSA.customer_group == filters.customer_group, TSA.stock_customer_group == filters.customer_group]
			)
		)
	if filters.get("territory"):
		query = query.where(
			Criterion.any([TSA.territory == filters.territory, TSA.stock_territory == filters.territory])
		)
	if filters.get("region"):
		query = query.where(Criterion.any([TSA.region == filters.region, TSA.stock_region == filters.region]))

	matching = None
	from pratap_dev.pratap_dashboard.utils.item_filters import get_parents_for_item_filters

	matching = get_parents_for_item_filters(
		filters,
		child_doctype="TSA Item",
		parenttype="TSA Request",
		item_link_field="item_code",
	)
	if matching is not None:
		if not matching:
			return query.where(TSA.name == "__no_match__")
		query = query.where(TSA.name.isin(matching))
	return query



def get_chart(data):
	return {
		"data": {
			"labels": [row["tsa_request_type"] for row in data],
			"datasets": [{"name": _("TSA Requests"), "values": [row["request_count"] for row in data]}],
		},
		"type": "donut",
		"colors": CHART_COLORS,
	}
