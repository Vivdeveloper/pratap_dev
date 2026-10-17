# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Packing Material Requirement for a Work Order — mirrors the Forecast Club table.

For the WO's item to manufacture, list each packing option from the Item's "Packing
Material Details": the packed good (SF), its filling capacity and packing material, the
pack qty required for the WO, the packing material AVAILABLE in the WO's SOURCE warehouse,
the (editable) MR Qty, and the Material Request raised per week-of-month for this WO.

The operator enters an MR Qty per row and clicks "Create Packing Material Request": for any
row where the entered MR Qty exceeds the Available Qty in the source warehouse, the shortfall
is added to a SINGLE draft Material Request (Material Transfer) that brings the packing
material INTO the source warehouse. Rows already covered by source stock are skipped.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, get_first_day, get_last_day, getdate, today

from sales_forecast.sales_forecast.doctype.forecast_sales_person.forecast_sales_person import (
	_week_of_month,
)


def _forecast_club_qty_by_pack_size(fg, company):
	"""This month's Pack FG Forecast club for the FG item, keyed by pack size (filling
	capacity): the MONTH TOTAL = sum of the weekly forecast (fc_w1..fc_w4). Same source and
	numbers as the Pack FG Forecast popup. {filling_capacity: month_total_forecast}."""
	if not (fg and company):
		return {}

	from sales_forecast.sales_forecast.doctype.forecast_club.forecast_club import (
		get_pack_fg_clubbing,
	)

	start = str(get_first_day(today()))
	end = str(get_last_day(today()))
	try:
		club = get_pack_fg_clubbing(start, end, company)
	except Exception:
		frappe.log_error(title="WO packing forecast club failed", message=frappe.get_traceback())
		return {}

	out = {}
	for c in club or []:
		if c.get("item_code") != fg:
			continue
		fc = flt(c.get("filling_capacity"))
		out[fc] = (
			flt(c.get("fc_w1"))
			+ flt(c.get("fc_w2"))
			+ flt(c.get("fc_w3"))
			+ flt(c.get("fc_w4"))
		)
	return out


def _source_warehouse(wo):
	"""The WO's source warehouse used for 'Available Qty in Source'."""
	return (
		wo.get("custom_custom_source_warehouse")
		or wo.get("source_warehouse")
		or wo.get("wip_warehouse")
	)


def _stock_in_warehouse(item_code, warehouse):
	if not item_code or not warehouse:
		return 0.0
	return flt(
		frappe.db.get_value(
			"Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty"
		)
	)


def _weekly_inward_by_material(packing_materials, warehouse):
	"""Inward qty (actual_qty > 0) of each packing material INTO the warehouse, bucketed by
	week-of-month, for the current month — regardless of where it came from. Returns
	{packing_material: {1: qty, 2: qty, 3: qty, 4: qty}}."""
	result = {pm: {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0} for pm in packing_materials if pm}
	if not result or not warehouse:
		return result

	start = str(get_first_day(today()))
	end = str(get_last_day(today()))
	rows = frappe.db.sql(
		"""
		select sle.item_code, sle.actual_qty, sle.posting_date
		from `tabStock Ledger Entry` sle
		where sle.warehouse = %(wh)s
			and sle.item_code in %(items)s
			and sle.actual_qty > 0
			and sle.is_cancelled = 0
			and sle.posting_date between %(start)s and %(end)s
		""",
		{
			"wh": warehouse,
			"items": tuple(result.keys()),
			"start": start,
			"end": end,
		},
		as_dict=True,
	)
	for r in rows:
		if r.item_code not in result or not r.posting_date:
			continue
		wk = _week_of_month(getdate(r.posting_date).day)
		result[r.item_code][wk] += flt(r.actual_qty)
	return result


def _weekly_mr_by_material(work_order, packing_materials):
	"""Material Request qty per packing material, bucketed by week-of-month, for Material
	Requests linked to THIS Work Order (MR.work_order). Returns
	{packing_material: {1: qty, 2: qty, 3: qty, 4: qty}}."""
	result = {pm: {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0} for pm in packing_materials if pm}
	if not result:
		return result

	rows = frappe.db.sql(
		"""
		select mri.item_code, mri.qty, mr.transaction_date
		from `tabMaterial Request Item` mri
		join `tabMaterial Request` mr on mr.name = mri.parent
		where mr.work_order = %(wo)s
			and mr.docstatus < 2
			and mri.item_code in %(items)s
		""",
		{"wo": work_order, "items": tuple(result.keys())},
		as_dict=True,
	)
	for r in rows:
		if not r.transaction_date or r.item_code not in result:
			continue
		wk = _week_of_month(getdate(r.transaction_date).day)
		result[r.item_code][wk] += flt(r.qty)
	return result


@frappe.whitelist()
def get_wo_packing_requirement(work_order):
	"""Return the packing-material requirement rows for a Work Order."""
	wo = frappe.get_doc("Work Order", work_order)
	fg = wo.production_item
	qty = flt(wo.qty)
	source_warehouse = _source_warehouse(wo)

	# Qty (SF) comes from this month's Pack FG Forecast club per pack size (NOT WO qty / pack
	# size) — forecast packs are whole numbers, so no partial-pack fractions.
	club_qty = _forecast_club_qty_by_pack_size(fg, wo.company)

	details = frappe.get_all(
		"Packing Material Details",
		filters={"parent": fg, "parenttype": "Item"},
		fields=["packing_item_code", "packing_item_name", "filling_capacity", "item"],
		order_by="idx",
	)

	packing_materials = [d.packing_item_code for d in details if d.packing_item_code]
	weekly = _weekly_mr_by_material(work_order, packing_materials)
	# Weekly inward (received) qty of each packing material into the source warehouse.
	inward = _weekly_inward_by_material(packing_materials, source_warehouse)

	rows = []
	for d in details:
		fc = flt(d.filling_capacity)
		packing_material = d.packing_item_code  # the PK… packing material
		packed_good = d.item  # the sellable SF SKU
		# Qty (SF) = this month's forecast club (sum of weekly forecast) for this pack size.
		qty_sf = flt(club_qty.get(fc, 0.0))
		# Packing material available in the WO's source warehouse.
		source_qty = _stock_in_warehouse(packing_material, source_warehouse)
		# Default MR Qty (shortfall) — the operator may overwrite it in the UI.
		mr_qty = max(0.0, flt(qty_sf) - flt(source_qty))
		wk = weekly.get(packing_material) or {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
		iw = inward.get(packing_material) or {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
		rows.append(
			{
				"fg": fg,
				"packed_good": packed_good,
				"packed_good_name": frappe.db.get_value("Item", packed_good, "item_name")
				or packed_good
				if packed_good
				else "",
				"filling_capacity": fc,
				"packing_material": packing_material,
				"packing_material_name": d.packing_item_name or packing_material,
				"qty_sf": qty_sf,
				"source_qty": source_qty,
				"mr_qty": mr_qty,
				"mr_w1": flt(wk.get(1)),
				"mr_w2": flt(wk.get(2)),
				"mr_w3": flt(wk.get(3)),
				"mr_w4": flt(wk.get(4)),
				"in_w1": flt(iw.get(1)),
				"in_w2": flt(iw.get(2)),
				"in_w3": flt(iw.get(3)),
				"in_w4": flt(iw.get(4)),
			}
		)

	return {
		"fg": fg,
		"qty": qty,
		"source_warehouse": source_warehouse,
		"rows": rows,
	}


@frappe.whitelist()
def create_packing_material_request(work_order, rows):
	"""Create ONE draft Material Request (Material Transfer) for the packing-material shortfall.

	rows: [{packing_material, mr_qty}, ...] — the operator-entered MR Qty per row. For each row
	the shortfall = mr_qty - (available in source warehouse); rows with no shortfall are skipped.
	The draft transfers the shortfall INTO the WO's source warehouse (from-warehouse left blank
	for the user to pick). Returns {created: <MR name or None>, message}.
	"""
	if isinstance(rows, str):
		rows = json.loads(rows)

	wo = frappe.get_doc("Work Order", work_order)
	wo.check_permission("read")
	source_warehouse = _source_warehouse(wo)
	if not source_warehouse:
		frappe.throw(_("This Work Order has no source warehouse set."))

	# The MR Qty column already nets off the stock available in the source warehouse (its
	# default = Qty SF - Available). So request EXACTLY the MR Qty shown — do NOT subtract
	# the available stock again (that double-netting dropped covered rows). A row is "already
	# fulfilled" when its MR Qty is 0 (or the user cleared it) -> nothing to request.
	short_items = []
	for row in rows or []:
		pm = row.get("packing_material")
		want = flt(row.get("mr_qty"), 3)
		if not pm or want <= 0:
			continue
		short_items.append({"item_code": pm, "qty": want})

	if not short_items:
		return {
			"created": None,
			"message": _("Nothing to request — every row's MR Qty is 0 (already fulfilled)."),
		}

	today = frappe.utils.nowdate()
	mr = frappe.new_doc("Material Request")
	mr.material_request_type = "Material Transfer"
	mr.company = wo.company
	mr.transaction_date = today
	mr.schedule_date = today
	if mr.meta.has_field("work_order"):
		mr.work_order = wo.name
	# Target of the transfer = the WO's source warehouse. From-warehouse is left blank.
	if mr.meta.has_field("set_warehouse"):
		mr.set_warehouse = source_warehouse

	for it in short_items:
		mr.append(
			"items",
			{
				"item_code": it["item_code"],
				"qty": it["qty"],
				"schedule_date": today,
				"warehouse": source_warehouse,  # target warehouse (into source)
			},
		)

	mr.flags.ignore_permissions = True
	mr.insert(ignore_permissions=True)  # draft — not submitted
	return {
		"created": mr.name,
		"message": _("Draft Material Request {0} created for {1} packing item(s).").format(
			mr.name, len(short_items)
		),
	}
