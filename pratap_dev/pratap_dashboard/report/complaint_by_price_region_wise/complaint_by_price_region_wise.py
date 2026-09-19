# Copyright (c) 2026, saurabh@exacuer.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder.functions import Count, Sum
from frappe.utils import add_days, cint, flt, getdate


DATE_FIELDS = {
	"Created Date": "posting_date",
	"Closure Date": "closure_date",
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
			"fieldname": "region",
			"label": _("Region"),
			"fieldtype": "Data",
			"width": 200,
		},
		{
			"fieldname": "complaint_count",
			"label": _("Complaints"),
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
		{
			"fieldname": "average_amount",
			"label": _("Average Amount"),
			"fieldtype": "Currency",
			"width": 150,
		},
	]


def get_data(filters):
	Complaint = frappe.qb.DocType("Complaint")
	Item = frappe.qb.DocType("Complaint CRM Item")
	ItemMaster = frappe.qb.DocType("Item")
	date_field = Complaint[DATE_FIELDS[filters.date_based_on]]
	complaint_count = Count(Complaint.name).distinct()
	total_qty = Sum(Item.qty)
	total_amount = Sum(Item.amount)

	query = (
		frappe.qb.from_(Complaint)
		.inner_join(Item)
		.on((Item.parent == Complaint.name) & (Item.parenttype == "Complaint"))
		.left_join(ItemMaster)
		.on(ItemMaster.name == Item.custom_packing_material)
		.select(
			Complaint.region.as_("region"),
			complaint_count.as_("complaint_count"),
			total_qty.as_("total_qty"),
			total_amount.as_("total_amount"),
		)
		.where(date_field >= filters.from_date)
		.where(date_field < add_days(filters.to_date, 1))
		.groupby(Complaint.region)
		.orderby(total_amount, order=frappe.qb.desc)
	)
	query = apply_optional_filters(query, Complaint, Item, ItemMaster, filters)

	rows = query.run(as_dict=True)
	grand_amount = sum(flt(row.total_amount) for row in rows)

	data = []
	for row in rows:
		amount = flt(row.total_amount)
		count = cint(row.complaint_count)
		if not amount:
			continue
		data.append(
			{
				"region": row.region or _("Not Set"),
				"complaint_count": count,
				"percentage": (amount / grand_amount * 100) if grand_amount else 0,
				"total_qty": flt(row.total_qty),
				"total_amount": round(amount, 2),
				"average_amount": round(amount / count if count else 0, 2),
			}
		)
		if len(data) >= filters.limit:
			break

	return data


def apply_optional_filters(query, Complaint, Item, ItemMaster, filters):
	field_map = {
		"status": Complaint.status,
		"closed_type": Complaint.closed_type,
		"customer": Complaint.customer_id,
		"customer_group": Complaint.customer_group,
		"enquiry_opportunity": Complaint.enquiry_opportunity,
		"product_trial": Complaint.product_trial,
		"risk_level": Complaint.risk_level,
		"region": Complaint.region,
		"territory": Complaint.territory,
		"city": Complaint.city,
		"created_by": Complaint.creator,
		"workflow_state": Complaint.workflow_state,
		"item_code": Item.custom_packing_material,
		"packing_material": Item.item_code,
		"item_group": Item.item_group,
		"brand": Item.brand,
		"custom_year": ItemMaster.custom_year,
		"custom_erp": ItemMaster.custom_erp,
		"custom_category_type": ItemMaster.custom_category_type,
		"custom_material_base": ItemMaster.custom_material_base,
		"custom_product_type": ItemMaster.custom_product_type,
		"custom_product_category": ItemMaster.custom_product_category,
	}
	for filter_name, field in field_map.items():
		if filters.get(filter_name):
			query = query.where(field == filters[filter_name])

	return query


def get_chart(data):
	return {
		"data": {
			"labels": [row["region"] for row in data],
			"datasets": [
				{
					"name": _("Total Amount"),
					"values": [row["total_amount"] for row in data],
					"chartType": "bar",
				},
				{
					"name": _("Complaints"),
					"values": [row["complaint_count"] for row in data],
					"chartType": "line",
				},
			],
		},
		"type": "axis-mixed",
		"colors": ["#28a745", "#5e64ff"],
	}
