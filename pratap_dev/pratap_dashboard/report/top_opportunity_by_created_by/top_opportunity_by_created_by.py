# Copyright (c) 2026, saurabh@exacuer.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder.functions import Count, IfNull, Sum
from frappe.utils import add_days, cint, flt, getdate


DATE_FIELDS = {
	"Opportunity Date": "transaction_date",
	"Expected Closing Date": "expected_closing",
	"Document Creation": "creation",
}

ITEM_FILTERS = (
	"item_code",
	"custom_year",
	"custom_erp",
	"custom_category_type",
	"custom_material_base",
	"custom_product_type",
	"custom_product_category",
)


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
			"fieldname": "rank",
			"label": _("Rank"),
			"fieldtype": "Int",
			"width": 80,
		},
		{
			"fieldname": "created_by",
			"label": _("Created By"),
			"fieldtype": "Link",
			"options": "User",
			"width": 220,
		},
		{
			"fieldname": "full_name",
			"label": _("Full Name"),
			"fieldtype": "Data",
			"width": 220,
		},
		{
			"fieldname": "opportunity_count",
			"label": _("Opportunities"),
			"fieldtype": "Int",
			"width": 140,
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
	User = frappe.qb.DocType("User")
	date_field = Opportunity[DATE_FIELDS[filters.date_based_on]]
	opportunity_count = Count(Opportunity.name)
	total_amount = Sum(Opportunity.total)

	query = (
		frappe.qb.from_(Opportunity)
		.left_join(User)
		.on(User.name == Opportunity.owner)
		.select(
			Opportunity.owner.as_("created_by"),
			IfNull(User.full_name, Opportunity.owner).as_("full_name"),
			opportunity_count.as_("opportunity_count"),
			total_amount.as_("total_amount"),
		)
		.where(date_field >= filters.from_date)
		.where(date_field < add_days(filters.to_date, 1))
		.groupby(Opportunity.owner, User.full_name)
		.orderby(opportunity_count, order=frappe.qb.desc)
		.orderby(total_amount, order=frappe.qb.desc)
		.limit(filters.limit)
	)
	query = apply_optional_filters(query, Opportunity, filters)

	matching_opportunities = get_opportunities_for_item_filters(filters)
	if matching_opportunities is not None:
		if not matching_opportunities:
			return []
		query = query.where(Opportunity.name.isin(matching_opportunities))

	rows = query.run(as_dict=True)
	data = []
	for index, row in enumerate(rows, start=1):
		count = cint(row.opportunity_count)
		amount = flt(row.total_amount)
		data.append(
			{
				"rank": index,
				"created_by": row.created_by,
				"full_name": row.full_name or row.created_by or _("Not Set"),
				"opportunity_count": count,
				"total_amount": round(amount, 2),
				"average_amount": round(amount / count if count else 0, 2),
			}
		)

	return data


def get_opportunities_for_item_filters(filters):
	if not any(filters.get(field) for field in ITEM_FILTERS):
		return None

	ItemRow = frappe.qb.DocType("Opportunity CRM Item")
	Item = frappe.qb.DocType("Item")
	query = (
		frappe.qb.from_(ItemRow)
		.inner_join(Item)
		.on(Item.name == ItemRow.custom_packing_material)
		.select(ItemRow.parent)
		.distinct()
		.where(ItemRow.parenttype == "Opportunity")
	)
	item_field_map = {
		"item_code": Item.name,
		"custom_year": Item.custom_year,
		"custom_erp": Item.custom_erp,
		"custom_category_type": Item.custom_category_type,
		"custom_material_base": Item.custom_material_base,
		"custom_product_type": Item.custom_product_type,
		"custom_product_category": Item.custom_product_category,
	}
	for filter_name, field in item_field_map.items():
		if filters.get(filter_name):
			query = query.where(field == filters[filter_name])

	return query.run(pluck=True)


def apply_optional_filters(query, Opportunity, filters):
	field_map = {
		"company": Opportunity.company,
		"status": Opportunity.status,
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
			"labels": [row["full_name"] for row in data],
			"datasets": [
				{
					"name": _("Opportunities"),
					"values": [row["opportunity_count"] for row in data],
					"chartType": "bar",
				},
				{
					"name": _("Total Amount"),
					"values": [row["total_amount"] for row in data],
					"chartType": "line",
				},
			],
		},
		"type": "axis-mixed",
		"colors": ["#5e64ff", "#28a745"],
	}
