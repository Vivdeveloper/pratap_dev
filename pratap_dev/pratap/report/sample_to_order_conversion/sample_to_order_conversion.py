# Copyright (c) 2026, saurabh@exacuer.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	"""Columns for Sample to Order Conversion: samples that led to orders."""
	return [
		{
			"label": _("Sample Request ID"),
			"fieldname": "sample_request_id",
			"fieldtype": "Link",
			"options": "Sample Request",
			"width": 150,
		},
		{"label": _("Customer Name"), "fieldname": "customer_name", "fieldtype": "Data", "width": 160},
		{"label": _("Product"), "fieldname": "product", "fieldtype": "Data", "width": 180},
		{"label": _("Sample Quantity"), "fieldname": "sample_quantity", "fieldtype": "Float", "width": 120},
		{"label": _("Sample Date"), "fieldname": "sample_date", "fieldtype": "Date", "width": 110},
		{
			"label": _("Sales Order ID"),
			"fieldname": "sales_order_id",
			"fieldtype": "Link",
			"options": "Sales Order",
			"width": 140,
		},
		{"label": _("Order Quantity"), "fieldname": "order_quantity", "fieldtype": "Float", "width": 120},
		{"label": _("Conversion Status"), "fieldname": "conversion_status", "fieldtype": "Data", "width": 130},
	]


def get_data(filters):
	"""Build rows from Sample Request; link to Sales Order via Opportunity (sample_request_id) -> Quotation -> SO."""
	if not frappe.db.table_exists("Sample Request"):
		return []

	meta = frappe.get_meta("Sample Request")
	has_company = meta.has_field("company")
	has_sales_order = meta.has_field("sales_order") or meta.has_field("linked_sales_order")
	so_field = None
	if has_sales_order:
		so_field = "sales_order" if meta.has_field("sales_order") else "linked_sales_order"

	# 1) All Sample Requests (optionally filtered)
	sr_filters = {}
	if filters.get("from_date") and filters.get("to_date"):
		if meta.has_field("dispatch_date"):
			sr_filters["dispatch_date"] = ["between", [filters["from_date"], filters["to_date"]]]
		else:
			sr_filters["creation"] = ["between", [filters["from_date"], filters["to_date"]]]
	if filters.get("company") and has_company:
		sr_filters["company"] = filters["company"]

	fields = ["name", "sample_request_id", "customer_name", "customer_management", "dispatch_date", "creation"]
	if so_field:
		fields.append(so_field)

	requests = frappe.get_all(
		"Sample Request",
		filters=sr_filters,
		fields=fields,
		order_by="dispatch_date desc" if meta.has_field("dispatch_date") else "creation desc",
	)
	if not requests:
		return []

	sr_names = [r["name"] for r in requests]

	# 2) Product and Sample Quantity from product_table (Quotation Item, parenttype=Sample Request)
	product_by_sr = {}
	qty_by_sr = {}
	for sr_name in sr_names:
		items = frappe.get_all(
			"Quotation Item",
			filters={"parent": sr_name, "parenttype": "Sample Request", "parentfield": "product_table"},
			fields=["item_code", "item_name", "qty", "stock_qty"],
		)
		if items:
			product_by_sr[sr_name] = items[0].get("item_name") or items[0].get("item_code") or ""
			qty_by_sr[sr_name] = sum(flt(i.get("stock_qty") or i.get("qty")) for i in items)
		else:
			product_by_sr[sr_name] = ""
			qty_by_sr[sr_name] = 0

	# 3) Linked Sales Order: direct field if present, else via sample_request_id (Opportunity) -> Quotation -> SO
	sr_to_so = {}
	if so_field:
		for r in requests:
			so_name = r.get(so_field)
			if so_name:
				sr_to_so[r["name"]] = so_name

	opportunity_ids = list({r.get("sample_request_id") for r in requests if r.get("sample_request_id")})
	if opportunity_ids:
		quotations = frappe.get_all(
			"Quotation",
			filters={"opportunity": ["in", opportunity_ids]},
			fields=["name", "opportunity"],
		)
		qtn_to_opp = {q["name"]: q["opportunity"] for q in quotations}
		qtn_names = list(qtn_to_opp.keys())
		if qtn_names:
			so_items = frappe.get_all(
				"Sales Order Item",
				filters={"prevdoc_docname": ["in", qtn_names]},
				fields=["parent", "prevdoc_docname"],
			)
			qtn_to_so = {}
			for row in so_items:
				q = row.get("prevdoc_docname")
				if q and q not in qtn_to_so:
					qtn_to_so[q] = row["parent"]
			for r in requests:
				if r["name"] in sr_to_so:
					continue
				opp = r.get("sample_request_id")
				if not opp:
					continue
				for qtn_name, qtn_opp in qtn_to_opp.items():
					if qtn_opp == opp and qtn_name in qtn_to_so:
						sr_to_so[r["name"]] = qtn_to_so[qtn_name]
						break

	# 4) Order quantity per SO
	so_names = list(sr_to_so.values())
	so_total_qty = {}
	if so_names:
		for so_name in so_names:
			items = frappe.get_all(
				"Sales Order Item",
				filters={"parent": so_name},
				fields=["qty", "stock_qty"],
			)
			so_total_qty[so_name] = sum(flt(i.get("stock_qty") or i.get("qty")) for i in items)

	# 5) Build rows
	rows = []
	for r in requests:
		sr_name = r["name"]
		so_name = sr_to_so.get(sr_name)
		sample_date = r.get("dispatch_date") or r.get("creation")
		customer = r.get("customer_name") or r.get("customer_management") or "—"
		conversion_status = "Converted" if so_name else "Not Converted"
		rows.append({
			"sample_request_id": sr_name,
			"customer_name": customer,
			"product": product_by_sr.get(sr_name) or "—",
			"sample_quantity": flt(qty_by_sr.get(sr_name)),
			"sample_date": sample_date,
			"sales_order_id": so_name or "",
			"order_quantity": flt(so_total_qty.get(so_name)) if so_name else None,
			"conversion_status": conversion_status,
		})

	if filters.get("conversion_status"):
		rows = [r for r in rows if r.get("conversion_status") == filters["conversion_status"]]
	return rows
