# Copyright (c) 2026, pratap_dev contributors
# License: MIT

import json

import frappe
from frappe import _
from frappe.model.mapper import get_mapped_doc
from frappe.utils import flt

from erpnext.buying.doctype.purchase_order.purchase_order import set_missing_values


def get_grn_stats_for_po(purchase_order):
	"""Draft GRN qty per PO item (excludes cancelled PRs)."""
	stats = {}

	rows = frappe.db.sql(
		"""
		SELECT
			pri.purchase_order_item,
			COALESCE(SUM(CASE WHEN pr.docstatus = 0 THEN pri.qty ELSE 0 END), 0) AS draft_grn_qty
		FROM `tabPurchase Receipt Item` pri
		INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
		WHERE pri.purchase_order = %s
			AND pr.docstatus < 2
		GROUP BY pri.purchase_order_item
		""",
		purchase_order,
		as_dict=True,
	)

	for row in rows:
		stats[row.purchase_order_item] = row

	return stats


def get_packing_and_units(po_item_row):
	"""Return packing qty, PO no of unit, and PO total qty for a PO item."""
	packing_qty = flt(po_item_row.get("custom_packing_qty")) or 1
	po_qty = flt(po_item_row.qty)
	po_no_of_unit = flt(po_item_row.get("custom_total_qty"))

	if not po_no_of_unit and packing_qty:
		po_no_of_unit = po_qty / packing_qty

	return packing_qty, po_no_of_unit, po_qty


def get_balance_units_and_qty(po_item_row, grn_stats=None):
	"""Balance based on No of Unit; total qty = balance units × packing."""
	packing_qty, po_no_of_unit, po_qty = get_packing_and_units(po_item_row)
	received_qty = flt(po_item_row.received_qty)
	draft_grn_qty = 0

	if grn_stats:
		item_stats = grn_stats.get(po_item_row.name) or {}
		draft_grn_qty = flt(item_stats.get("draft_grn_qty"))

	received_units = received_qty / packing_qty if packing_qty else 0
	draft_units = draft_grn_qty / packing_qty if packing_qty else 0
	balance_units = max(po_no_of_unit - received_units - draft_units, 0)
	balance_qty = balance_units * packing_qty

	return {
		"packing_qty": packing_qty,
		"po_no_of_unit": po_no_of_unit,
		"po_qty": po_qty,
		"received_units": received_units,
		"draft_units": draft_units,
		"balance_no_of_unit": balance_units,
		"balance_grn_qty": balance_qty,
	}


@frappe.whitelist()
def get_po_grn_dialog_items(purchase_order):
	"""Return PO lines with packing/qty details for the Create GRN dialog."""
	po = frappe.get_doc("Purchase Order", purchase_order)
	po.check_permission("read")

	if po.docstatus != 1:
		frappe.throw(_("Purchase Order must be submitted before creating a GRN."))

	grn_stats = get_grn_stats_for_po(purchase_order)
	has_unit_price_items = po.has_unit_price_items
	rows = []

	for row in po.items:
		if row.delivered_by_supplier:
			continue

		is_unit_price_row = has_unit_price_items and flt(row.qty) == 0
		balance = get_balance_units_and_qty(row, grn_stats)
		balance_qty = balance["balance_grn_qty"]

		if not is_unit_price_row and balance_qty <= 0:
			continue

		balance_units = balance["balance_no_of_unit"]
		packing_qty = balance["packing_qty"]
		default_grn_qty = balance_qty if not is_unit_price_row else flt(row.qty)

		rows.append(
			{
				"po_item": row.name,
				"item_code": row.item_code,
				"item_name": row.item_name,
				"custom_packing_qty": packing_qty,
				"po_no_of_unit": balance["po_no_of_unit"],
				"custom_total_qty": balance_units,
				"po_qty": balance["po_qty"],
				"qty": packing_qty * balance_units,
				"uom": row.uom,
				"received_grn_qty": row.received_qty,
				"draft_grn_qty": flt((grn_stats.get(row.name) or {}).get("draft_grn_qty")),
				"balance_no_of_unit": balance_units,
				"balance_grn_qty": balance_qty,
				"pending_grn_qty": default_grn_qty,
				"grn_qty_to_create": default_grn_qty,
			}
		)

	return rows


def _validate_grn_qty(po_item_name, item_row):
	po_item = frappe.db.get_value(
		"Purchase Order Item",
		po_item_name,
		["qty", "received_qty", "custom_packing_qty", "custom_total_qty", "parent"],
		as_dict=True,
	)

	if not po_item:
		frappe.throw(_("Purchase Order Item {0} not found.").format(po_item_name))

	purchase_order = po_item.parent
	grn_stats = get_grn_stats_for_po(purchase_order)
	balance = get_balance_units_and_qty(
		frappe._dict(
			name=po_item_name,
			qty=po_item.qty,
			received_qty=po_item.received_qty,
			custom_packing_qty=po_item.custom_packing_qty,
			custom_total_qty=po_item.custom_total_qty,
		),
		grn_stats,
	)

	packing_qty = flt(item_row.get("custom_packing_qty")) or balance["packing_qty"]
	no_of_unit = flt(item_row.get("custom_total_qty"))
	receive_qty = flt(item_row.get("grn_qty") or item_row.get("qty"))

	if packing_qty and no_of_unit:
		calculated_qty = packing_qty * no_of_unit
		if abs(calculated_qty - receive_qty) > 0.01:
			receive_qty = calculated_qty

	if no_of_unit > balance["balance_no_of_unit"]:
		frappe.throw(
			_("No of Unit {0} cannot be greater than Balance No of Unit {1}").format(
				no_of_unit, balance["balance_no_of_unit"]
			)
		)

	if receive_qty > balance["balance_grn_qty"]:
		frappe.throw(
			_("Total Qty {0} cannot be greater than Balance GRN Qty {1}").format(
				receive_qty, balance["balance_grn_qty"]
			)
		)

	return receive_qty, packing_qty, no_of_unit


def _make_single_purchase_receipt(purchase_order, item_row):
	"""Create and save one Purchase Receipt containing a single PO item."""
	po_item = item_row.get("po_item")
	receive_qty, packing_qty, no_of_unit = _validate_grn_qty(po_item, item_row)

	item_data_map = {
		po_item: {
			**item_row,
			"grn_qty": receive_qty,
			"custom_packing_qty": packing_qty,
			"custom_total_qty": no_of_unit,
		}
	}

	def update_item(obj, target, source_parent):
		row_data = item_data_map.get(obj.name)
		if not row_data:
			return

		row_receive_qty = flt(row_data.get("grn_qty"))

		target.qty = row_receive_qty
		target.stock_qty = row_receive_qty * flt(obj.conversion_factor)
		target.amount = row_receive_qty * flt(obj.rate)
		target.base_amount = row_receive_qty * flt(obj.rate) * flt(source_parent.conversion_rate)

		for fieldname in ("custom_packing_qty", "custom_total_qty"):
			if row_data.get(fieldname) is not None and hasattr(target, fieldname):
				target.set(fieldname, row_data.get(fieldname))

	def select_item(doc):
		return doc.name in item_data_map

	doc = get_mapped_doc(
		"Purchase Order",
		purchase_order,
		{
			"Purchase Order": {
				"doctype": "Purchase Receipt",
				"field_map": {"supplier_warehouse": "supplier_warehouse"},
				"validation": {"docstatus": ["=", 1]},
			},
			"Purchase Order Item": {
				"doctype": "Purchase Receipt Item",
				"field_map": {
					"name": "purchase_order_item",
					"parent": "purchase_order",
					"bom": "bom",
					"material_request": "material_request",
					"material_request_item": "material_request_item",
					"sales_order": "sales_order",
					"sales_order_item": "sales_order_item",
					"wip_composite_asset": "wip_composite_asset",
				},
				"postprocess": update_item,
				"condition": lambda doc: select_item(doc) and doc.delivered_by_supplier != 1,
			},
			"Purchase Taxes and Charges": {
				"doctype": "Purchase Taxes and Charges",
				"reset_value": True,
			},
		},
		target_doc=None,
		postprocess=set_missing_values,
	)

	doc.save()
	return doc


@frappe.whitelist()
def make_purchase_receipts_from_po(purchase_order, items=None):
	"""Create and auto-save one Purchase Receipt per PO item row."""
	if isinstance(items, str):
		items = json.loads(items)

	valid_items = [
		row
		for row in (items or [])
		if row.get("po_item")
		and (flt(row.get("grn_qty")) or flt(row.get("qty")) or flt(row.get("custom_total_qty"))) > 0
	]

	if not valid_items:
		frappe.throw(_("Please enter No of Unit or GRN quantity for at least one item."))

	frappe.get_doc("Purchase Order", purchase_order).check_permission("read")

	purchase_receipts = []
	for row in valid_items:
		purchase_receipts.append(_make_single_purchase_receipt(purchase_order, row))

	return purchase_receipts


@frappe.whitelist()
def make_purchase_receipt_from_po(purchase_order, items=None):
	"""Backward-compatible API: returns a single PR when only one item is passed."""
	receipts = make_purchase_receipts_from_po(purchase_order, items)
	return receipts[0] if len(receipts) == 1 else receipts
