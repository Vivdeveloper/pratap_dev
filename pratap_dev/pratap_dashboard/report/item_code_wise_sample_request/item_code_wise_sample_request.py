# Copyright (c) 2026, saurabh@exacuer.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder.functions import Count, Sum
from frappe.utils import add_days, cint, flt, getdate


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
			"fieldname": "item_code",
			"label": _("Item Code"),
			"fieldtype": "Link",
			"options": "Item",
			"width": 220,
		},
		{
			"fieldname": "item_name",
			"label": _("Item Name"),
			"fieldtype": "Data",
			"width": 220,
		},
		{
			"fieldname": "request_count",
			"label": _("Sample Requests"),
			"fieldtype": "Int",
			"width": 140,
		},
		{
			"fieldname": "total_qty",
			"label": _("Total Quantity"),
			"fieldtype": "Float",
			"width": 140,
		},
		{
			"fieldname": "total_amount",
			"label": _("Total Amount"),
			"fieldtype": "Currency",
			"width": 160,
		},
	]


def get_data(filters):
	SampleRequest = frappe.qb.DocType("Sample Request")
	Item = frappe.qb.DocType("Sample CRM Item")
	date_field = SampleRequest[DATE_FIELDS[filters.date_based_on]]
	request_count = Count(SampleRequest.name).distinct()
	total_qty = Sum(Item.total_qty)
	total_amount = Sum(Item.amount)

	query = (
		frappe.qb.from_(SampleRequest)
		.inner_join(Item)
		.on(
			(Item.parent == SampleRequest.name)
			& (Item.parenttype == "Sample Request")
			& (Item.parentfield == "sample_crm_item")
		)
		.select(
			Item.item_code.as_("item_code"),
			Item.item_name.as_("item_name"),
			request_count.as_("request_count"),
			total_qty.as_("total_qty"),
			total_amount.as_("total_amount"),
		)
		.where(date_field >= filters.from_date)
		.where(date_field < add_days(filters.to_date, 1))
		.where(Item.item_code.isnotnull())
		.where(Item.item_code != "")
		.groupby(Item.item_code, Item.item_name)
		.orderby(total_amount, order=frappe.qb.desc)
	)
	query = apply_optional_filters(query, SampleRequest, Item, filters)

	rows = query.run(as_dict=True)

	data = []
	for row in rows:
		qty = flt(row.total_qty)
		amount = flt(row.total_amount)
		if not qty and not amount:
			continue
		data.append(
			{
				"item_code": row.item_code,
				"item_name": row.item_name or row.item_code,
				"request_count": cint(row.request_count),
				"total_qty": round(qty, 2),
				"total_amount": round(amount, 2),
			}
		)
		if len(data) >= filters.limit:
			break

	return data


def apply_optional_filters(query, SampleRequest, Item, filters):
	field_map = {
		"customer": SampleRequest.customer_id,
		"customer_group": SampleRequest.customer_group,
		"sample_type": SampleRequest.sample_type,
		"approval_status": SampleRequest.approval_status,
		"region": SampleRequest.region,
		"territory": SampleRequest.territory,
		"city": SampleRequest.city,
		"creator": SampleRequest.creator,
		"item_code": Item.item_code,
	}
	for filter_name, field in field_map.items():
		if filters.get(filter_name):
			query = query.where(field == filters[filter_name])

	return query


def get_chart(data):
	return {
		"data": {
			"labels": [row["item_code"] for row in data],
			"datasets": [
				{
					"name": _("Total Quantity"),
					"values": [row["total_qty"] for row in data],
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
		"colors": ["#4463F0", "#ECAD4B"],
	}
