# Copyright (c) 2026, saurabh@exacuer.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder.functions import Count, Sum
from frappe.utils import add_days, cint, flt, getdate


DATE_FIELDS = {
	"Opportunity Date": "transaction_date",
	"Expected Closing Date": "expected_closing",
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
			"fieldname": "opportunity_count",
			"label": _("Opportunities"),
			"fieldtype": "Int",
			"width": 140,
		},
		{
			"fieldname": "percentage",
			"label": _("Percentage"),
			"fieldtype": "Percent",
			"precision": 2,
			"width": 130,
		},
		{
			"fieldname": "total_amount",
			"label": _("Total Opportunity Amount"),
			"fieldtype": "Currency",
			"width": 200,
		},
		{
			"fieldname": "average_amount",
			"label": _("Average Amount"),
			"fieldtype": "Currency",
			"width": 160,
		},
	]


def get_data(filters):
	Opportunity = frappe.qb.DocType("Opportunity")
	date_field = Opportunity[DATE_FIELDS[filters.date_based_on]]
	opportunity_count = Count(Opportunity.name)
	total_amount = Sum(Opportunity.total)

	query = (
		frappe.qb.from_(Opportunity)
		.select(
			Opportunity.territory,
			opportunity_count.as_("opportunity_count"),
			total_amount.as_("total_amount"),
		)
		.where(date_field >= filters.from_date)
		.where(date_field < add_days(filters.to_date, 1))
		.groupby(Opportunity.territory)
		.orderby(opportunity_count, order=frappe.qb.desc)
	)
	query = apply_optional_filters(query, Opportunity, filters)

	rows = query.run(as_dict=True)
	total_opportunities = sum(cint(row.opportunity_count) for row in rows)

	data = []
	for row in rows:
		count = cint(row.opportunity_count)
		if not count:
			continue
		amount = flt(row.total_amount)
		data.append(
			{
				"territory": row.territory or _("Not Set"),
				"opportunity_count": count,
				"percentage": (count / total_opportunities * 100) if total_opportunities else 0,
				"total_amount": round(amount, 2),
				"average_amount": round(amount / count if count else 0, 2),
			}
		)

	return data


def apply_optional_filters(query, Opportunity, filters):
	field_map = {
		"company": Opportunity.company,
		"country": Opportunity.country,
		"custom_trial": Opportunity.custom_trial,
		"custom_select_field": Opportunity.custom_select_field,
		"opportunity_status": Opportunity.status,
		"opportunity_type": Opportunity.opportunity_type,
		"source": Opportunity.source,
		"sales_stage": Opportunity.sales_stage,
		"territory": Opportunity.territory,
		"customer_group": Opportunity.customer_group,
		"opportunity_owner": Opportunity.opportunity_owner,
		"created_by": Opportunity.owner,
		"industry": Opportunity.industry,
		"market_segment": Opportunity.market_segment,
		"campaign": Opportunity.campaign,
		"customer": Opportunity.party_name,
	}
	for filter_name, field in field_map.items():
		if filters.get(filter_name):
			query = query.where(field == filters[filter_name])

	return query


def get_chart(data):
	return {
		"data": {
			"labels": [row["territory"] for row in data],
			"datasets": [
				{
					"name": _("Opportunities"),
					"values": [row["opportunity_count"] for row in data],
				}
			],
		},
		"type": "bar",
		"colors": ["#5e64ff"],
	}
