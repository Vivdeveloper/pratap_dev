# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Item-by-item, batch-wise Material Transfer for Manufacture from a Work Order.

Replaces the standard "Start -> transfer all items in one Stock Entry" flow. The
operator opens a popup, and for ONE required item at a time picks batch(es) (Std Pkg
Qty x No of Units = actual taken), runs a Start/Hold/End timer, and on End(=Submit)
this creates + submits a single "Material Transfer for Manufacture" Stock Entry for
that item (linked to the Work Order). ERPNext then updates the row's Transferred Qty.

We also persist, on the Work Order Item row: the batch breakdown taken ("BATCH PKG
UNITS" lines), and the addition start/end/time-window/duration from the timer.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, format_datetime


@frappe.whitelist()
def get_wo_transfer_context(work_order):
	"""Per required item: qty figures, available batches, and any saved transfer data."""
	wo = frappe.get_doc("Work Order", work_order)
	wo.check_permission("read")

	items = []
	for row in wo.required_items:
		if not row.item_code:
			continue
		src = row.source_warehouse or wo.source_warehouse
		required = flt(row.required_qty)
		# Exclude rework transfers from the main tab's figures — they belong to the
		# Rework tab and are tracked per rework QC (see _wo_rework_qcs).
		transferred = flt(row.transferred_qty) - _rework_transferred_qty(wo.name, row.item_code)
		remaining = max(required - transferred, 0)
		has_batch = bool(frappe.db.get_value("Item", row.item_code, "has_batch_no"))
		items.append(
			{
				"row": row.name,
				"item_code": row.item_code,
				"item_name": row.item_name,
				"instruction_marathi": row.get("custom_operation_instruction_marathi") or "",
				"uom": row.stock_uom,
				"required_qty": required,
				"transferred_qty": flt(transferred, 3),
				"remaining_qty": flt(remaining, 3),
				"source_warehouse": src,
				"has_batch": has_batch,
				"batches": _available_batches(row.item_code, src) if has_batch else [],
				# Actual transfers made for this item (from the submitted Stock Entries).
				"transfers": _item_transfers(wo.name, row.item_code),
				"time_window": row.get("custom_addition_time_window") or "",
				# In-progress (unsubmitted) batch rows saved via "Save as Draft".
				"draft_rows": _parse_draft(row.get("custom_transfer_draft")),
				# Chronological Start/Stop/Material Transfer trail shown against the item.
				"addition_log": row.get("custom_addition_log") or "",
				# Accumulated time (sum of all Start→Stop intervals) + open-timer state.
				"duration_mins": flt(row.get("custom_addition_duration_mins"), 3),
				"timer_running": bool(row.get("custom_addition_start")),
				"finished": "Finish —" in (row.get("custom_addition_log") or ""),
				"is_full": remaining <= 0.0001,
			}
		)

	plan_set = any(r.get("custom_planned_batches") for r in wo.required_items)
	return {
		"work_order": wo.name,
		"wip_warehouse": wo.wip_warehouse,
		"items": items,
		"plan_set": plan_set,
		"can_set_plan": _can_set_plan(bool(wo.get("custom_plan_user_saved"))),
		"job_cards": _wo_job_cards(wo),
		"batch_started_at": str(wo.get("custom_batch_started_at") or "") or None,
		"rework_qcs": _wo_rework_qcs(wo),
	}


@frappe.whitelist()
def start_batch(work_order):
	"""Stamp the batch start time on the Work Order, once. Returns the stored value;
	never overwrites an existing one (the popup hides the button after it is set)."""
	from frappe.utils import now_datetime

	wo = frappe.get_doc("Work Order", work_order)
	wo.check_permission("read")
	existing = wo.get("custom_batch_started_at")
	if not existing:
		existing = str(now_datetime())
		frappe.db.set_value(
			"Work Order", wo.name, "custom_batch_started_at", existing, update_modified=False
		)
		frappe.db.commit()
	return {"batch_started_at": str(existing)}


# --- Job Cards (operations run from the popup) --------------------------------

def _wo_job_cards(wo):
	"""Job Cards for this Work Order with the state the popup needs to show operation
	controls (Start / Hold / Resume / Finish) mirroring the Job Card form's own gating."""
	names = frappe.get_all(
		"Job Card",
		filters={"work_order": wo.name, "docstatus": ["<", 2]},
		pluck="name",
		order_by="sequence_id asc, creation asc",
	)
	skip_transfer = bool(wo.get("skip_transfer"))
	wo_status = wo.status
	out = []
	for name in names:
		jc = frappe.get_doc("Job Card", name)
		items = jc.get("items") or []
		material_ok = (not items) or all(flt(i.transferred_qty) >= flt(i.required_qty) for i in items)
		wo_ok = skip_transfer or wo_status == "In Process" or flt(jc.get("transferred_qty")) > 0 or (not items)
		for_qty = flt(jc.for_quantity)
		done_qty = flt(jc.total_completed_qty)
		qty_met = for_qty > 0 and done_qty >= for_qty

		employees = []
		for e in (jc.get("employee") or []):
			employees.append(
				{"employee": e.employee,
				 "employee_name": frappe.db.get_value("Employee", e.employee, "employee_name") or e.employee}
			)

		# "Running" = there is an open time log (a row started but not yet closed). This is
		# more reliable than started_time/current_time, which ERPNext clears on Resume.
		has_open_log = any(tl.from_time and not tl.to_time for tl in (jc.get("time_logs") or []))

		if jc.docstatus == 1:
			ui = "completed"
		elif qty_met:
			ui = "awaiting_submit"
		elif not material_ok:
			ui = "needs_material"
		elif not wo_ok:
			ui = "wo_not_started"
		elif jc.status == "On Hold":
			ui = "on_hold"
		elif has_open_log:
			ui = "running"
		else:
			ui = "not_started"

		# Planned operation time (the WO Operations "Time" column, e.g. 60 / 30 mins).
		planned_mins = 0.0
		if jc.get("operation_id"):
			planned_mins = flt(frappe.db.get_value("Work Order Operation", jc.operation_id, "time_in_mins"))
		if not planned_mins:
			planned_mins = flt(jc.get("time_required"))

		out.append(
			{
				"name": jc.name,
				"operation": jc.operation,
				"workstation": jc.workstation,
				"status": jc.status,
				"for_quantity": for_qty,
				"total_completed_qty": done_qty,
				"remaining_qty": max(for_qty - done_qty, 0.0),
				"uom": jc.get("stock_uom") or "",
				"docstatus": jc.docstatus,
				"employees": employees,
				"has_employees": bool(employees),
				"ui_state": ui,
				# times: planned (op time), actual (from time logs), and start/end stamps.
				"planned_mins": flt(planned_mins, 2),
				"actual_mins": flt(jc.get("total_time_in_mins"), 2),
				"start_time": str(jc.get("actual_start_date") or ""),
				"end_time": str(jc.get("actual_end_date") or ""),
				# Submit becomes available once some qty is completed and it's still a draft.
				"can_submit": jc.docstatus == 0 and done_qty > 0,
			}
		)
	return out


@frappe.whitelist()
def get_wo_job_cards(work_order):
	"""Refresh the Job Cards section after a Start/Hold/Resume/Finish action."""
	wo = frappe.get_doc("Work Order", work_order)
	wo.check_permission("read")
	return _wo_job_cards(wo)


@frappe.whitelist()
def run_job_card_action(job_card, action, employees=None, completed_qty=None):
	"""Start / Hold / Resume / Finish a Job Card from the transfer popup, reusing
	ERPNext's own make_time_log so behaviour + validations are identical to the Job Card
	form. Exceptions are returned as {ok: False, error: ...} (not raised) so the popup can
	show them inline next to the card. Always returns the refreshed job_cards list."""
	from erpnext.manufacturing.doctype.job_card.job_card import make_time_log
	from frappe.utils import now_datetime, strip_html_tags

	jc = frappe.get_doc("Job Card", job_card)
	jc.check_permission("write")
	wo_name = jc.work_order
	if isinstance(employees, str):
		employees = json.loads(employees or "null")

	# Submit the Job Card (docstatus 0 -> 1); ERPNext validates completeness on submit.
	if action == "submit":
		try:
			jc.submit()
			frappe.db.set_value("Job Card", jc.name, "custom_submitted_at", now_datetime(), update_modified=False)
		except Exception as e:
			frappe.db.rollback()
			msg = strip_html_tags(str(e)) or _("Could not submit the Job Card.")
			out = _wo_job_cards(frappe.get_doc("Work Order", wo_name)) if wo_name else []
			return {"ok": False, "error": msg, "job_cards": out}
		out = _wo_job_cards(frappe.get_doc("Work Order", wo_name)) if wo_name else []
		return {"ok": True, "job_cards": out}

	now = str(now_datetime())
	args = {"job_card_id": job_card}
	if action == "start":
		args.update({"start_time": now, "employees": employees or [], "status": "Work In Progress"})
	elif action == "resume":
		args.update({"start_time": now, "employees": employees or [], "status": "Resume Job"})
	elif action == "hold":
		args.update({"complete_time": now, "status": "On Hold"})
	elif action == "finish":
		args.update({"complete_time": now, "status": "Complete", "completed_qty": flt(completed_qty)})
	else:
		frappe.throw(_("Unknown Job Card action: {0}").format(action))

	try:
		make_time_log(args)
	except Exception as e:
		frappe.db.rollback()
		msg = strip_html_tags(str(e)) or _("Could not update the Job Card.")
		out = _wo_job_cards(frappe.get_doc("Work Order", wo_name)) if wo_name else []
		return {"ok": False, "error": msg, "job_cards": out}

	out = _wo_job_cards(frappe.get_doc("Work Order", wo_name)) if wo_name else []
	return {"ok": True, "job_cards": out}


# --- Plan (blueprint) ---------------------------------------------------------

def _can_set_plan(user_already_saved):
	"""Administrator / Manufacturing Manager / System Manager can set the plan any time.
	A plain Manufacturing User can MANUALLY save it only ONCE. The automatic FIFO
	blueprint saved on the first Start does not count against that allowance."""
	if frappe.session.user == "Administrator":
		return True
	roles = set(frappe.get_roles())
	if roles & {"System Manager", "Manufacturing Manager"}:
		return True
	if "Manufacturing User" in roles:
		return not user_already_saved
	return False


def _is_plain_manufacturing_user():
	if frappe.session.user == "Administrator":
		return False
	roles = set(frappe.get_roles())
	if roles & {"System Manager", "Manufacturing Manager"}:
		return False
	return "Manufacturing User" in roles


@frappe.whitelist()
def set_transfer_plan(work_order, plan, auto=0):
	"""Save the planned batch blueprint (per item) from the draft, once it covers every
	item's required qty. The plan is a suggestion only — the actual transfer can differ.

	`auto=1` is the automatic FIFO blueprint saved on the first Start click: it only
	writes when no plan exists yet, never errors (silently no-ops if it can't cover or
	one already exists), and does NOT consume the Manufacturing User's one manual save.
	A manual save (auto=0) follows the usual rule: Manufacturing User once, Manager/Admin
	any time; a successful manual save by a plain Manufacturing User uses up their turn."""
	auto = int(auto or 0)
	if isinstance(plan, str):
		plan = json.loads(plan)

	wo = frappe.get_doc("Work Order", work_order)
	wo.check_permission("read")

	user_saved = bool(wo.get("custom_plan_user_saved"))
	plan_already_set = any(r.get("custom_planned_batches") for r in wo.required_items)

	if auto:
		# First-Start auto blueprint: skip if a plan already exists or the caller can't set.
		if plan_already_set or not _can_set_plan(user_saved):
			return {"plan_set": plan_already_set, "items": 0, "can_set_plan": _can_set_plan(user_saved), "auto": 1}
	elif not _can_set_plan(user_saved):
		frappe.throw(
			_("You have already saved the plan. Only a Manufacturing Manager can change it.")
		)

	# Build the per-row planned rows; fall back to the actual transfers for items that
	# are already fully transferred (no draft rows sent for them).
	planned_by_row = {}
	for row in wo.required_items:
		rows = plan.get(row.name) or []
		clean = []
		for b in rows:
			std_pkg = flt(b.get("std_pkg"))
			units = flt(b.get("units"))
			qty = flt(std_pkg * units, 3)
			batch_no = (b.get("batch_no") or "").strip()
			if batch_no and qty > 0:
				clean.append({"batch_no": batch_no, "std_pkg": std_pkg, "units": units, "qty": qty})

		if not clean and flt(row.transferred_qty) + 0.0001 >= flt(row.required_qty):
			# already fully transferred -> use the actual transfers as the plan
			for t in _item_transfers(work_order, row.item_code):
				clean.append({"batch_no": t["batch_no"], "std_pkg": t["std_pkg"], "units": t["units"], "qty": t["qty"]})

		planned_by_row[row.name] = (row, clean)

	# Completeness: every item's planned qty must cover its required qty. On auto, an
	# incomplete plan (e.g. not enough stock) is silently skipped, not an error.
	for row, clean in planned_by_row.values():
		planned_qty = sum(flt(c["qty"]) for c in clean)
		if flt(planned_qty, 3) + 1e-6 < flt(row.required_qty, 3):
			if auto:
				return {"plan_set": False, "items": 0, "can_set_plan": _can_set_plan(user_saved), "auto": 1}
			frappe.throw(
				_("Plan for {0} ({1}) does not cover the required qty ({2}).").format(
					row.item_code, flt(planned_qty, 3), flt(row.required_qty, 3)
				)
			)

	# Save the plan (with UOM) onto each item.
	for row, clean in planned_by_row.values():
		for c in clean:
			c["uom"] = row.stock_uom
		frappe.db.set_value(
			"Work Order Item", row.name, "custom_planned_batches",
			json.dumps(clean), update_modified=False,
		)

	# A manual save by a plain Manufacturing User uses up their single allowance.
	if not auto and _is_plain_manufacturing_user():
		frappe.db.set_value("Work Order", wo.name, "custom_plan_user_saved", 1, update_modified=False)
		user_saved = True

	frappe.db.commit()
	return {"plan_set": True, "items": len(planned_by_row), "can_set_plan": _can_set_plan(user_saved), "auto": auto}


def _parse_draft(value):
	if not value:
		return []
	try:
		data = json.loads(value)
		return data if isinstance(data, list) else []
	except (ValueError, TypeError):
		return []


@frappe.whitelist()
def save_transfer_draft(work_order, drafts):
	"""Persist the popup's in-progress batch rows per item so it can be resumed later.

	`drafts` = { row_name: [ {batch_no, std_pkg, units, qty}, ... ] }. Stored as JSON on
	each Work Order Item's custom_transfer_draft (bypasses the after-submit lock).
	"""
	if isinstance(drafts, str):
		drafts = json.loads(drafts)

	wo = frappe.get_doc("Work Order", work_order)
	wo.check_permission("read")
	valid_rows = {r.name for r in wo.required_items}

	saved = 0
	for row_name, rows in (drafts or {}).items():
		if row_name not in valid_rows:
			continue
		frappe.db.set_value(
			"Work Order Item", row_name, "custom_transfer_draft",
			json.dumps(rows or []), update_modified=False,
		)
		saved += 1
	frappe.db.commit()
	return {"saved": saved}


@frappe.whitelist()
def log_addition_event(work_order, row_name, action):
	"""Log a Start/Stop time event and keep a running total of the addition time.

	No live stopwatch. "Start" records the clock time and opens an interval; "Stop"
	closes it, adds (Stop − Start) to the accumulated total, and returns that total.
	Start/Stop can continue even after the material has been transferred. The trail is
	shown against the item; the accumulated minutes are stored on the row.
	"""
	from frappe.utils import now_datetime

	wo = frappe.get_doc("Work Order", work_order)
	wo.check_permission("read")
	if row_name not in {r.name for r in wo.required_items}:
		frappe.throw(_("Required item row not found on this Work Order."))

	now = now_datetime()
	log = _append_log(row_name, action, now)
	duration = flt(frappe.db.get_value("Work Order Item", row_name, "custom_addition_duration_mins"))
	running = None

	def _close_open_interval(total):
		last_start = frappe.db.get_value("Work Order Item", row_name, "custom_addition_start")
		if last_start:
			total = flt(total + (now - get_datetime(last_start)).total_seconds() / 60.0, 3)
			frappe.db.set_value(
				"Work Order Item", row_name,
				{"custom_addition_duration_mins": total, "custom_addition_start": None},
				update_modified=False,
			)
		return total

	if action == "Start":
		# custom_addition_start acts as the open-interval marker.
		frappe.db.set_value(
			"Work Order Item", row_name, "custom_addition_start", now, update_modified=False
		)
		running = True
	elif action == "Stop":
		duration = _close_open_interval(duration)
		running = False
	elif action == "Finish":
		# Close any open interval, then lock the timer for this item.
		duration = _close_open_interval(duration)
		running = False

	frappe.db.commit()
	return {
		"addition_log": log,
		"duration_mins": duration,
		"running": running,
		"finished": "Finish —" in (log or ""),
	}


def _append_log(row_name, action, now=None):
	from frappe.utils import now_datetime

	if now is None:
		now = now_datetime()
	existing = frappe.db.get_value("Work Order Item", row_name, "custom_addition_log") or ""
	line = "%s — %s" % (action, format_datetime(now, "yyyy-MM-dd hh:mm:ss a"))
	combined = "\n".join([x for x in [existing.strip()] if x] + [line])
	frappe.db.set_value(
		"Work Order Item", row_name, "custom_addition_log", combined, update_modified=False
	)
	return combined


def _available_batches(item_code, warehouse):
	"""Batches of an item with positive on-hand qty in a warehouse (+ default pkg qty).

	Uses ERPNext's Serial-and-Batch-Bundle-aware availability (batch qty lives on the
	bundle, not directly on the Stock Ledger Entry), then keeps only positive balances.
	"""
	if not warehouse:
		return []
	from erpnext.stock.doctype.serial_and_batch_bundle.serial_and_batch_bundle import (
		get_available_batches,
	)

	rows = get_available_batches(
		frappe._dict({"item_code": item_code, "warehouse": warehouse})
	)
	# Sum per batch (rows are per batch+warehouse) and drop non-positive balances.
	agg = {}
	for r in rows:
		agg[r.batch_no] = agg.get(r.batch_no, 0.0) + flt(r.qty)

	# Fallback pkg qty when the batch has none: the item's latest GRN packing qty.
	item_default_pkg = _item_default_pkg_qty(item_code)
	out = []
	for batch_no, qty in agg.items():
		if qty <= 0.0001:
			continue
		std_pkg = (
			flt(frappe.db.get_value("Batch", batch_no, "custom_standard_pkg_qty"))
			or item_default_pkg
			or 1
		)
		out.append({"batch_no": batch_no, "available_qty": flt(qty, 3), "std_pkg": std_pkg})
	return out


def _item_transfers(work_order, item_code):
	"""All Material Transfer for Manufacture rows made for this Work Order + item, from
	the submitted Stock Entries — Stock Entry, batch, qty, and the std-pkg/units format."""
	rows = frappe.db.sql(
		"""
		SELECT sed.parent AS stock_entry, se.posting_date, se.posting_time,
		       sed.batch_no, sed.qty
		FROM `tabStock Entry Detail` sed
		INNER JOIN `tabStock Entry` se ON se.name = sed.parent
		WHERE se.work_order = %(wo)s AND se.purpose = 'Material Transfer for Manufacture'
		  AND se.docstatus = 1 AND sed.item_code = %(item)s
		  AND IFNULL(sed.batch_no, '') != ''
		  AND IFNULL(se.custom_rework_qc, '') = ''
		ORDER BY se.posting_date ASC, se.creation ASC, sed.idx ASC
		""",
		{"wo": work_order, "item": item_code},
		as_dict=True,
	)
	default_pkg = _item_default_pkg_qty(item_code)
	out = []
	for r in rows:
		std = flt(frappe.db.get_value("Batch", r.batch_no, "custom_standard_pkg_qty")) or default_pkg or 1
		out.append(
			{
				"stock_entry": r.stock_entry,
				"posting_date": str(r.posting_date or ""),
				"batch_no": r.batch_no,
				"qty": flt(r.qty, 3),
				"std_pkg": flt(std, 3),
				"units": flt(r.qty / std, 3) if std else 0,
			}
		)
	return out


def _item_default_pkg_qty(item_code):
	"""Item's Standard Pkg Qty fallback = custom_packing_qty from its most recent
	Purchase Receipt (GRN) row (the same source the Batch's std pkg is derived from)."""
	row = frappe.db.sql(
		"""
		SELECT pri.custom_packing_qty AS pkg
		FROM `tabPurchase Receipt Item` pri
		INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
		WHERE pri.item_code = %(item)s AND pr.docstatus = 1
		  AND IFNULL(pri.custom_packing_qty, 0) > 0
		ORDER BY pr.posting_date DESC, pr.creation DESC
		LIMIT 1
		""",
		{"item": item_code},
		as_dict=True,
	)
	return flt(row[0].pkg) if row else 0


@frappe.whitelist()
def transfer_item_for_manufacture(work_order, row_name, batches):
	"""Create + submit a single-item Material Transfer for Manufacture Stock Entry with
	the chosen batches, then persist the breakdown + log onto the Work Order Item."""
	if isinstance(batches, str):
		batches = json.loads(batches)
	if not batches:
		frappe.throw(_("Pick at least one batch to transfer."))

	wo = frappe.get_doc("Work Order", work_order)
	wo.check_permission("read")

	row = next((r for r in wo.required_items if r.name == row_name), None)
	if not row:
		frappe.throw(_("Required item row not found on this Work Order."))

	item_code = row.item_code
	src = row.source_warehouse or wo.source_warehouse

	# Normalize batch lines: qty = std pkg x no of units (actual taken).
	lines = []
	total_qty = 0.0
	for b in batches:
		std_pkg = flt(b.get("std_pkg"))
		units = flt(b.get("units"))
		qty = flt(std_pkg * units, 3)
		batch_no = (b.get("batch_no") or "").strip()
		if not batch_no or qty <= 0:
			continue
		lines.append({"batch_no": batch_no, "std_pkg": std_pkg, "units": units, "qty": qty})
		total_qty += qty
	if not lines or total_qty <= 0:
		frappe.throw(_("Enter Std Pkg Qty and No of Units for the chosen batch(es)."))

	# Guard: don't transfer more than remaining for this item. Compare at 3 decimals so
	# entering the on-screen remaining (shown rounded to 3 dp) isn't rejected by
	# floating-point noise beyond the 3rd decimal.
	remaining = flt(row.required_qty) - flt(row.transferred_qty)
	if flt(total_qty, 3) > flt(remaining, 3) + 1e-6:
		frappe.throw(
			_("Cannot transfer {0}: only {1} is pending for {2}.").format(
				flt(total_qty, 3), flt(remaining, 3), item_code
			)
		)

	# Guard: don't transfer more than what's on hand for each batch.
	avail = {b["batch_no"]: flt(b["available_qty"]) for b in _available_batches(item_code, src)}
	qty_by_batch = {}
	for ln in lines:
		qty_by_batch[ln["batch_no"]] = qty_by_batch.get(ln["batch_no"], 0.0) + ln["qty"]
	for batch_no, want in qty_by_batch.items():
		have = flt(avail.get(batch_no, 0))
		if flt(want, 3) > flt(have, 3) + 1e-6:
			frappe.throw(
				_("Only {0} available in batch {1} (tried to transfer {2}).").format(
					flt(have, 3), batch_no, flt(want, 3)
				)
			)

	se_name = _make_single_item_transfer(wo, item_code, src, lines)

	# Persist the batch breakdown; log a "Material Transfer" marker; clear the saved
	# draft (reset) so the operator continues fresh on any leftover qty next time. The
	# Start/Stop timer is intentionally left untouched — time logging continues after
	# the transfer.
	_save_batches_taken(row.name, lines)
	_append_actual_batches(row.name, lines, row.stock_uom)
	log = _append_log(row.name, "Material Transfer")
	frappe.db.set_value(
		"Work Order Item", row.name, "custom_transfer_draft", "", update_modified=False
	)
	# Track the last material-transfer time on the Work Order (shown below Batch Started At).
	from frappe.utils import now_datetime
	frappe.db.set_value(
		"Work Order", wo.name, "custom_last_material_transfer_at", now_datetime(), update_modified=False
	)

	# Return updated figures.
	new_transferred = flt(frappe.db.get_value("Work Order Item", row.name, "transferred_qty"))
	new_remaining = max(flt(row.required_qty) - new_transferred, 0)
	return {
		"stock_entry": se_name,
		"transferred_qty": flt(new_transferred, 3),
		"remaining_qty": flt(new_remaining, 3),
		"is_full": new_remaining <= 0.0001,
		"transfers": _item_transfers(wo.name, item_code),
		"addition_log": log,
		"duration_mins": flt(frappe.db.get_value("Work Order Item", row.name, "custom_addition_duration_mins"), 3),
	}


def _make_single_item_transfer(wo, item_code, src, lines, rework_qc=None):
	"""Build + submit a Material Transfer for Manufacture SE for one item's batches.
	When `rework_qc` is given, the SE is tagged to that rework QC (so it shows only in the
	Rework tab and is excluded from the main tab's figures)."""
	from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry

	se = frappe.get_doc(make_stock_entry(wo.name, "Material Transfer for Manufacture"))

	# Template from the target item's mapped row; rebuild items = one row per batch.
	template = next((r for r in se.items if r.item_code == item_code), None)
	if not template:
		frappe.throw(_("Item {0} is not pending transfer on this Work Order.").format(item_code))

	copy_fields = [
		"item_code", "item_name", "s_warehouse", "t_warehouse", "uom", "stock_uom",
		"conversion_factor", "expense_account", "cost_center", "bom_no", "original_item",
	]
	base = {f: template.get(f) for f in copy_fields if template.get(f) is not None}
	if src:
		base["s_warehouse"] = src

	se.set("items", [])
	for ln in lines:
		child = se.append("items", dict(base))
		child.qty = ln["qty"]
		child.transfer_qty = flt(ln["qty"]) * flt(base.get("conversion_factor") or 1)
		child.use_serial_batch_fields = 1
		child.batch_no = ln["batch_no"]

	# This is a deliberate partial, single-item transfer; per-item remaining is already
	# enforced above. Exempt it from the fg_completed_qty-based over-transfer guard
	# (which assumes a full-batch transfer).
	if rework_qc:
		se.custom_rework_qc = rework_qc
	# Per-item partial transfer: don't claim a full FG batch. Leaving fg_completed_qty at
	# the WO qty makes every transfer add wo.qty to material_transferred_for_manufacturing
	# (6 transfers -> 6x). Set 0 so the WO recomputes it from actual item transfers.
	se.fg_completed_qty = 0
	se.flags.pratap_partial_item_transfer = True
	se.flags.ignore_permissions = True
	se.insert(ignore_permissions=True)
	se.submit()
	return se.name


def _append_actual_batches(row_name, lines, uom):
	"""Append the actually-transferred batches (with UOM) as JSON on the item, for the
	future print format's 'Actual' column."""
	existing = _parse_draft(frappe.db.get_value("Work Order Item", row_name, "custom_actual_batches"))
	for ln in lines:
		existing.append(
			{"batch_no": ln["batch_no"], "std_pkg": ln["std_pkg"], "units": ln["units"], "qty": ln["qty"], "uom": uom}
		)
	frappe.db.set_value(
		"Work Order Item", row_name, "custom_actual_batches", json.dumps(existing), update_modified=False
	)


def _save_batches_taken(row_name, lines):
	"""Append the batch breakdown ("BATCH PKG UNITS" lines) to the WO Item row."""
	existing = frappe.db.get_value("Work Order Item", row_name, "custom_batches_taken") or ""
	new_lines = [
		"%s %s %s" % (ln["batch_no"], _num(ln["std_pkg"]), _num(ln["units"])) for ln in lines
	]
	combined = "\n".join([x for x in [existing.strip()] if x] + new_lines)
	frappe.db.set_value(
		"Work Order Item", row_name, "custom_batches_taken", combined, update_modified=False
	)


def _num(v):
	v = flt(v)
	return int(v) if v == int(v) else v


# --- Rework (per rework-QC material transfer + timer) -------------------------

def _rework_data(qc_name):
	"""Parse the per-item rework timer/log JSON stored on the Pratap QC."""
	raw = frappe.db.get_value("Pratap Quality Inspection", qc_name, "custom_rework_transfer_data")
	if not raw:
		return {}
	try:
		d = json.loads(raw)
		return d if isinstance(d, dict) else {}
	except (ValueError, TypeError):
		return {}


def _save_rework_data(qc_name, data):
	frappe.db.set_value(
		"Pratap Quality Inspection", qc_name, "custom_rework_transfer_data",
		json.dumps(data), update_modified=False,
	)


def _compose_log(existing, action, now=None):
	"""Append 'Action — timestamp' to a log string (does not persist)."""
	from frappe.utils import now_datetime

	if now is None:
		now = now_datetime()
	line = "%s — %s" % (action, format_datetime(now, "yyyy-MM-dd hh:mm:ss a"))
	existing = (existing or "").strip()
	return "\n".join([x for x in [existing] if x] + [line])


def _rework_transferred_qty(work_order, item_code):
	"""Total qty transferred for an item via rework-tagged Stock Entries (to keep the
	main tab's transferred/remaining figures free of rework material)."""
	v = frappe.db.sql(
		"""
		SELECT SUM(sed.qty) FROM `tabStock Entry Detail` sed
		INNER JOIN `tabStock Entry` se ON se.name = sed.parent
		WHERE se.work_order = %(wo)s AND se.purpose = 'Material Transfer for Manufacture'
		  AND se.docstatus = 1 AND IFNULL(se.custom_rework_qc, '') != '' AND sed.item_code = %(item)s
		""",
		{"wo": work_order, "item": item_code},
	)
	return flt(v[0][0]) if v and v[0][0] else 0.0


def _rework_item_transfers(work_order, qc_name, item_code):
	"""Rework transfers (SEs tagged to this QC) for an item — same shape as _item_transfers."""
	rows = frappe.db.sql(
		"""
		SELECT sed.parent AS stock_entry, se.posting_date, sed.batch_no, sed.qty
		FROM `tabStock Entry Detail` sed
		INNER JOIN `tabStock Entry` se ON se.name = sed.parent
		WHERE se.work_order = %(wo)s AND se.purpose = 'Material Transfer for Manufacture'
		  AND se.docstatus = 1 AND se.custom_rework_qc = %(qc)s
		  AND sed.item_code = %(item)s AND IFNULL(sed.batch_no, '') != ''
		ORDER BY se.posting_date ASC, se.creation ASC, sed.idx ASC
		""",
		{"wo": work_order, "qc": qc_name, "item": item_code},
		as_dict=True,
	)
	default_pkg = _item_default_pkg_qty(item_code)
	out = []
	for r in rows:
		std = flt(frappe.db.get_value("Batch", r.batch_no, "custom_standard_pkg_qty")) or default_pkg or 1
		out.append(
			{
				"stock_entry": r.stock_entry,
				"posting_date": str(r.posting_date or ""),
				"batch_no": r.batch_no,
				"qty": flt(r.qty, 3),
				"std_pkg": flt(std, 3),
				"units": flt(r.qty / std, 3) if std else 0,
			}
		)
	return out


def _wo_rework_qcs(wo):
	"""Rework Pratap QCs for this Work Order. Each shows ONLY the items added to that QC's
	Raw Materials table (not the whole WO), the QC's Rework Notes on top, and per-item a
	rework material transfer (operator-entered qty) + a Start/Stop/Finish timer."""
	names = frappe.get_all(
		"Pratap Quality Inspection",
		filters={
			"reference_type": "Work Order",
			"reference_name": wo.name,
			"status": "Rework",
			"docstatus": ["<", 2],
		},
		pluck="name",
		order_by="creation asc",
	)
	out = []
	for name in names:
		qc = frappe.get_doc("Pratap Quality Inspection", name)
		data = _rework_data(name)
		items = []
		for rm in (qc.get("raw_materials") or []):
			if not rm.item_code:
				continue
			src = rm.get("source_warehouse") or wo.source_warehouse
			has_batch = bool(frappe.db.get_value("Item", rm.item_code, "has_batch_no"))
			d = data.get(rm.item_code, {})
			log = d.get("addition_log") or ""
			items.append(
				{
					"item_code": rm.item_code,
					"item_name": rm.item_name or frappe.db.get_value("Item", rm.item_code, "item_name"),
					"uom": rm.uom or frappe.db.get_value("Item", rm.item_code, "stock_uom"),
					"required_qty": flt(rm.get("total_req_qty"), 3),
					"source_warehouse": src,
					"has_batch": has_batch,
					"batches": _available_batches(rm.item_code, src) if has_batch else [],
					"transfers": _rework_item_transfers(wo.name, name, rm.item_code),
					"duration_mins": flt(d.get("duration_mins"), 3),
					"timer_running": bool(d.get("addition_start")),
					"finished": "Finish —" in log,
					"addition_log": log,
				}
			)
		out.append(
			{
				"name": name,
				"inspection_type": qc.inspection_type,
				"status": qc.status,
				"inspection_date": str(qc.inspection_date or ""),
				"rework_notes": qc.get("rework_notes") or "",
				"items": items,
			}
		)
	return out


def _make_rework_transfer(wo, item_code, src, lines, qc):
	"""Build + submit a Material Transfer for Manufacture SE for a rework item's batches,
	tagged to the rework QC. Unlike the main transfer, the item may not be a WO required
	item, so the rows are built generically (source -> WIP) rather than from the WO map."""
	from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry

	se = frappe.get_doc(make_stock_entry(wo.name, "Material Transfer for Manufacture"))
	wip = wo.wip_warehouse
	item = frappe.get_doc("Item", item_code)

	se.set("items", [])
	for ln in lines:
		child = se.append(
			"items",
			{
				"item_code": item_code,
				"item_name": item.item_name,
				"s_warehouse": src,
				"t_warehouse": wip,
				"uom": item.stock_uom,
				"stock_uom": item.stock_uom,
				"conversion_factor": 1,
				"qty": ln["qty"],
				"transfer_qty": ln["qty"],
				"use_serial_batch_fields": 1,
				"batch_no": ln["batch_no"],
			},
		)
		child.set_basic_rate_manually = 0

	se.custom_rework_qc = qc
	se.fg_completed_qty = 0  # per-item partial transfer; don't inflate material_transferred
	se.flags.pratap_partial_item_transfer = True
	se.flags.ignore_permissions = True
	se.insert(ignore_permissions=True)
	se.submit()
	return se.name


def _validate_rework_qc(qc, wo_name):
	info = frappe.db.get_value(
		"Pratap Quality Inspection", qc,
		["reference_type", "reference_name", "status", "docstatus"], as_dict=True,
	)
	if not info or info.reference_type != "Work Order" or info.reference_name != wo_name or info.status != "Rework":
		frappe.throw(_("This is not a rework QC for this Work Order."))


@frappe.whitelist()
def get_wo_rework(work_order):
	"""Refresh the Rework tab after a transfer or timer action."""
	wo = frappe.get_doc("Work Order", work_order)
	wo.check_permission("read")
	return _wo_rework_qcs(wo)


@frappe.whitelist()
def rework_transfer_item(work_order, qc, item_code, batches):
	"""Create + submit a Material Transfer for Manufacture SE (tagged to the rework QC)
	for the chosen batches of a rework item. Operator-entered qty; no required cap (rework
	needs extra material) — only per-batch availability is enforced. The item comes from
	the rework QC's Raw Materials table (it need not be a WO required item)."""
	if isinstance(batches, str):
		batches = json.loads(batches)
	if not batches:
		frappe.throw(_("Pick at least one batch to transfer."))

	wo = frappe.get_doc("Work Order", work_order)
	wo.check_permission("read")
	_validate_rework_qc(qc, wo.name)

	qc_doc = frappe.get_doc("Pratap Quality Inspection", qc)
	rm = next((r for r in (qc_doc.get("raw_materials") or []) if r.item_code == item_code), None)
	if not rm:
		frappe.throw(_("Item {0} is not in this rework QC.").format(item_code))
	src = rm.get("source_warehouse") or wo.source_warehouse

	lines, total = [], 0.0
	for b in batches:
		std_pkg = flt(b.get("std_pkg"))
		units = flt(b.get("units"))
		qty = flt(std_pkg * units, 3)
		batch_no = (b.get("batch_no") or "").strip()
		if not batch_no or qty <= 0:
			continue
		lines.append({"batch_no": batch_no, "std_pkg": std_pkg, "units": units, "qty": qty})
		total += qty
	if not lines or total <= 0:
		frappe.throw(_("Enter Std Pkg Qty and No of Units for the chosen batch(es)."))

	avail = {b["batch_no"]: flt(b["available_qty"]) for b in _available_batches(item_code, src)}
	qty_by_batch = {}
	for ln in lines:
		qty_by_batch[ln["batch_no"]] = qty_by_batch.get(ln["batch_no"], 0.0) + ln["qty"]
	for batch_no, want in qty_by_batch.items():
		have = flt(avail.get(batch_no, 0))
		if flt(want, 3) > flt(have, 3) + 1e-6:
			frappe.throw(
				_("Only {0} available in batch {1} (tried to transfer {2}).").format(
					flt(have, 3), batch_no, flt(want, 3)
				)
			)

	se_name = _make_rework_transfer(wo, item_code, src, lines, qc)

	data = _rework_data(qc)
	d = data.setdefault(item_code, {})
	d["addition_log"] = _compose_log(d.get("addition_log"), "Material Transfer")
	_save_rework_data(qc, data)
	frappe.db.commit()

	return {
		"stock_entry": se_name,
		"transfers": _rework_item_transfers(wo.name, qc, item_code),
		"addition_log": d["addition_log"],
		"duration_mins": flt(d.get("duration_mins"), 3),
	}


@frappe.whitelist()
def rework_log_event(work_order, qc, item_code, action):
	"""Start/Stop/Finish timer for a rework item, stored per rework QC (per item)."""
	from frappe.utils import get_datetime, now_datetime

	wo = frappe.get_doc("Work Order", work_order)
	wo.check_permission("read")
	_validate_rework_qc(qc, wo.name)

	now = now_datetime()
	data = _rework_data(qc)
	d = data.setdefault(item_code, {})
	d["addition_log"] = _compose_log(d.get("addition_log"), action, now)
	duration = flt(d.get("duration_mins"))
	running = None

	def _close(total):
		start = d.get("addition_start")
		if start:
			total = flt(total + (now - get_datetime(start)).total_seconds() / 60.0, 3)
			d["addition_start"] = None
		return total

	if action == "Start":
		d["addition_start"] = str(now)
		running = True
	elif action in ("Stop", "Finish"):
		duration = _close(duration)
		running = False

	d["duration_mins"] = duration
	_save_rework_data(qc, data)
	frappe.db.commit()
	return {
		"addition_log": d["addition_log"],
		"duration_mins": duration,
		"running": running,
		"finished": "Finish —" in (d["addition_log"] or ""),
	}


# --- Time Log tab (read-only report on the Work Order form) -------------------

def _parse_log_events(log):
	"""Split an addition_log string ('Action — timestamp' lines) into structured events."""
	events = []
	for line in (log or "").split("\n"):
		line = line.strip()
		if not line or " — " not in line:
			continue
		action, ts = line.split(" — ", 1)
		events.append({"action": action.strip(), "time": ts.strip()})
	return events


def _transfer_bounds(work_order, rework):
	"""First & last material-transfer time (SE creation) for a WO — rework-tagged or not."""
	cond = "!= ''" if rework else "= ''"
	rows = frappe.db.sql(
		f"""SELECT MIN(creation) AS first_at, MAX(creation) AS last_at
		    FROM `tabStock Entry`
		    WHERE work_order = %(wo)s AND purpose = 'Material Transfer for Manufacture'
		      AND docstatus = 1 AND IFNULL(custom_rework_qc, '') {cond}""",
		{"wo": work_order}, as_dict=True,
	)
	r = rows[0] if rows else {}
	return str(r.get("first_at") or "") or None, str(r.get("last_at") or "") or None


@frappe.whitelist()
def get_wo_time_log(work_order):
	"""All time-stamps and per-item/operation logs for the Work Order 'Time Log' tab:
	batch (start / first & last transfer + per-item log), job cards (first started / last
	submitted + per-card time logs), and rework (first & last transfer + per-item log)."""
	wo = frappe.get_doc("Work Order", work_order)
	wo.check_permission("read")

	# --- Batch section ---
	b_first, b_last = _transfer_bounds(wo.name, rework=False)
	batch_items = []
	# The batch is "ended" only once every required material has been fully
	# transferred; at that point it ends at the last material transfer time.
	batch_complete = True
	any_required = False
	for row in wo.required_items:
		if not row.item_code:
			continue
		req = flt(row.required_qty)
		if req > 0:
			any_required = True
			transferred = flt(row.transferred_qty) - _rework_transferred_qty(wo.name, row.item_code)
			if transferred + 1e-6 < req:
				batch_complete = False
		log = row.get("custom_addition_log") or ""
		if not (log or _item_transfers(wo.name, row.item_code)):
			pass  # still list it so the dropdown is complete
		batch_items.append(
			{
				"row": row.name,
				"item_code": row.item_code,
				"item_name": row.item_name,
				"uom": row.stock_uom,
				"duration_mins": flt(row.get("custom_addition_duration_mins"), 2),
				"events": _parse_log_events(log),
				"transfers": _item_transfers(wo.name, row.item_code),
			}
		)
	batch_ended = b_last if (any_required and batch_complete) else None

	# --- Job Cards section ---
	jc_names = frappe.get_all(
		"Job Card", filters={"work_order": wo.name, "docstatus": ["<", 2]},
		pluck="name", order_by="sequence_id asc, creation asc",
	)
	job_cards = []
	first_started = None
	last_submitted = None
	any_unsubmitted = False
	for name in jc_names:
		jc = frappe.get_doc("Job Card", name)
		started = str(jc.get("actual_start_date") or "") or None
		ended = str(jc.get("actual_end_date") or "") or None
		submitted = None
		if jc.docstatus == 1:
			submitted = str(jc.get("custom_submitted_at") or jc.get("modified") or "") or None
		else:
			any_unsubmitted = True
		if started and (first_started is None or started < first_started):
			first_started = started
		if submitted and (last_submitted is None or submitted > last_submitted):
			last_submitted = submitted
		logs = []
		for tl in (jc.get("time_logs") or []):
			logs.append(
				{
					"from_time": str(tl.from_time or ""),
					"to_time": str(tl.to_time or ""),
					"mins": flt(tl.time_in_mins, 2),
					"employee": tl.employee,
					"employee_name": frappe.db.get_value("Employee", tl.employee, "employee_name") if tl.employee else "",
					"completed_qty": flt(tl.completed_qty, 3),
				}
			)
		job_cards.append(
			{
				"name": jc.name,
				"operation": jc.operation,
				"workstation": jc.workstation,
				"status": jc.status,
				"started": started,
				"ended": ended,
				"submitted": submitted,
				"total_time_in_mins": flt(jc.get("total_time_in_mins"), 2),
				"time_logs": logs,
			}
		)

	# "Last Job Card Submitted" is meaningful only once every job card is submitted.
	if any_unsubmitted or not jc_names:
		last_submitted = None

	# --- Rework section (per rework QC) ---
	rw_first, rw_last = _transfer_bounds(wo.name, rework=True)
	rework = []
	for qc in _wo_rework_qcs(wo):
		items = []
		for it in qc["items"]:
			items.append(
				{
					"item_code": it["item_code"],
					"item_name": it["item_name"],
					"uom": it["uom"],
					"duration_mins": it["duration_mins"],
					"events": _parse_log_events(it["addition_log"]),
					"transfers": it["transfers"],
				}
			)
		rework.append(
			{
				"name": qc["name"],
				"status": qc["status"],
				"rework_notes": qc.get("rework_notes") or "",
				"items": items,
			}
		)

	return {
		"batch": {
			"start_batch": str(wo.get("custom_batch_started_at") or "") or None,
			"batch_ended": batch_ended,
			"first_transfer": b_first,
			"last_transfer": b_last,
			"items": batch_items,
		},
		"job_cards": {
			"first_started": first_started,
			"last_submitted": last_submitted,
			"list": job_cards,
		},
		"rework": {
			"first_transfer": rw_first,
			"last_transfer": rw_last,
			"qcs": rework,
		},
	}
