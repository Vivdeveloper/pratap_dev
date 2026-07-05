# Copyright (c) 2026, pratap_dev contributors
# License: MIT

import json

import frappe
from frappe import _
from frappe.model.mapper import get_mapped_doc
from frappe.model.naming import make_autoname
from frappe.utils import flt

# Running series for the GRN group id, e.g. PRG-26-00001, PRG-26-00002 ...
# `.YY.` = 2-digit year, `.#####` = zero-padded incrementing counter (kept in `tabSeries`).
GRN_GROUP_SERIES = "PRG-.YY.-.#####"

from erpnext.buying.doctype.purchase_order.purchase_order import set_missing_values


@frappe.whitelist()
def get_last_buying_rate(doc=None, supplier=None, item_codes=None, current_po=None):
	"""Return last buying rate details for PO items."""
	doc = _parse_po_doc(doc) if doc else {}
	po_items = doc.get("items") or []

	supplier = supplier or doc.get("supplier")
	if isinstance(item_codes, str):
		item_codes = json.loads(item_codes) if item_codes else []
	if not item_codes and po_items:
		item_codes = [item.get("item_code") for item in po_items if item.get("item_code")]

	if not current_po and doc.get("name") and not doc.get("__islocal"):
		current_po = doc.get("name")

	if not supplier or not item_codes:
		return []

	normalized_codes = [(code or "").strip().upper() for code in item_codes]
	rate_map = _get_last_buying_rate_map(supplier, normalized_codes, current_po)

	rows = []
	source_items = po_items or [{"item_code": code} for code in item_codes]

	for item in source_items:
		item_code = item.get("item_code")
		if not item_code:
			continue

		last = rate_map.get(item_code.strip().upper(), {})
		rows.append(
			{
				"item_code": item_code,
				"supplier_item": _resolve_supplier_item(item, supplier),
				"po_rate": flt(item.get("rate")),
				"po_uom": item.get("uom"),
				"last_buying_rate": last.get("last_buying_rate"),
				"last_uom": last.get("uom"),
				"last_supplier": last.get("supplier_name") or last.get("supplier"),
			}
		)

	return rows


def _resolve_supplier_item(item, supplier):
	if item.get("supplier_part_no"):
		return item.get("supplier_part_no")

	item_code = item.get("item_code")
	if supplier and item_code:
		item_supplier = frappe.db.get_value(
			"Item Supplier",
			{"parent": item_code, "supplier": supplier},
			["supplier_part_no", "custom_supplier_item"],
			as_dict=True,
		)
		if item_supplier:
			return item_supplier.custom_supplier_item or item_supplier.supplier_part_no

	return item.get("item_name") or item_code


def _get_last_buying_rate_map(supplier, item_codes, current_po=None):
	if not item_codes:
		return {}

	item_tuple = (item_codes[0], item_codes[0]) if len(item_codes) == 1 else tuple(item_codes)
	params = {
		"supplier": supplier,
		"item_codes": item_tuple,
		"current_po": current_po or "",
	}

	rows = frappe.db.sql(
		"""
		SELECT
			UPPER(TRIM(poi.item_code)) AS item_code,
			poi.rate AS last_buying_rate,
			poi.uom,
			po.supplier_name,
			po.transaction_date,
			po.creation
		FROM `tabPurchase Order Item` poi
		INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
		WHERE po.docstatus IN (0, 1)
			AND po.supplier = %(supplier)s
			AND po.name != %(current_po)s
			AND UPPER(TRIM(poi.item_code)) IN %(item_codes)s
		ORDER BY po.transaction_date DESC, po.creation DESC
		""",
		params,
		as_dict=True,
	)

	rate_map = {}
	for row in rows:
		if row.item_code not in rate_map:
			rate_map[row.item_code] = row

	return rate_map


def disable_purchase_after_save_message():
	"""Disable legacy UOM popup shown after save."""
	script_name = "Purchase After Save Message"
	if frappe.db.exists("Client Script", script_name):
		frappe.db.set_value("Client Script", script_name, "enabled", 0)


def _parse_po_doc(doc):
	if not doc:
		doc = frappe.form_dict.get("doc")
	if isinstance(doc, str):
		doc = json.loads(doc)
	return doc or {}


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


def _make_purchase_receipt_for_rows(
	purchase_order,
	item_rows,
	group_id=None,
	sales_invoice_number=None,
	sales_invoice_date=None,
):
	"""Create and save one Purchase Receipt containing the given PO item rows.

	Multiple rows of the SAME item (each with its own Standard Pkg Qty / No of Unit)
	are placed into ONE GRN, so batches for each row can be handled together.
	"""
	item_data_map = {}
	for item_row in item_rows:
		po_item = item_row.get("po_item")
		receive_qty, packing_qty, no_of_unit = _validate_grn_qty(po_item, item_row)
		item_data_map[po_item] = {
			**item_row,
			"grn_qty": receive_qty,
			"custom_packing_qty": packing_qty,
			"custom_total_qty": no_of_unit,
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

	if group_id and doc.meta.has_field("custom_grn_group_id"):
		doc.custom_grn_group_id = group_id

	# Dialog's Sales Invoice Number / Date go into the GRN's Supplier Invoice fields
	# (these flow to the combined Purchase Invoice later).
	if sales_invoice_number and doc.meta.has_field("custom_supplier_invoice_no"):
		doc.custom_supplier_invoice_no = sales_invoice_number
	if sales_invoice_date and doc.meta.has_field("custom_supplier_invoice_date"):
		doc.custom_supplier_invoice_date = sales_invoice_date

	doc.save()
	return doc


@frappe.whitelist()
def make_purchase_receipts_from_po(
	purchase_order, items=None, sales_invoice_number=None, sales_invoice_date=None
):
	"""Create and auto-save one Purchase Receipt per PO item row.

	All receipts made in one call share a single GRN group id; the combined Purchase
	Invoice is created once every GRN in that group is submitted (see purchase_receipt.py).
	"""
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

	if not sales_invoice_number:
		frappe.throw(_("Sales Invoice Number is mandatory."))
	if not sales_invoice_date:
		frappe.throw(_("Invoice Date is mandatory."))

	frappe.get_doc("Purchase Order", purchase_order).check_permission("read")

	group_id = make_autoname(GRN_GROUP_SERIES)

	# Group selected rows by item_code -> one GRN per unique item. So a PO where the
	# same item appears in multiple rows (different Std Pkg Qty / No of Unit) makes a
	# single GRN for that item (e.g. 4 rows with 2 same item -> 3 GRNs, not 4).
	from collections import OrderedDict

	grouped = OrderedDict()
	for row in valid_items:
		item_code = row.get("item_code") or frappe.db.get_value(
			"Purchase Order Item", row.get("po_item"), "item_code"
		)
		grouped.setdefault(item_code, []).append(row)

	purchase_receipts = []
	for item_rows in grouped.values():
		purchase_receipts.append(
			_make_purchase_receipt_for_rows(
				purchase_order,
				item_rows,
				group_id=group_id,
				sales_invoice_number=sales_invoice_number,
				sales_invoice_date=sales_invoice_date,
			)
		)

	return purchase_receipts


@frappe.whitelist()
def make_purchase_receipt_from_po(
	purchase_order, items=None, sales_invoice_number=None, sales_invoice_date=None
):
	"""Backward-compatible API: returns a single PR when only one item is passed."""
	receipts = make_purchase_receipts_from_po(
		purchase_order, items, sales_invoice_number, sales_invoice_date
	)
	return receipts[0] if len(receipts) == 1 else receipts
