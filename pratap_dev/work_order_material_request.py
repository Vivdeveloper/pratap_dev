# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Create a Material Request for a Work Order's short raw materials.

Each Required Items row carries an MR Qty (``custom_qty_amount``) = required qty minus the
qty already available at the source warehouse, floored at 0. Rows with MR Qty 0 need
nothing ordered, and including them made ERPNext reject the whole Material Request with
"Row #N: Quantity for Item X cannot be zero" -- so one fully-stocked item blocked the
request for every other item too. Those rows are skipped here instead.

This replaces the DB-resident Server Script ``create material request from work order``
and its companion Client Script ``Create Material Request``; disable both so the button is
not added twice.
"""

import frappe
from frappe import _
from frappe.utils import flt, nowdate

MR_QTY_FIELD = "custom_qty_amount"

# Per-row warehouse stock columns on Work Order Item: (warehouse_name prefix, fieldname).
# Mirrors the "Refresh Stock Count" button (work_order_override.js) so these fill on every
# save too — not only when the button is clicked. "Plant 1/2 WIP RM" as a prefix also matches
# the "…- JOB WORK" warehouse, so JOB WORK is excluded and only leaf warehouses are used.
WO_STOCK_WAREHOUSES = (
	("Plant 1 WIP RM", "custom_plant_1_wip_rm"),
	("Plant 2 WIP RM", "custom_plant_2_wip_rm"),
	("Main Store RM", "custom_main_store_rm"),
)


def _resolve_wo_stock_warehouse(prefix, company):
	rows = frappe.get_all(
		"Warehouse",
		filters=[
			["warehouse_name", "like", prefix + "%"],
			["warehouse_name", "not like", "%JOB WORK%"],
			["company", "=", company],
			["is_group", "=", 0],
		],
		fields=["name"],
		order_by="name asc",
		limit=1,
	)
	return rows[0].name if rows else None


def _set_wo_warehouse_columns(doc):
	"""Fill each Required Items row's Plant 1 WIP / Plant 2 WIP / Main Store RM columns with
	the item's live on-hand stock in those warehouses (Data fields, stored to 3 dp)."""
	from erpnext.stock.utils import get_latest_stock_qty

	# Resolve each warehouse once for the doc's company.
	wh_by_field = {
		fieldname: _resolve_wo_stock_warehouse(prefix, doc.company)
		for prefix, fieldname in WO_STOCK_WAREHOUSES
	}

	for row in doc.get("required_items") or []:
		for fieldname, warehouse in wh_by_field.items():
			if not row.meta.has_field(fieldname):
				continue
			qty = (
				flt(get_latest_stock_qty(row.item_code, warehouse), 3)
				if (warehouse and row.item_code)
				else 0
			)
			row.set(fieldname, qty)


def _requested_qty_by_item(work_order_name):
	"""Qty already requested for this Work Order via NON-CANCELLED Material Requests (DRAFT
	included), per item. So the moment a draft MR is raised for a short item, that item's
	MR Qty reflects it — it no longer shows as still-to-request (and the Start gate opens)."""
	if not work_order_name:
		return {}
	rows = frappe.db.sql(
		"""
		SELECT mri.item_code, SUM(mri.qty) AS qty
		FROM `tabMaterial Request Item` mri
		JOIN `tabMaterial Request` mr ON mr.name = mri.parent
		WHERE mr.work_order = %s AND mr.docstatus != 2
		GROUP BY mri.item_code
		""",
		work_order_name,
		as_dict=True,
	)
	return {r.item_code: flt(r.qty) for r in rows}


@frappe.whitelist()
def get_wo_items_stock(items, company):
	"""Return {item_code: {plant1, plant2, main}} — live on-hand of each item in the three
	RM warehouses. Used by the Work Order form to fill the Plant 1 WIP / Plant 2 WIP / Main
	Store columns LIVE on a new/unsaved WO (before save), using the same resolution as the
	on-save hook so the numbers always agree."""
	import json

	from erpnext.stock.utils import get_latest_stock_qty

	if isinstance(items, str):
		items = json.loads(items or "[]")
	items = [i for i in (items or []) if i]
	if not items:
		return {}

	# Resolve each warehouse once for the company.
	wh_by_field = {
		fieldname: _resolve_wo_stock_warehouse(prefix, company)
		for prefix, fieldname in WO_STOCK_WAREHOUSES
	}

	out = {}
	for item_code in items:
		row = {}
		for fieldname, warehouse in wh_by_field.items():
			row[fieldname] = (
				flt(get_latest_stock_qty(item_code, warehouse), 3) if warehouse else 0
			)
		out[item_code] = row
	return out


def set_mr_qty(doc, method=None):
	"""Keep each Required Items row's MR Qty (``custom_qty_amount``) = required qty minus
	what is already procured for it (available at source + already transferred + already
	requested via a non-cancelled Material Request), floored at 0.

	Runs on Work Order validate (drafts and the after-submit qty Update). The available
	figure is recomputed here from live stock (same helper ERPNext uses) and written back
	to ``available_qty_at_source_warehouse`` so the shown Available column and the derived
	MR Qty always agree: if a row is already fully covered, MR Qty is 0 (nothing to request).
	"""
	from erpnext.stock.utils import get_latest_stock_qty

	requested = _requested_qty_by_item(doc.name)

	# Fill the per-warehouse stock columns (Plant 1 WIP / Plant 2 WIP / Main Store) so they
	# always show actual on-hand on save — the source column already does. This makes, e.g.,
	# Plant 1 WIP RM show the same count as Available at Source when the source IS Plant 1 WIP.
	_set_wo_warehouse_columns(doc)

	for row in doc.get("required_items") or []:
		available = 0.0
		if row.source_warehouse and row.item_code:
			available = flt(get_latest_stock_qty(row.item_code, row.source_warehouse))

		row.available_qty_at_source_warehouse = available

		# Already-transferred material has left the source warehouse but is still procured
		# for this Work Order, so it counts toward the requirement. Without this, every
		# transfer would drop `available` and make MR Qty spike back above 0 mid-flow
		# (which then wrongly re-hid the Start gate).
		# Already-REQUESTED qty (draft/submitted MR for this WO) also counts — so a draft MR
		# drops MR Qty to 0 immediately, reflecting that the request has been placed.
		procured = available + flt(row.transferred_qty) + flt(requested.get(row.item_code))
		shortfall = flt(row.required_qty) - procured
		row.set(MR_QTY_FIELD, shortfall if shortfall > 0 else 0)


def recompute_wo_mr_qty_from_mr(doc, method=None):
	"""Material Request doc-event: when an MR linked to a Work Order is saved / submitted /
	cancelled, refresh that Work Order's Required Items MR Qty right away (so a freshly-saved
	DRAFT MR is reflected without re-saving the Work Order). Writes the two allow-on-submit
	fields directly on the child rows to avoid re-running the whole Work Order save chain."""
	from erpnext.stock.utils import get_latest_stock_qty

	wo_name = doc.get("work_order")
	if not wo_name or not frappe.db.exists("Work Order", wo_name):
		return

	requested = _requested_qty_by_item(wo_name)
	wo = frappe.get_doc("Work Order", wo_name)
	for row in wo.get("required_items") or []:
		available = 0.0
		if row.source_warehouse and row.item_code:
			available = flt(get_latest_stock_qty(row.item_code, row.source_warehouse))
		procured = available + flt(row.transferred_qty) + flt(requested.get(row.item_code))
		shortfall = flt(row.required_qty) - procured
		mr_qty = shortfall if shortfall > 0 else 0
		frappe.db.set_value(
			"Work Order Item", row.name,
			{"available_qty_at_source_warehouse": available, MR_QTY_FIELD: mr_qty},
			update_modified=False,
		)


@frappe.whitelist()
def create_and_submit_material_request(work_order_name):
	if not work_order_name:
		frappe.throw(_("Work Order Name is required"))

	work_order = frappe.get_doc("Work Order", work_order_name)
	work_order.check_permission("read")

	if work_order.docstatus != 1:
		frappe.throw(_("Work Order must be submitted"))

	existing = frappe.db.exists(
		"Material Request", {"work_order": work_order.name, "docstatus": ["!=", 2]}
	)
	if existing:
		frappe.throw(
			_("{0} already exists for this Work Order.").format(
				frappe.utils.get_link_to_form("Material Request", existing)
			),
			title=_("Material Request Already Created"),
		)

	short_rows = [row for row in work_order.required_items if flt(row.get(MR_QTY_FIELD)) > 0]
	if not short_rows:
		frappe.throw(
			_(
				"No items are short — every required item already has enough quantity at its source warehouse."
			),
			title=_("Nothing to Request"),
		)

	mr = frappe.new_doc("Material Request")
	mr.material_request_type = "Material Transfer"
	mr.company = work_order.company
	mr.transaction_date = nowdate()
	mr.schedule_date = nowdate()
	mr.set_warehouse = work_order.source_warehouse
	mr.work_order = work_order.name
	# frappe.session.user is always the login id (email), never the display name --
	# keep it that way so "Requested by user" stays a valid User link, not free text.
	mr.custom_requested_by_user = frappe.session.user

	for row in short_rows:
		mr.append(
			"items",
			{
				"item_code": row.item_code,
				"qty": flt(row.get(MR_QTY_FIELD)),
				"schedule_date": nowdate(),
				"warehouse": row.source_warehouse,
			},
		)

	mr.insert(ignore_permissions=True)
	mr.submit()

	skipped = len(work_order.required_items) - len(short_rows)
	return {"name": mr.name, "requested": len(short_rows), "skipped": skipped}
