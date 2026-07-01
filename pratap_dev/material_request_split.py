# Copyright (c) 2026, pratap_dev contributors
# License: MIT
"""Split Material Request item rows whose qty exceeds a fixed threshold.

Any item row with qty greater than MR_ROW_QTY_THRESHOLD is broken into
multiple rows for the same item, each capped at the threshold, with the
remaining quantity carried into new rows (e.g. 1,312,778 -> 470000 + 470000 + 372778).
The operation is idempotent: rows already at/below the threshold are left as-is.
"""

import frappe
from frappe.utils import flt

MR_ROW_QTY_THRESHOLD = 470000

# Fields that must never be copied onto a freshly created split row.
_SKIP_FIELDS = {
	"name",
	"idx",
	"qty",
	"creation",
	"modified",
	"modified_by",
	"owner",
	"docstatus",
}


def split_rows_over_threshold(doc, method=None):
	threshold = MR_ROW_QTY_THRESHOLD
	if threshold <= 0 or not doc.get("items"):
		return

	if not any(flt(row.qty) > threshold for row in doc.items):
		return

	rebuilt = []
	for row in doc.items:
		qty = flt(row.qty)
		if qty <= threshold:
			rebuilt.append(row)
			continue

		remaining = qty
		first = True
		while remaining > 0:
			chunk = min(remaining, threshold)
			if first:
				row.qty = chunk
				rebuilt.append(row)
				first = False
			else:
				rebuilt.append(_make_split_row(doc, row, chunk))
			remaining = flt(remaining) - chunk

	for index, row in enumerate(rebuilt, start=1):
		row.idx = index

	doc.items = rebuilt


def _make_split_row(doc, source_row, qty):
	data = source_row.as_dict()
	for field in _SKIP_FIELDS:
		data.pop(field, None)

	new_row = frappe.new_doc("Material Request Item")
	new_row.update(data)
	new_row.qty = qty
	new_row.parent = doc.name
	new_row.parenttype = doc.doctype
	new_row.parentfield = source_row.parentfield or "items"
	return new_row
