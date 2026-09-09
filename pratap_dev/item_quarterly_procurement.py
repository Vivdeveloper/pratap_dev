# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Quarterly average procurement per item (incl. alternates).

For each item that is the MAIN item of an Item Alternative group, compute the average
monthly received quantity over the last COMPLETED quarter:

    avg = SUM(received qty of the item + all its alternates in the quarter) / 3 months

and store it on the Item in custom_quarterly_avg_procurement. Triggered manually from a
global button on the Item list (a quarterly cron will call the same function later).
"""

import frappe
from frappe.utils import flt, getdate, add_months, get_first_day, get_last_day, today

AVG_FIELD = "custom_quarterly_avg_procurement"
QUARTER_MONTHS = 3


def get_last_completed_quarter(ref_date=None):
	"""Return (start_date, end_date, label) of the last COMPLETED quarter before ref_date.

	Quarters: Jan-Mar, Apr-Jun, Jul-Sep, Oct-Dec. If today is in Q3 (Jul-Sep), the last
	completed quarter is Q2 (Apr-Jun).
	"""
	d = getdate(ref_date or today())
	# first month of the current quarter (1,4,7,10)
	q_start_month = ((d.month - 1) // 3) * 3 + 1
	current_q_first = getdate(f"{d.year}-{q_start_month:02d}-01")
	# step back one quarter
	prev_q_ref = add_months(current_q_first, -3)
	start = get_first_day(prev_q_ref)
	end = get_last_day(add_months(start, 2))
	q_no = (start.month - 1) // 3 + 1
	return start, end, f"Q{q_no} {start.year}"


def _alternate_group(item_code):
	"""Item + all its alternates (from Item Alternative, both directions), de-duplicated."""
	group = {item_code}
	for r in frappe.get_all(
		"Item Alternative", filters={"item_code": item_code}, fields=["alternative_item_code"]
	):
		if r.alternative_item_code:
			group.add(r.alternative_item_code)
	# two-way alternates may list this item as the alternative side
	for r in frappe.get_all(
		"Item Alternative",
		filters={"alternative_item_code": item_code, "two_way": 1},
		fields=["item_code"],
	):
		if r.item_code:
			group.add(r.item_code)
	return list(group)


def _received_qty(item_codes, start, end):
	"""Total received qty (submitted Purchase Receipts) for the items in [start, end]."""
	if not item_codes:
		return 0.0
	rows = frappe.db.sql(
		"""
		SELECT SUM(pri.qty) AS qty
		FROM `tabPurchase Receipt Item` pri
		INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
		WHERE pr.docstatus = 1
		  AND pr.posting_date BETWEEN %(start)s AND %(end)s
		  AND pri.item_code IN %(items)s
		""",
		{"items": tuple(item_codes), "start": start, "end": end},
		as_dict=True,
	)
	return flt(rows[0].qty) if rows else 0.0


def compute_quarterly_avg(item_code, ref_date=None):
	"""Monthly-average received qty for an item's alternate group over the last completed
	quarter = total received (item + alternates) / 3."""
	start, end, label = get_last_completed_quarter(ref_date)
	group = _alternate_group(item_code)
	total = _received_qty(group, start, end)
	avg = flt(total / QUARTER_MONTHS, 3)
	return {"item_code": item_code, "avg": avg, "total": total, "group": group, "quarter": label,
	        "start": str(start), "end": str(end)}


def _main_items():
	"""Distinct MAIN items of Item Alternative groups (the item_code side)."""
	return list({
		r.item_code
		for r in frappe.get_all("Item Alternative", fields=["item_code"])
		if r.item_code
	})


@frappe.whitelist()
def update_quarterly_avg(item_codes=None, ref_date=None):
	"""Compute + save custom_quarterly_avg_procurement for the given items (or for ALL main
	items of Item Alternative groups when none are passed). Saved on the MAIN item only.
	Returns a summary the list-view button can show."""
	import json

	if isinstance(item_codes, str):
		item_codes = json.loads(item_codes) if item_codes.strip().startswith("[") else [item_codes]

	# Only main items (item_code side of an Item Alternative) get a value.
	main_items = set(_main_items())
	if item_codes:
		targets = [i for i in item_codes if i in main_items]
	else:
		targets = list(main_items)

	updated = 0
	reorder_rows_set = 0
	details = []
	quarter_label = None
	for item in targets:
		res = compute_quarterly_avg(item, ref_date)
		quarter_label = res["quarter"]
		frappe.db.set_value("Item", item, AVG_FIELD, res["avg"], update_modified=False)
		# Also push the same figure into the item's Auto re-order table (Re-order Qty), so
		# the reorder quantity reflects the last quarter's monthly-average procurement.
		reorder_rows = frappe.get_all(
			"Item Reorder", filters={"parent": item, "parenttype": "Item"}, pluck="name"
		)
		for rname in reorder_rows:
			frappe.db.set_value(
				"Item Reorder", rname, "warehouse_reorder_qty", res["avg"], update_modified=False
			)
			reorder_rows_set += 1
		updated += 1
		details.append({"item_code": item, "avg": res["avg"], "total": res["total"],
		                "alternates": len(res["group"]) - 1, "reorder_rows": len(reorder_rows)})
	frappe.db.commit()

	skipped = len(item_codes) - updated if item_codes else 0
	return {
		"updated": updated,
		"reorder_rows_set": reorder_rows_set,
		"skipped": skipped,
		"quarter": quarter_label,
		"details": details[:50],
	}
