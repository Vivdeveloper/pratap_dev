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
	from pratap_dev.pratap_dashboard.utils.period_filters import apply_period_filters

	if filters.get("date_based_on") not in DATE_FIELDS:
		frappe.throw(_("Please select a valid Date Based On value."))
	apply_period_filters(filters, require_limit=True)



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
	ItemMaster = frappe.qb.DocType("Item")
	date_field = TSA[DATE_FIELDS[filters.date_based_on]]
	request_count = Count(TSA.name).distinct()
	total_qty = Sum(Item.total_qty)
	total_amount = Sum(Item.amount)

	query = (
		frappe.qb.from_(TSA)
		.inner_join(Item)
		.on((Item.parent == TSA.name) & (Item.parenttype == "TSA Request"))
		.left_join(ItemMaster)
		.on(ItemMaster.name == Item.item_code)
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
	from frappe.query_builder import Criterion

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
	if filters.get("customer"):
		query = query.where(Criterion.any([TSA.customer_id == filters.customer, TSA.stock_customer_id == filters.customer]))
	if filters.get("customer_group"):
		query = query.where(
			Criterion.any([TSA.customer_group == filters.customer_group, TSA.stock_customer_group == filters.customer_group])
		)
	if filters.get("territory"):
		query = query.where(Criterion.any([TSA.territory == filters.territory, TSA.stock_territory == filters.territory]))
	if filters.get("region"):
		query = query.where(Criterion.any([TSA.region == filters.region, TSA.stock_region == filters.region]))
	for fname, field in {
		"custom_erp": ItemMaster.custom_erp,
		"custom_category_type": ItemMaster.custom_category_type,
		"custom_material_base": ItemMaster.custom_material_base,
		"custom_product_type": ItemMaster.custom_product_type,
		"custom_product_category": ItemMaster.custom_product_category,
	}.items():
		if filters.get(fname):
			query = query.where(field == filters[fname])

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
