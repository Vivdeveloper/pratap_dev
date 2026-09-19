"""Per-supplier standard pack size tracking.

Flow
----
1. CAPTURE (Purchase Receipt `on_update`):
   A Purchase Receipt has one Supplier (header) and each item row carries a
   Standard Pkg Qty (`custom_packing_qty`). Whenever a PR is saved we record the
   latest pack size per (Item, Supplier) into the Item master's dedicated
   "Supplier Pack Sizes" table (`Item.custom_supplier_pack_sizes`, child doctype
   "Item Supplier Pack Size"). Same supplier again -> update to the latest value;
   new supplier -> append a new row.

2. USE (Request for Quotation `validate`):
   For each RFQ item we look up the tracked pack size for the RFQ's supplier and
   pre-fill Standard Pkg Qty (only when it's blank, so a manual override wins),
   then compute No of Unit = ceil(Quantity / Standard Pkg Qty). If nothing is
   tracked for that (Item, Supplier), both fields are left blank for manual entry.
"""

import math

import frappe
from frappe.utils import flt


def _fmt(value):
	"""Render a number without a trailing .0 (fields are Data / free text)."""
	value = flt(value)
	return str(int(value)) if value == int(value) else str(value)


# ---------------------------------------------------------------------------
# CAPTURE — Purchase Receipt -> Item.custom_supplier_pack_sizes
# ---------------------------------------------------------------------------
def capture_pack_sizes(doc, method=None):
	"""Track the latest Standard Pkg Qty per (Item, Supplier) from a Purchase Receipt.

	The supplier is taken from the Purchase Receipt header; each item row supplies
	the Standard Pkg Qty (`custom_packing_qty`).
	"""
	supplier = doc.get("supplier")
	if not supplier:
		return

	touched = {}
	for row in doc.get("items") or []:
		item_code = row.get("item_code")
		pack = flt(row.get("custom_packing_qty"))
		if not item_code or pack <= 0:
			continue
		# Latest row within this document wins for a given (item, supplier).
		touched.setdefault(item_code, {})[supplier] = pack

	for item_code, supplier_map in touched.items():
		try:
			_upsert_item_pack_sizes(item_code, supplier_map)
		except Exception:
			# Never let pack-size tracking block the Material Request from saving.
			frappe.log_error(
				title="Item pack-size capture failed",
				message=f"item={item_code} suppliers={supplier_map}\n{frappe.get_traceback()}",
			)


def _upsert_item_pack_sizes(item_code, supplier_map):
	if not frappe.db.exists("Item", item_code):
		return

	item = frappe.get_doc("Item", item_code)
	existing = {r.supplier: r for r in (item.get("custom_supplier_pack_sizes") or [])}
	changed = False

	for supplier, pack in supplier_map.items():
		row = existing.get(supplier)
		if row:
			if flt(row.get("pack_size")) != flt(pack):
				row.pack_size = pack
				changed = True
		else:
			item.append("custom_supplier_pack_sizes", {"supplier": supplier, "pack_size": pack})
			changed = True

	if changed:
		item.save(ignore_permissions=True)


# ---------------------------------------------------------------------------
# USE — Request for Quotation: pre-fill Standard Pkg Qty + No of Unit
# ---------------------------------------------------------------------------
def apply_rfq_pack_sizes(doc, method=None):
	"""Fill Standard Pkg Qty (from the tracked table) and No of Unit on RFQ items."""
	supplier = doc.get("custom_supplier_code")
	if not supplier:
		suppliers = doc.get("suppliers") or []
		supplier = suppliers[0].supplier if suppliers else None
	if not supplier:
		return

	cache = {}
	for row in doc.get("items") or []:
		item_code = row.get("item_code")
		if not item_code:
			continue

		if item_code not in cache:
			cache[item_code] = _get_pack_size(item_code, supplier)
		tracked = cache[item_code]

		# Auto-fill Standard Pkg Qty from the tracked table only when it's blank
		# (a manually entered value is preserved so the user can override).
		if tracked > 0 and not flt(row.get("custom_packing_qty")):
			row.custom_packing_qty = _fmt(tracked)

		# Default No of Unit = ceil(Quantity / Standard Pkg Qty), but ONLY when it's
		# blank -- a manually entered No of Unit is preserved. Live recompute while
		# editing is handled client-side (request_for_quotation.js).
		pack = flt(row.get("custom_packing_qty"))
		qty = flt(row.get("qty"))
		if pack > 0 and qty > 0 and not flt(row.get("custom_total_qty")):
			row.custom_total_qty = str(int(math.ceil(qty / pack)))


def _get_pack_size(item_code, supplier):
	rows = frappe.get_all(
		"Item Supplier Pack Size",
		filters={"parenttype": "Item", "parent": item_code, "supplier": supplier},
		fields=["pack_size"],
		order_by="idx desc",
		limit=1,
	)
	return flt(rows[0].pack_size) if rows else 0.0


@frappe.whitelist()
def get_pack_size(item_code, supplier):
	"""Client hook: tracked pack size for (item, supplier), or 0 if none. Used by
	request_for_quotation.js to pre-fill Standard Pkg Qty live on item selection."""
	if not item_code or not supplier:
		return 0.0
	return _get_pack_size(item_code, supplier)
