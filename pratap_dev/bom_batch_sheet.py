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


# Scalar batch-sheet fields that mirror BOM -> Work Order.
_BATCH_SHEET_SCALARS = [
	"custom_remarks",
	"custom_shelf_life",
	"custom_sample_qty_prepared",
	"custom_total_percentage",
	"custom_min_batch_quantity",
	"custom_effective_date",
]


@frappe.whitelist()
def refresh_batch_details_from_bom(work_order):
	"""Pull the batch-sheet fields + Notes table from the BOM onto an existing Work
	Order — including SUBMITTED ones.

	fetch_from only populates these at creation; a Work Order made before the BOM was
	filled stays blank. This lets the user re-sync on demand. Writes go through
	frappe.db.set_value / direct child rows so they apply regardless of docstatus
	(these are descriptive fields with no stock/ledger impact).
	"""
	wo = frappe.get_doc("Work Order", work_order)
	wo.check_permission("read")
	if not wo.bom_no:
		frappe.throw(_("This Work Order has no BOM to fetch batch details from."))

	bom_meta = frappe.get_meta("BOM")
	wo_meta = frappe.get_meta("Work Order")

	# Scalars: copy each field the BOM and Work Order both have.
	values = {}
	for fieldname in _BATCH_SHEET_SCALARS:
		if bom_meta.has_field(fieldname) and wo_meta.has_field(fieldname):
			values[fieldname] = frappe.db.get_value("BOM", wo.bom_no, fieldname)
	if values:
		frappe.db.set_value("Work Order", work_order, values, update_modified=False)

	# Notes table: replace the Work Order's rows with the BOM's.
	notes = []
	if wo_meta.has_field("custom_notes"):
		frappe.db.delete(
			"Pratap BOM Note",
			{"parent": work_order, "parenttype": "Work Order", "parentfield": "custom_notes"},
		)
		notes = _get_bom_notes(wo.bom_no)
		for idx, note in enumerate(notes, start=1):
			frappe.get_doc(
				{
					"doctype": "Pratap BOM Note",
					"parent": work_order,
					"parenttype": "Work Order",
					"parentfield": "custom_notes",
					"idx": idx,
					"note": note,
				}
			).insert(ignore_permissions=True)

	frappe.db.commit()
	return {"scalars": len(values), "notes": len(notes)}
