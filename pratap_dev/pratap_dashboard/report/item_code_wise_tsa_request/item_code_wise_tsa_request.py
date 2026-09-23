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
		{"fieldname": "item_code", "label": _("Item Code"), "fieldtype": "Link", "options": "Item", "width": 220},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 220},
		{"fieldname": "request_count", "label": _("TSA Requests"), "fieldtype": "Int", "width": 130},
		{"fieldname": "total_qty", "label": _("Total Quantity"), "fieldtype": "Float", "width": 140},
		{"fieldname": "total_amount", "label": _("Total Amount"), "fieldtype": "Currency", "width": 150},
	]


def get_data(filters):
	TSA = frappe.qb.DocType("TSA Request")
	Item = frappe.qb.DocType("TSA Item")
	date_field = TSA[DATE_FIELDS[filters.date_based_on]]
	request_count = Count(TSA.name).distinct()
	total_qty = Sum(Item.total_qty)
	total_amount = Sum(Item.amount)

	query = (
		frappe.qb.from_(TSA)
		.inner_join(Item)
		.on((Item.parent == TSA.name) & (Item.parenttype == "TSA Request"))
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
	if filters.get("tsa_request_type"):
		query = query.where(TSA.tsa_request_type == filters.tsa_request_type)
	if filters.get("workflow_state"):
		query = query.where(TSA.workflow_state == filters.workflow_state)
	if filters.get("creator"):
		query = query.where(TSA.creator_id == filters.creator)
	if filters.get("item_code"):
		query = query.where(Item.item_code == filters.item_code)
	if filters.get("courier_details"):
		query = query.where(TSA.courier_details == filters.courier_details)

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


def get_chart(data):
	return {
		"data": {
			"labels": [row["item_code"] for row in data],
			"datasets": [
				{"name": _("Total Quantity"), "values": [row["total_qty"] for row in data], "chartType": "bar"},
				{"name": _("Total Amount"), "values": [row["total_amount"] for row in data], "chartType": "line"},
			],
		},
		"type": "axis-mixed",
		"colors": ["#4463F0", "#ECAD4B"],
	}
