# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Rework material provisioning + transfer.

For a rework Pratap QC item, the operator transfers a qty from the Work Order's source
warehouse to the WIP warehouse. If the source warehouse is short, we auto-provision the
missing qty:

  1) create a Material Request of purpose "Rework Material Transfer" (auto-submitted /
     auto-approved through the workflow), from a donor warehouse that has the stock into
     the source warehouse, and
  2) actually MOVE the missing qty with a submitted Material Transfer Stock Entry (donor
     -> source), picking batches FIFO,

so the subsequent rework transfer (source -> WIP) always succeeds.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, nowtime, today

REWORK_MR_TYPE = "Rework Material Transfer"

# Warehouses whose available qty is shown on the rework QC grid (JOB WORK excluded).
RM_WAREHOUSE_FIELDS = [
	("Plant 1 WIP RM", "custom_plant_1_wip_rm"),
	("Plant 2 WIP RM", "custom_plant_2_wip_rm"),
	("Main Store RM", "custom_main_store_rm"),
]


def _resolve_warehouse(prefix, company):
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


def _real_qty(item_code, warehouse):
	if not (item_code and warehouse):
		return 0.0
	from erpnext.stock.utils import get_latest_stock_qty

	return flt(get_latest_stock_qty(item_code, warehouse))


def _item_batches(item_code, warehouse=None):
	"""Batches of an item (optionally in a warehouse) with positive qty, FIFO order."""
	from erpnext.stock.doctype.serial_and_batch_bundle.serial_and_batch_bundle import (
		get_auto_batch_nos,
	)

	kwargs = frappe._dict(
		{
			"item_code": item_code,
			"posting_date": today(),
			"posting_time": nowtime(),
			"for_stock_levels": True,
		}
	)
	if warehouse:
		kwargs.warehouse = warehouse
	out = []
	for b in get_auto_batch_nos(kwargs) or []:
		if flt(b.get("qty")) > 0.0001:
			out.append({"batch_no": b.get("batch_no"), "warehouse": b.get("warehouse"), "qty": flt(b.get("qty"))})
	return out


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def batch_with_qty_query(doctype, txt, searchfield, start, page_len, filters):
	"""Link-field query for the rework Batch dropdown: shows each batch WITH its available
	qty right in the dropdown (batch_no | "Qty: N")."""
	filters = filters or {}
	if isinstance(filters, str):
		filters = json.loads(filters)
	item_code = filters.get("item")
	if not item_code:
		return []
	rows = []
	for b in _item_batches(item_code):
		bn = b["batch_no"]
		if txt and txt.lower() not in (bn or "").lower():
			continue
		rows.append((bn, "Qty: %s" % _fmt(b["qty"])))
	# collapse duplicate batch rows (same batch across warehouses) into one, summing qty
	agg = {}
	for bn, _lbl in rows:
		agg[bn] = agg.get(bn, 0.0)
	# recompute summed qty per batch
	sums = {}
	for b in _item_batches(item_code):
		sums[b["batch_no"]] = sums.get(b["batch_no"], 0.0) + flt(b["qty"])
	out = []
	for bn in agg:
		out.append((bn, "Qty: %s" % _fmt(sums.get(bn, 0))))
	return out[: (page_len or 20)]


def _fmt(v):
	v = flt(v)
	return int(v) if v == int(v) else round(v, 3)


@frappe.whitelist()
def get_rework_item_stock(item_code, company, warehouse=None):
	"""Stock snapshot for a rework QC item: the 3 RM warehouses' available qty, the full
	batch list (batch + qty), and (if a warehouse is given) that warehouse's total qty.
	Feeds the QC grid columns + the batch dropdown."""
	data = {"warehouses": {}, "batches": [], "source_qty": 0.0}
	if not item_code or not company:
		return data

	for prefix, fieldname in RM_WAREHOUSE_FIELDS:
		wh = _resolve_warehouse(prefix, company)
		data["warehouses"][fieldname] = flt(_real_qty(item_code, wh))

	data["batches"] = _item_batches(item_code)
	if warehouse:
		data["source_qty"] = flt(_real_qty(item_code, warehouse))
	return data


def _find_donor_warehouse(item_code, needed, exclude_wh, company):
	"""A warehouse (other than the source) holding at least `needed` of the item. Prefer
	the tracked RM warehouses, then any warehouse with the most stock. Returns
	(warehouse, available_qty) or (None, 0)."""
	needed = flt(needed)

	# 1) preferred RM warehouses
	for prefix, _f in RM_WAREHOUSE_FIELDS:
		wh = _resolve_warehouse(prefix, company)
		if wh and wh != exclude_wh:
			q = flt(_real_qty(item_code, wh))
			if q + 1e-6 >= needed:
				return wh, q

	# 2) any warehouse with enough (most stock first), excluding JOB WORK & the source
	rows = frappe.db.sql(
		"""
		SELECT sle.warehouse, SUM(sle.actual_qty) AS qty
		FROM `tabStock Ledger Entry` sle
		INNER JOIN `tabWarehouse` w ON w.name = sle.warehouse
		WHERE sle.item_code = %(item)s AND sle.is_cancelled = 0
		  AND w.company = %(company)s AND w.warehouse_name NOT LIKE '%%JOB WORK%%'
		  AND sle.warehouse != %(exclude)s
		GROUP BY sle.warehouse HAVING qty > 0.0001
		ORDER BY qty DESC
		""",
		{"item": item_code, "company": company, "exclude": exclude_wh or ""},
		as_dict=True,
	)
	for r in rows:
		if flt(r.qty) + 1e-6 >= needed:
			return r.warehouse, flt(r.qty)
	# nothing has the full amount; return the largest partial (caller decides)
	if rows:
		return rows[0].warehouse, flt(rows[0].qty)
	return None, 0.0


def _pick_batches_fifo(item_code, warehouse, qty):
	"""FIFO batch lines [{batch_no, qty}] covering `qty` from `warehouse`. Raises if the
	warehouse cannot cover it."""
	remaining = flt(qty)
	lines = []
	for b in _item_batches(item_code, warehouse):
		if remaining <= 0.0001:
			break
		take = min(flt(b["qty"]), remaining)
		if take > 0:
			lines.append({"batch_no": b["batch_no"], "qty": flt(take, 3)})
			remaining = flt(remaining - take, 3)
	if remaining > 0.0001:
		frappe.throw(
			_("Warehouse {0} cannot cover {1} of {2} (short by {3}).").format(
				warehouse, flt(qty, 3), item_code, flt(remaining, 3)
			)
		)
	return lines


def _create_rework_mr(company, item_code, uom, qty, from_wh, to_wh, work_order):
	"""Create + auto-submit (auto-approve) a Material Request of purpose Rework Material
	Transfer, moving `qty` from `from_wh` to `to_wh`. Record/paper trail for the move."""
	mr = frappe.new_doc("Material Request")
	mr.material_request_type = REWORK_MR_TYPE
	mr.company = company
	mr.transaction_date = today()
	mr.schedule_date = today()
	mr.set_from_warehouse = from_wh
	mr.set_warehouse = to_wh
	# custom_requested_by_user is a User link that otherwise defaults to a bad value ("EMP")
	# and blocks submit — stamp the current (valid) user.
	if mr.meta.has_field("custom_requested_by_user"):
		mr.custom_requested_by_user = frappe.session.user
	if mr.meta.has_field("work_order"):
		mr.work_order = work_order
	mr.append(
		"items",
		{
			"item_code": item_code,
			"qty": qty,
			"uom": uom,
			"schedule_date": today(),
			"warehouse": to_wh,
			"from_warehouse": from_wh,
		},
	)
	mr.flags.ignore_permissions = True
	mr.insert(ignore_permissions=True)
	# Auto-approve through the workflow (if any) + submit.
	if mr.meta.has_field("workflow_state"):
		mr.db_set("workflow_state", "Submitted", update_modified=False)
	mr.reload()
	mr.flags.ignore_permissions = True
	mr.submit()
	return mr.name


def _move_stock(company, item_code, from_wh, to_wh, qty, uom, material_request=None, mr_item=None):
	"""Create + submit a Material Transfer Stock Entry moving `qty` of a (batched) item
	from `from_wh` to `to_wh`, picking batches FIFO. When `material_request`/`mr_item` are
	given, each row is linked back to the MR so the MR reflects the transfer (shows
	Transferred, not Pending). Returns the Stock Entry name."""
	lines = _pick_batches_fifo(item_code, from_wh, qty)
	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Material Transfer"
	se.purpose = "Material Transfer"
	se.company = company
	se.posting_date = today()
	se.posting_time = nowtime()
	se.set_posting_time = 1
	stock_uom = frappe.get_cached_value("Item", item_code, "stock_uom")
	for ln in lines:
		row = {
			"s_warehouse": from_wh,
			"t_warehouse": to_wh,
			"item_code": item_code,
			"qty": ln["qty"],
			"transfer_qty": ln["qty"],
			"uom": uom or stock_uom,
			"stock_uom": stock_uom,
			"conversion_factor": 1,
			"use_serial_batch_fields": 1,
			"batch_no": ln["batch_no"],
		}
		if material_request:
			row["material_request"] = material_request
			row["material_request_item"] = mr_item
		se.append("items", row)
	if material_request:
		se.add_to_transit = 0
	se.flags.ignore_permissions = True
	se.insert(ignore_permissions=True)
	se.submit()
	return se.name


@frappe.whitelist()
def provision_source_shortfall(work_order, item_code, needed_qty, source_warehouse):
	"""Ensure `source_warehouse` holds at least `needed_qty` of `item_code`. If short,
	auto-create a Rework Material Transfer MR + a submitted Stock Entry that moves the
	missing qty from a donor warehouse into the source. Returns a summary."""
	wo = frappe.get_doc("Work Order", work_order)
	wo.check_permission("read")
	needed_qty = flt(needed_qty)
	src = source_warehouse or wo.source_warehouse
	company = wo.company
	uom = frappe.get_cached_value("Item", item_code, "stock_uom")

	have = flt(_real_qty(item_code, src))
	if have + 1e-6 >= needed_qty:
		return {"shortfall": 0, "source_qty": have}

	missing = flt(needed_qty - have, 3)
	donor, donor_qty = _find_donor_warehouse(item_code, missing, src, company)
	if not donor or donor_qty + 1e-6 < missing:
		frappe.throw(
			_(
				"Source warehouse {0} is short by {1} of {2}, and no other warehouse has "
				"enough to cover it (best available: {3} in {4})."
			).format(src, missing, item_code, flt(donor_qty, 3), donor or _("none"))
		)

	mr = _create_rework_mr(company, item_code, uom, missing, donor, src, wo.name)
	mr_item = frappe.db.get_value("Material Request Item", {"parent": mr, "item_code": item_code}, "name")
	se = _move_stock(company, item_code, donor, src, missing, uom, material_request=mr, mr_item=mr_item)

	# ERPNext doesn't auto-update fulfilment status for the custom "Rework Material Transfer"
	# type, so mark it Transferred ourselves (the linked Stock Entry above actually moved the
	# stock). This keeps the MR from lingering on "Pending" after it's really done.
	if mr_item:
		frappe.db.set_value("Material Request Item", mr_item, "ordered_qty", missing, update_modified=False)
	frappe.db.set_value("Material Request", mr, {"per_ordered": 100, "status": "Transferred"}, update_modified=False)
	frappe.db.commit()
	return {
		"shortfall": missing,
		"donor_warehouse": donor,
		"material_request": mr,
		"stock_entry": se,
		"source_qty": flt(_real_qty(item_code, src)),
	}


@frappe.whitelist()
def rework_transfer_with_provision(work_order, qc, item_code, qty, batch=None):
	"""Transfer `qty` of a rework item from the WO source warehouse to WIP. If the source
	is short, first auto-provision the shortfall (Rework Material Transfer MR + Stock Entry
	move), then do the rework transfer via the existing per-batch rework flow.

	Returns {provision, transfer} — `provision` is null when the source already had enough.
	"""
	from pratap_dev.work_order_transfer import _make_rework_transfer, _validate_rework_qc

	qty = flt(qty)
	if qty <= 0:
		frappe.throw(_("Enter a transfer qty greater than 0."))

	wo = frappe.get_doc("Work Order", work_order)
	wo.check_permission("read")
	_validate_rework_qc(qc, wo.name)

	qc_doc = frappe.get_doc("Pratap Quality Inspection", qc)
	rm = next((r for r in (qc_doc.get("raw_materials") or []) if r.item_code == item_code), None)
	if not rm:
		frappe.throw(_("Item {0} is not in this rework QC.").format(item_code))
	src = rm.get("source_warehouse") or wo.source_warehouse

	# 1) Make sure the source warehouse holds `qty` (auto-provision the shortfall).
	provision = provision_source_shortfall(wo.name, item_code, qty, src)

	# 2) Transfer `qty` from source -> WIP, picking batches FIFO from the source (or the
	#    chosen batch first). This is the rework Material Transfer for Manufacture SE.
	lines = []
	remaining = qty
	# prefer the operator-chosen batch, then FIFO for the rest.
	ordered = _item_batches(item_code, src)
	if batch:
		ordered.sort(key=lambda b: 0 if b["batch_no"] == batch else 1)
	for b in ordered:
		if remaining <= 0.0001:
			break
		take = min(flt(b["qty"]), remaining)
		if take > 0:
			lines.append({"batch_no": b["batch_no"], "std_pkg": take, "units": 1, "qty": flt(take, 3)})
			remaining = flt(remaining - take, 3)
	if remaining > 0.0001 or not lines:
		frappe.throw(_("Could not cover {0} of {1} at {2} even after provisioning.").format(qty, item_code, src))

	se_name = _make_rework_transfer(wo, item_code, src, lines, qc)

	# Log a "Material Transfer" marker on the rework item (same as the popup does).
	from pratap_dev.work_order_transfer import _rework_data, _save_rework_data, _compose_log, _rework_item_transfers

	data = _rework_data(qc)
	d = data.setdefault(item_code, {})
	d["addition_log"] = _compose_log(d.get("addition_log"), "Material Transfer")
	_save_rework_data(qc, data)
	frappe.db.commit()

	return {
		"provision": provision if provision.get("shortfall") else None,
		"transfer": {
			"stock_entry": se_name,
			"transfers": _rework_item_transfers(wo.name, qc, item_code),
			"addition_log": d["addition_log"],
		},
	}
