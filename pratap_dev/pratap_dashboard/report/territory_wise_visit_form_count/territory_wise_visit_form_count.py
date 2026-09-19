# Copyright (c) 2026, saurabh@exacuer.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder.functions import Count
from frappe.utils import add_days, cint, getdate


DATE_FIELDS = {
	"Visit Date": "posting_date",
	"Created Date": "created_date",
	"Document Creation": "creation",
}

CHECK_FILTERS = {
	"customer_visit": "customer_visit",
	"visit_for_office": "visit_for_office",
	"ptcpl_plant_visit": "ptcpl_plant_visit",
	"channel_partner_office": "channel_partner_office",
	"visit_again_required": "visit_again_required",
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
			"fieldname": "territory",
			"label": _("Territory"),
			"fieldtype": "Link",
			"options": "Territory",
			"width": 200,
		},
		{
			"fieldname": "visit_count",
			"label": _("Visits"),
			"fieldtype": "Int",
			"width": 130,
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
	Visit = frappe.qb.DocType("Visit Form")
	Customer = frappe.qb.DocType("Customer")
	date_field = Visit[DATE_FIELDS[filters.date_based_on]]
	visit_count = Count(Visit.name)

	query = (
		frappe.qb.from_(Visit)
		.left_join(Customer)
		.on(Customer.name == Visit.customer_id)
		.select(
			Customer.territory.as_("territory"),
			visit_count.as_("visit_count"),
		)
		.where(date_field >= filters.from_date)
		.where(date_field < add_days(filters.to_date, 1))
		.groupby(Customer.territory)
		.orderby(visit_count, order=frappe.qb.desc)
	)
	query = apply_optional_filters(query, Visit, Customer, filters)

	rows = query.run(as_dict=True)
	grand_total = sum(cint(row.visit_count) for row in rows)

	data = []
	for row in rows:
		count = cint(row.visit_count)
		if not count:
			continue
		data.append(
			{
				"territory": row.territory or _("Not Set"),
				"visit_count": count,
				"percentage": (count / grand_total * 100) if grand_total else 0,
			}
		)
		if len(data) >= filters.limit:
			break

	return data


def apply_optional_filters(query, Visit, Customer, filters):
	field_map = {
		"visit_type": Visit.visit_type,
		"workflow_state": Visit.workflow_state,
		"customer": Visit.customer_id,
		"customer_group": Visit.customer_group,
		"secondary_customer": Visit.secondary_customer,
		"creator_id": Visit.creator_id,
		"creator": Visit.creator,
		"visit_for_opportunity": Visit.visit_for_opportunity,
		"customer_feedbaack": Visit.customer_feedbaack,
		"document_type": Visit.document_type,
		"document_id": Visit.document_id,
		"region": Customer.custom_region,
		"territory": Customer.territory,
		"city": Customer.custom_city,
	}
	for filter_name, field in field_map.items():
		if filters.get(filter_name):
			query = query.where(field == filters[filter_name])

	for filter_name, fieldname in CHECK_FILTERS.items():
		value = filters.get(filter_name)
		if value == "Yes":
			query = query.where(Visit[fieldname] == 1)
		elif value == "No":
			query = query.where(Visit[fieldname] == 0)

	return query


def get_chart(data):
	return {
		"data": {
			"labels": [row["territory"] for row in data],
			"datasets": [
				{
					"name": _("Visits"),
					"values": [row["visit_count"] for row in data],
				}
			],
		},
		"type": "bar",
		"colors": ["#5e64ff"],
	}
