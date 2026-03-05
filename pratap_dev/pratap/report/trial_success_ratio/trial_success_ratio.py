# Copyright (c) 2026, saurabh@exacuer.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	"""Columns for Trial Success Ratio: product trial success and conversion to order."""
	return [
		{
			"label": _("Trial ID"),
			"fieldname": "trial_id",
			"fieldtype": "Link",
			"options": "Product Trial",
			"width": 140,
		},
		{"label": _("Customer Name"), "fieldname": "customer_name", "fieldtype": "Data", "width": 160},
		{"label": _("Product"), "fieldname": "product", "fieldtype": "Data", "width": 180},
		{"label": _("Trial Quantity"), "fieldname": "trial_quantity", "fieldtype": "Float", "width": 110},
		{"label": _("Trial Date"), "fieldname": "trial_date", "fieldtype": "Date", "width": 100},
		{"label": _("Trial Result"), "fieldname": "trial_result", "fieldtype": "Data", "width": 100},
		{
			"label": _("Sales Person"),
			"fieldname": "sales_person",
			"fieldtype": "Link",
			"options": "User",
			"width": 120,
		},
		{"label": _("Converted to Order"), "fieldname": "converted_to_order", "fieldtype": "Data", "width": 120},
	]


def get_data(filters):
	"""Build rows from Product Trial; derive Sales Person from Opportunity and Converted to Order from Quotation->SO."""
	if not frappe.db.table_exists("Product Trial"):
		return []

	meta = frappe.get_meta("Product Trial")
	has_trial_date = meta.has_field("trial_date")
	has_sales_person = meta.has_field("sales_person")

	# 1) All Product Trials (optionally filtered by date)
	pt_filters = {}
	if filters.get("from_date") and filters.get("to_date"):
		pt_filters["creation"] = ["between", [filters["from_date"], filters["to_date"]]]
	if filters.get("trial_status"):
		pt_filters["trial_status"] = filters["trial_status"]
	if filters.get("company") and meta.has_field("company"):
		pt_filters["company"] = filters["company"]

	fields = [
		"name", "trial_id", "customer_name", "trial_quantity", "trial_status",
		"enquiry_opportunity", "creation", "modified",
	]
	if has_trial_date:
		fields.append("trial_date")
	if has_sales_person:
		fields.append("sales_person")

	trials = frappe.get_all(
		"Product Trial",
		filters=pt_filters,
		fields=fields,
		order_by="creation desc",
	)

	if not trials:
		return []

	pt_names = [t["name"] for t in trials]
	opportunity_names = list({t.get("enquiry_opportunity") for t in trials if t.get("enquiry_opportunity")})

	# 2) Product from product_table (first item)
	product_by_pt = {}
	if frappe.db.table_exists("Quotation Item"):  # Product Trial product_table may use Quotation Item as child
		# Try child table name from Product Trial - could be product_table with parenttype Product Trial
		for pt_name in pt_names:
			items = frappe.get_all(
				"Quotation Item",
				filters={"parent": pt_name, "parenttype": "Product Trial"},
				fields=["item_code", "item_name"],
				limit=1,
			)
			if items:
				product_by_pt[pt_name] = items[0].get("item_name") or items[0].get("item_code") or ""
			else:
				product_by_pt[pt_name] = ""
	else:
		product_by_pt = {n: "" for n in pt_names}

	# 3) Sales Person: from Product Trial if field exists, else from Opportunity (opportunity_owner)
	sales_person_by_pt = {}
	if has_sales_person:
		for t in trials:
			sales_person_by_pt[t["name"]] = t.get("sales_person") or ""
	else:
		sales_person_by_opp = {}
		if opportunity_names:
			for opp in frappe.get_all(
				"Opportunity",
				filters={"name": ["in", opportunity_names]},
				fields=["name", "opportunity_owner"],
			):
				sales_person_by_opp[opp["name"]] = opp.get("opportunity_owner") or ""
		for t in trials:
			opp = t.get("enquiry_opportunity")
			sales_person_by_pt[t["name"]] = sales_person_by_opp.get(opp, "") if opp else ""

	# 4) Converted to Order: Quotation with opportunity in (enquiry_opportunity) -> has Sales Order?
	converted_opps = set()
	if opportunity_names:
		quotations = frappe.get_all(
			"Quotation",
			filters={"opportunity": ["in", opportunity_names]},
			fields=["name"],
		)
		qtn_names = [q["name"] for q in quotations]
		if qtn_names:
			so_items = frappe.get_all(
				"Sales Order Item",
				filters={"prevdoc_docname": ["in", qtn_names]},
				fields=["prevdoc_docname"],
			)
			# Quotations that were converted to SO
			converted_qtn = {r["prevdoc_docname"] for r in so_items if r.get("prevdoc_docname")}
			# Which opportunities have at least one converted quotation?
			for q in quotations:
				if q["name"] in converted_qtn:
					opp = frappe.db.get_value("Quotation", q["name"], "opportunity")
					if opp:
						converted_opps.add(opp)

	# 5) Build rows
	rows = []
	for t in trials:
		trial_date = t.get("trial_date") if has_trial_date else (t.get("creation") or t.get("modified"))

		trial_result = (t.get("trial_status") or "").strip() or "—"
		if trial_result and trial_result.lower() in ("success", "successful"):
			trial_result = "Success"
		elif trial_result and trial_result.lower() in ("fail", "failed", "failure"):
			trial_result = "Fail"

		opp = t.get("enquiry_opportunity")
		rows.append({
			"trial_id": t["name"],
			"customer_name": t.get("customer_name") or "—",
			"product": product_by_pt.get(t["name"]) or "—",
			"trial_quantity": t.get("trial_quantity") or 0,
			"trial_date": trial_date,
			"trial_result": trial_result,
			"sales_person": sales_person_by_pt.get(t["name"]),  # from PT or from Opportunity
			"converted_to_order": "Yes" if opp and opp in converted_opps else "No",
		})

	return rows
