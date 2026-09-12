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
			"fieldname": "item_code",
			"label": _("Item Code"),
			"fieldtype": "Link",
			"options": "Item",
			"width": 160,
		},
		{
			"fieldname": "item_name",
			"label": _("Item Name"),
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
			"fieldname": "total_qty",
			"label": _("Total Qty"),
			"fieldtype": "Float",
			"width": 120,
		},
		{
			"fieldname": "total_amount",
			"label": _("Total Amount"),
			"fieldtype": "Currency",
			"width": 160,
		},
	]


def get_data(filters):
	Opportunity = frappe.qb.DocType("Opportunity")
	Item = frappe.qb.DocType("Opportunity CRM Item")
	date_field = Opportunity[DATE_FIELDS[filters.date_based_on]]
	opportunity_count = Count(Opportunity.name).distinct()
	total_qty = Sum(Item.qty)
	total_amount = Sum(Item.amount)

	query = (
		frappe.qb.from_(Opportunity)
		.inner_join(Item)
		.on((Item.parent == Opportunity.name) & (Item.parenttype == "Opportunity"))
		.select(
			Item.custom_packing_material.as_("item_code"),
			Item.custom_item_name_fg.as_("item_name"),
			opportunity_count.as_("opportunity_count"),
			total_qty.as_("total_qty"),
			total_amount.as_("total_amount"),
		)
		.where(date_field >= filters.from_date)
		.where(date_field < add_days(filters.to_date, 1))
		.where(Item.custom_packing_material.isnotnull())
		.where(Item.custom_packing_material != "")
		.groupby(Item.custom_packing_material, Item.custom_item_name_fg)
		.orderby(opportunity_count, order=frappe.qb.desc)
		.orderby(total_amount, order=frappe.qb.desc)
		.limit(filters.limit)
	)
	query = apply_optional_filters(query, Opportunity, Item, filters)

	rows = query.run(as_dict=True)
	data = []
	for index, row in enumerate(rows, start=1):
		count = cint(row.opportunity_count)
		if not count:
			continue
		data.append(
			{
				"rank": index,
				"item_code": row.item_code,
				"item_name": row.item_name or row.item_code,
				"opportunity_count": count,
				"total_qty": flt(row.total_qty),
				"total_amount": round(flt(row.total_amount), 2),
			}
		)

	return data


def apply_optional_filters(query, Opportunity, Item, filters):
	field_map = {
		"company": Opportunity.company,
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
		"item_code": Item.custom_packing_material,
		"item_group": Item.item_group,
		"brand": Item.brand,
	}
	for filter_name, field in field_map.items():
		if filters.get(filter_name):
			query = query.where(field == filters[filter_name])

	return query


def get_chart(data):
	return {
		"data": {
			"labels": [row["item_name"] for row in data],
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
