# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Batch-sheet fields on BOM that flow to the Work Order.

BOM carries Remarks, Shelf Life, Sample Qty Prepared, Total Percentage, Minimum
Batch Quantity, Effective Date and a Notes table. The scalar fields flow to the
Work Order via ``fetch_from`` (set in the custom field JSON); the Notes table is
copied here (tables can't use fetch_from). Two rules are enforced:

* BOM Effective Date defaults to today and cannot be set to a past date.
* Work Order Qty to Manufacture must be >= the BOM's Minimum Batch Quantity.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today


def validate_bom_effective_date(doc, method=None):
	"""Default Effective Date to today; block any past date (only today/future)."""
	if not doc.meta.has_field("custom_effective_date"):
		return

	if not doc.custom_effective_date:
		doc.custom_effective_date = today()
		return

	# Only enforce when the value is new or actually changed, so re-saving an old
	# BOM whose date is now in the past doesn't get blocked.
	changed = doc.is_new() or doc.has_value_changed("custom_effective_date")
	if changed and getdate(doc.custom_effective_date) < getdate(today()):
		frappe.throw(
			_("Effective Date cannot be in the past. Pick today ({0}) or a future date.").format(
				frappe.utils.formatdate(today())
			),
			title=_("Invalid Effective Date"),
		)


def sync_work_order_batch_sheet(doc, method=None):
	"""On the Work Order: copy the BOM Notes table across and enforce Min Batch Qty."""
	if not doc.meta.has_field("custom_min_batch_quantity"):
		return

	# Minimum Batch Quantity: Qty to Manufacture must be >= the BOM's min batch qty.
	min_batch_qty = flt(doc.get("custom_min_batch_quantity"))
	if min_batch_qty > 0 and flt(doc.qty) + 1e-9 < min_batch_qty:
		frappe.throw(
			_(
				"Qty to Manufacture ({0}) is less than the Minimum Batch Quantity ({1}) "
				"defined on the BOM. Enter at least {1}."
			).format(flt(doc.qty), min_batch_qty),
			title=_("Below Minimum Batch Quantity"),
		)

	# Notes table flows from the BOM. Copy it in when the WO has none yet (fresh WO or
	# a just-changed BOM cleared by the client), so it mirrors the BOM at selection.
	if doc.meta.has_field("custom_notes") and doc.bom_no and not doc.get("custom_notes"):
		for row in _get_bom_notes(doc.bom_no):
			doc.append("custom_notes", {"note": row})


def _get_bom_notes(bom_no):
	"""Return the BOM's note strings, in order."""
	if not bom_no or not frappe.get_meta("BOM").has_field("custom_notes"):
		return []
	rows = frappe.get_all(
		"Pratap BOM Note",
		filters={"parent": bom_no, "parenttype": "BOM", "parentfield": "custom_notes"},
		fields=["note"],
		order_by="idx asc",
	)
	return [r.note for r in rows if r.note]


@frappe.whitelist()
def get_bom_batch_sheet(bom_no):
	"""Notes for a BOM — used by the Work Order client script to populate the grid
	immediately when the BOM is selected/changed (before save)."""
	return {"notes": _get_bom_notes(bom_no)}
