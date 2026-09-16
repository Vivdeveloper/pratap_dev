# Copyright (c) 2026, saurabh@exacuer.com and contributors
# For license information, please see license.txt

import frappe
from erpnext.accounts.utils import get_fiscal_year
from frappe import _
from frappe.query_builder.functions import Count, Sum
from frappe.utils import (
	add_days,
	add_months,
	cint,
	flt,
	get_first_day,
	get_first_day_of_week,
	get_last_day,
	get_last_day_of_week,
	getdate,
	nowdate,
)


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
	if filters.get("date_based_on") not in DATE_FIELDS:
		frappe.throw(_("Please select a valid Date Based On value."))

	period_type = filters.get("period_type") or "Financial Year"
	if period_type not in ("Financial Year", "Monthly", "Weekly"):
		frappe.throw(_("Please select a valid Period Type."))
	filters.period_type = period_type

	if not filters.get("fiscal_year"):
		filters.fiscal_year = get_fiscal_year(nowdate())[0]

	from_date, to_date = get_period_dates(filters)
	filters.from_date = from_date
	filters.to_date = to_date

	limit = cint(filters.get("limit") or 10)
	if limit < 1:
		frappe.throw(_("Limit must be at least 1."))
	filters.limit = limit


def get_month_number(month):
	months = {
		"January": 1,
		"February": 2,
		"March": 3,
		"April": 4,
		"May": 5,
		"June": 6,
		"July": 7,
		"August": 8,
		"September": 9,
		"October": 10,
		"November": 11,
		"December": 12,
	}
	if month in months:
		return months[month]
	return cint(month) or getdate().month


def get_period_dates(filters):
	fiscal_year = get_fiscal_year(fiscal_year=filters.fiscal_year, as_dict=True)
	year_start = getdate(fiscal_year.year_start_date)
	year_end = getdate(fiscal_year.year_end_date)

	if filters.period_type == "Monthly":
		month = get_month_number(filters.get("month"))
		current = get_first_day(year_start)
		matched = None
		while current <= year_end:
			if current.month == month:
				matched = current
				break
			current = add_months(current, 1)
		if not matched:
			frappe.throw(_("Selected month is not in Fiscal Year {0}.").format(filters.fiscal_year))
		return matched, get_last_day(matched)

	if filters.period_type == "Weekly":
		week_date = getdate(filters.get("week_date") or nowdate())
		from_date = get_first_day_of_week(week_date)
		to_date = get_last_day_of_week(week_date)
		if from_date < year_start:
			from_date = year_start
		if to_date > year_end:
			to_date = year_end
		if from_date > to_date:
			frappe.throw(_("Selected week is not in Fiscal Year {0}.").format(filters.fiscal_year))
		return from_date, to_date

	return year_start, year_end


def get_columns():
	return [
		{
			"fieldname": "rank",
			"label": _("Rank"),
			"fieldtype": "Int",
			"width": 80,
		},
		{
			"fieldname": "customer",
			"label": _("Customer"),
			"fieldtype": "Dynamic Link",
			"options": "opportunity_from",
			"width": 200,
		},
		{
			"fieldname": "opportunity_from",
			"label": _("Opportunity From"),
			"fieldtype": "Link",
			"options": "DocType",
			"width": 140,
		},
		{
			"fieldname": "customer_name",
			"label": _("Customer Name"),
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
			"fieldname": "total_qty",
			"label": _("Total Qty"),
			"fieldtype": "Float",
			"width": 140,
		},
	]


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


def get_data(filters):
	Opportunity = frappe.qb.DocType("Opportunity")
	date_field = Opportunity[DATE_FIELDS[filters.date_based_on]]
	opportunity_count = Count(Opportunity.name)
	total_amount = Sum(Opportunity.total)

	query = (
		frappe.qb.from_(Opportunity)
		.select(
			Opportunity.party_name.as_("customer"),
			Opportunity.opportunity_from,
			Opportunity.customer_name,
			opportunity_count.as_("opportunity_count"),
			total_amount.as_("total_amount"),
		)
		.where(date_field >= filters.from_date)
		.where(date_field < add_days(filters.to_date, 1))
		.groupby(Opportunity.party_name, Opportunity.opportunity_from, Opportunity.customer_name)
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
	qty_map = get_total_qty_map(filters, matching_opportunities)
	data = []
	for index, row in enumerate(rows, start=1):
		count = cint(row.opportunity_count)
		amount = flt(row.total_amount)
		key = (row.customer, row.opportunity_from, row.customer_name)
		data.append(
			{
				"rank": index,
				"customer": row.customer,
				"opportunity_from": row.opportunity_from,
				"customer_name": row.customer_name or row.customer or _("Not Set"),
				"opportunity_count": count,
				"total_amount": round(amount, 2),
				"total_qty": flt(qty_map.get(key)),
			}
		)

	return data


def get_total_qty_map(filters, matching_opportunities):
	Opportunity = frappe.qb.DocType("Opportunity")
	ItemRow = frappe.qb.DocType("Opportunity CRM Item")
	date_field = Opportunity[DATE_FIELDS[filters.date_based_on]]

	query = (
		frappe.qb.from_(Opportunity)
		.inner_join(ItemRow)
		.on((ItemRow.parent == Opportunity.name) & (ItemRow.parenttype == "Opportunity"))
		.select(
			Opportunity.party_name.as_("customer"),
			Opportunity.opportunity_from,
			Opportunity.customer_name,
			Sum(ItemRow.total_qty).as_("total_qty"),
		)
		.where(date_field >= filters.from_date)
		.where(date_field < add_days(filters.to_date, 1))
		.groupby(Opportunity.party_name, Opportunity.opportunity_from, Opportunity.customer_name)
	)
	query = apply_optional_filters(query, Opportunity, filters)
	if matching_opportunities is not None:
		if not matching_opportunities:
			return {}
		query = query.where(Opportunity.name.isin(matching_opportunities))

	return {
		(row.customer, row.opportunity_from, row.customer_name): flt(row.total_qty)
		for row in query.run(as_dict=True)
	}


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
			"labels": [row["customer_name"] for row in data],
			"datasets": [
				{
					"name": _("Opportunities"),
					"values": [row["opportunity_count"] for row in data],
					"chartType": "bar",
				},
				{
					"name": _("Total Qty"),
					"values": [row["total_qty"] for row in data],
					"chartType": "line",
				},
			],
		},
		"type": "axis-mixed",
		"colors": ["#5e64ff", "#28a745"],
	}
