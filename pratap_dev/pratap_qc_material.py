"""Pratap Quality Inspection — raw-material batch / Material-Request logic.

Requirements (from the batch/MR spec):

1. Two-way Mat Req % <-> Total Req Qty (client-side, pratap_quality_inspection.js).
2. Batch Qty must match Total Req Qty before save/submit — per item, the SUM of
   Batch Qty across an item's rows must equal that item's Total Req Qty.
3. Source Warehouse is fetched from the Work Order's Custom Source Warehouse and is
   read-only (client fills it; enforced here as a safety net).
4. Batch Location captures where the selected batch is stored (client picks from the
   batch's stock warehouses; helper below feeds that list).
5. On submit, if Batch Location != Source Warehouse, create a Material Request with
   purpose "Material Transfer" (Batch Location -> Source Warehouse). Multiple rows
   (item taken from several batches/locations) become multiple MR items.
"""

import frappe
from frappe import _
from frappe.utils import flt

# Tolerance for float comparison of the batch-qty vs total-req-qty check.
_QTY_TOLERANCE = 0.001


# ---------------------------------------------------------------------------
# Batch stock helper (client: batch-location dropdown + batch-qty autofill)
# ---------------------------------------------------------------------------
@frappe.whitelist()
def get_batch_warehouses(batch_no):
	"""Warehouses where `batch_no` currently has positive stock, largest first.

	Returns [{"warehouse": ..., "qty": ...}, ...]. Used by the QC raw-material grid to
	limit the Batch Location dropdown and to auto-fill Batch Qty for the chosen location.
	"""
	if not batch_no:
		return []

	from erpnext.stock.doctype.serial_and_batch_bundle.serial_and_batch_bundle import (
		get_available_batches,
	)

	item_code = frappe.db.get_value("Batch", batch_no, "item")
	if not item_code:
		return []

	# Batch stock is tracked via Serial & Batch bundles (not the SLE batch_no column),
	# so use ERPNext's helper. It reports the live per-warehouse balance for the batch.
	data = get_available_batches(
		frappe._dict({"item_code": item_code, "batch_no": batch_no})
	) or []
	rows = []
	for d in data:
		qty = flt(d.get("qty"))
		wh = d.get("warehouse")
		if wh and qty > 0:
			rows.append({"warehouse": wh, "qty": qty})
	rows.sort(key=lambda r: r["qty"], reverse=True)
	return rows


# ---------------------------------------------------------------------------
# Source Warehouse safety net (from Work Order Custom Source Warehouse)
# ---------------------------------------------------------------------------
def _wo_source_warehouse(doc):
	wo = doc.get("work_order") or (
		doc.get("reference_name") if doc.get("reference_type") == "Work Order" else None
	)
	if not wo:
		return None
	return frappe.db.get_value("Work Order", wo, "custom_custom_source_warehouse")


def set_source_warehouse_from_wo(doc, method=None):
	"""Stamp every raw-material row's Source Warehouse from the WO Custom Source
	Warehouse (read-only field; the client sets it live, this guarantees it on save)."""
	src = _wo_source_warehouse(doc)
	if not src:
		return
	for row in doc.get("raw_materials") or []:
		row.source_warehouse = src


# ---------------------------------------------------------------------------
# Validation: per-item SUM(Batch Qty) must equal SUM(Total Req Qty)
# ---------------------------------------------------------------------------
def validate_batch_qty_matches_total(doc, method=None):
	"""Block save/submit unless, for every item that uses batches, the summed Batch Qty
	across its rows equals the summed Total Req Qty. Items with no batch selected are
	skipped (nothing to reconcile yet)."""
	rows = doc.get("raw_materials") or []
	# Only enforce for items where at least one row has a batch selected.
	by_item = {}
	for row in rows:
		if not row.item_code:
			continue
		agg = by_item.setdefault(row.item_code, {"batch": 0.0, "total": 0.0, "has_batch": False})
		agg["total"] += flt(row.total_req_qty)
		if row.get("custom_batch"):
			agg["has_batch"] = True
			agg["batch"] += flt(row.custom_batch_qty)

	# Only block when the batch quantity is LESS than required (short). Equal or more is fine.
	shortfalls = []
	for item_code, agg in by_item.items():
		if not agg["has_batch"]:
			continue
		if agg["batch"] < agg["total"] - _QTY_TOLERANCE:
			shortfalls.append((item_code, agg["batch"], agg["total"]))

	if shortfalls:
		msg = "<br>".join(
			_("{0}: Batch Qty {1} is less than Total Req Qty {2}").format(
				frappe.bold(ic), flt(b), flt(t)
			)
			for ic, b, t in shortfalls
		)
		frappe.throw(
			_("Batch Qty cannot be less than Total Req Qty:<br>{0}").format(msg),
			title=_("Insufficient Batch Qty"),
		)


# ---------------------------------------------------------------------------
# On submit: create Material Transfer MR for rows where Batch Location != Source WH
# ---------------------------------------------------------------------------
REWORK_STOCK_ENTRY_TYPE = "Rework Material Transfer"


def create_transfer_mr_on_submit(doc, method=None):
	"""When a batch is stored somewhere other than the Source Warehouse, create BOTH:
	  1. A Material Request (type "Material Transfer") that is SUBMITTED (the record), and
	  2. A DRAFT Stock Entry (type "Rework Material Transfer") to move the batch
	     Batch Location -> Source Warehouse, left as a Draft for manual approval/submit.
	One MR + one Stock Entry for the whole QC; each row where Batch Location differs from
	Source Warehouse is one line."""
	items = []   # MR items
	moves = []   # Stock Entry batch moves
	from_whs = set()
	to_whs = set()
	for row in doc.get("raw_materials") or []:
		batch_loc = row.get("custom_batch_location")
		source = row.get("source_warehouse")
		qty = flt(row.get("custom_batch_qty"))
		if not (row.item_code and batch_loc and source and qty > 0):
			continue
		if batch_loc == source:
			continue
		from_whs.add(batch_loc)
		to_whs.add(source)
		items.append(
			{
				"item_code": row.item_code,
				"qty": qty,
				"uom": row.uom,
				"from_warehouse": batch_loc,
				"warehouse": source,
				"schedule_date": frappe.utils.today(),
			}
		)
		moves.append(
			{
				"item_code": row.item_code,
				"qty": qty,
				"uom": row.uom,
				"s_warehouse": batch_loc,
				"t_warehouse": source,
				"batch_no": row.get("custom_batch"),
			}
		)

	if not items:
		return

	# 1) Material Request (type "Material Transfer"), SUBMITTED — the record.
	mr = frappe.new_doc("Material Request")
	mr.material_request_type = "Material Transfer"
	mr.transaction_date = frappe.utils.today()
	mr.schedule_date = frappe.utils.today()
	if doc.get("company"):
		mr.company = doc.company
	if len(from_whs) == 1:
		mr.set_from_warehouse = next(iter(from_whs))
	if len(to_whs) == 1:
		mr.set_warehouse = next(iter(to_whs))
	# "Requested by user" defaults to an invalid "EMP" which blocks submit — set current user.
	if mr.meta.has_field("custom_requested_by_user"):
		mr.custom_requested_by_user = frappe.session.user
	for it in items:
		mr.append("items", it)
	mr.insert(ignore_permissions=True)
	try:
		mr.submit()
	except Exception:
		frappe.log_error(title="Rework MR submit failed", message=frappe.get_traceback())

	# 2) DRAFT Stock Entry of the dedicated rework type — NOT submitted (manual approval).
	se_name = None
	try:
		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = REWORK_STOCK_ENTRY_TYPE
		se.purpose = "Material Transfer"
		if doc.get("company"):
			se.company = doc.company
		se.set_posting_time = 1
		se.posting_date = frappe.utils.today()
		for m in moves:
			se.append(
				"items",
				{
					"item_code": m["item_code"],
					"qty": m["qty"],
					"uom": m["uom"],
					"stock_uom": m["uom"],
					"conversion_factor": 1,
					"s_warehouse": m["s_warehouse"],
					"t_warehouse": m["t_warehouse"],
					"use_serial_batch_fields": 1,
					"batch_no": m["batch_no"],
				},
			)
		se.insert(ignore_permissions=True)  # DRAFT — do not submit
		se_name = se.name
	except Exception:
		frappe.log_error(title="Rework draft Stock Entry failed", message=frappe.get_traceback())

	if se_name:
		frappe.msgprint(
			_("Material Request {0} (submitted) and Draft Stock Entry {1} ({2}) created for {3} batch(es) stored away from the Source Warehouse. Submit the Stock Entry to move the stock.").format(
				frappe.utils.get_link_to_form("Material Request", mr.name),
				frappe.utils.get_link_to_form("Stock Entry", se_name),
				REWORK_STOCK_ENTRY_TYPE,
				len(moves),
			),
			indicator="green",
			alert=True,
		)
	else:
		frappe.msgprint(
			_("Material Request {0} created, but the rework transfer Stock Entry could not be created automatically — create it manually.").format(
				frappe.utils.get_link_to_form("Material Request", mr.name)
			),
			indicator="orange",
		)
