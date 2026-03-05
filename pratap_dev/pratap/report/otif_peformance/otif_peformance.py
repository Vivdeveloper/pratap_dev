# Copyright (c) 2026, saurabh@exacuer.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	"""Columns for OTIF Performance: On Time In Full delivery tracking."""
	return [
		{
			"label": _("Sales Order ID"),
			"fieldname": "sales_order_id",
			"fieldtype": "Link",
			"options": "Sales Order",
			"width": 140,
		},
		{"label": _("Customer Name"), "fieldname": "customer_name", "fieldtype": "Link", "options": "Customer", "width": 160},
		{"label": _("Order Date"), "fieldname": "order_date", "fieldtype": "Date", "width": 100},
		{"label": _("Required Delivery Date"), "fieldname": "required_delivery_date", "fieldtype": "Date", "width": 140},
		{"label": _("Dispatch Date"), "fieldname": "dispatch_date", "fieldtype": "Date", "width": 110},
		{"label": _("Delivery Quantity"), "fieldname": "delivery_quantity", "fieldtype": "Float", "width": 120},
		{"label": _("Ordered Quantity"), "fieldname": "ordered_quantity", "fieldtype": "Float", "width": 120},
		{"label": _("Delivery Status"), "fieldname": "delivery_status", "fieldtype": "Data", "width": 120},
		{"label": _("OTIF Status"), "fieldname": "otif_status", "fieldtype": "Data", "width": 100},
	]


def get_data(filters):
	"""Build OTIF rows from Sales Order and Delivery Note (dispatch date, delivered qty vs ordered)."""
	if not filters.get("company"):
		return []

	company = filters["company"]
	from_date = filters.get("from_date")
	to_date = filters.get("to_date")

	# 1) Sales Orders (submitted) in date range
	so_filters = {"company": company, "docstatus": 1}
	if from_date and to_date:
		so_filters["transaction_date"] = ["between", [from_date, to_date]]

	so_list = frappe.get_all(
		"Sales Order",
		filters=so_filters,
		fields=["name", "customer", "customer_name", "transaction_date", "delivery_date"],
		order_by="transaction_date desc",
	)
	if not so_list:
		return []

	so_names = [s["name"] for s in so_list]

	# 2) Ordered quantity per SO (from Sales Order Item)
	so_items = frappe.get_all(
		"Sales Order Item",
		filters={"parent": ["in", so_names]},
		fields=["parent", "qty", "stock_qty"],
	)
	ordered_qty = {}
	for row in so_items:
		key = row["parent"]
		qty = flt(row.get("stock_qty") or row.get("qty"))
		ordered_qty[key] = ordered_qty.get(key, 0) + qty

	# 3) Delivery Note items against these SOs -> delivery qty and dispatch date (DN posting_date)
	dn_items = frappe.get_all(
		"Delivery Note Item",
		filters={"against_sales_order": ["in", so_names]},
		fields=["parent", "against_sales_order", "qty", "stock_qty"],
	)
	# Get posting_date for each DN
	dn_names = list({d["parent"] for d in dn_items})
	dn_dates = {}
	if dn_names:
		for dn in frappe.get_all("Delivery Note", filters={"name": ["in", dn_names]}, fields=["name", "posting_date"]):
			dn_dates[dn["name"]] = dn.get("posting_date")

	delivery_qty = {}
	dispatch_date_by_so = {}
	for row in dn_items:
		so_name = row.get("against_sales_order")
		if not so_name:
			continue
		qty = flt(row.get("stock_qty") or row.get("qty"))
		delivery_qty[so_name] = delivery_qty.get(so_name, 0) + qty
		dn_date = dn_dates.get(row["parent"])
		if dn_date:
			current = dispatch_date_by_so.get(so_name)
			# Use latest delivery date as dispatch date
			if current is None or getdate(dn_date) > getdate(current):
				dispatch_date_by_so[so_name] = dn_date

	# 4) Build rows
	rows = []
	for so in so_list:
		so_name = so["name"]
		req_date = so.get("delivery_date") or so.get("transaction_date")
		ord_qty = flt(ordered_qty.get(so_name))
		del_qty = flt(delivery_qty.get(so_name))
		disp_date = dispatch_date_by_so.get(so_name)

		# Delivery Status: On Time if dispatch_date <= required_delivery_date, else Delayed (or Not Delivered)
		if disp_date and req_date:
			delivery_status = "On Time" if getdate(disp_date) <= getdate(req_date) else "Delayed"
		elif disp_date:
			delivery_status = "On Time"
		else:
			delivery_status = "Not Delivered"

		# OTIF: Yes if On Time and delivered qty >= ordered qty
		if delivery_status == "On Time" and del_qty >= ord_qty and ord_qty > 0:
			otif_status = "Yes"
		else:
			otif_status = "No"

		rows.append({
			"sales_order_id": so_name,
			"customer_name": so.get("customer_name") or so.get("customer"),
			"order_date": so.get("transaction_date"),
			"required_delivery_date": req_date,
			"dispatch_date": disp_date,
			"delivery_quantity": del_qty,
			"ordered_quantity": ord_qty,
			"delivery_status": delivery_status,
			"otif_status": otif_status,
		})

	# Optional filters
	if filters.get("delivery_status"):
		rows = [r for r in rows if r.get("delivery_status") == filters["delivery_status"]]
	if filters.get("otif_status"):
		rows = [r for r in rows if r.get("otif_status") == filters["otif_status"]]

	return rows
