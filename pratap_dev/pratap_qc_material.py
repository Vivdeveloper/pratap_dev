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


def set_source_warehouse_from_wo(doc):
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

	mismatches = []
	for item_code, agg in by_item.items():
		if not agg["has_batch"]:
			continue
		if abs(agg["batch"] - agg["total"]) > _QTY_TOLERANCE:
			mismatches.append((item_code, agg["batch"], agg["total"]))

	if mismatches:
		msg = "<br>".join(
			_("{0}: Batch Qty {1} does not match Total Req Qty {2}").format(
				frappe.bold(ic), flt(b), flt(t)
			)
			for ic, b, t in mismatches
		)
		frappe.throw(
			_("Batch Qty must match Total Req Qty before saving:<br>{0}").format(msg),
			title=_("Batch Qty Mismatch"),
		)


# ---------------------------------------------------------------------------
# On submit: create Material Transfer MR for rows where Batch Location != Source WH
# ---------------------------------------------------------------------------
def create_transfer_mr_on_submit(doc, method=None):
	"""When a batch is stored somewhere other than the Source Warehouse, raise a
	Material Request (purpose Material Transfer) to move it Batch Location -> Source
	Warehouse. One MR for the whole QC; each mismatched row is one MR item."""
	items = []
	for row in doc.get("raw_materials") or []:
		batch_loc = row.get("custom_batch_location")
		source = row.get("source_warehouse")
		qty = flt(row.get("custom_batch_qty"))
		if not (row.item_code and batch_loc and source and qty > 0):
			continue
		if batch_loc == source:
			continue
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

	if not items:
		return

	mr = frappe.new_doc("Material Request")
	mr.material_request_type = "Material Transfer"
	mr.transaction_date = frappe.utils.today()
	mr.schedule_date = frappe.utils.today()
	if doc.get("company"):
		mr.company = doc.company
	mr.custom_source_pratap_qc = doc.name if mr.meta.has_field("custom_source_pratap_qc") else None
	for it in items:
		mr.append("items", it)
	mr.insert(ignore_permissions=True)

	frappe.msgprint(
		_("Material Request {0} (Material Transfer) created for {1} batch(es) stored away from the Source Warehouse.").format(
			frappe.utils.get_link_to_form("Material Request", mr.name), len(items)
		),
		indicator="green",
		alert=True,
	)
