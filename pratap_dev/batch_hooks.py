# Copyright (c) 2026, pratap_dev contributors
# License: MIT
"""Keep Batch's No of Unit consistent with its own Batch Quantity.

No of Unit = Batch Quantity / Standard Pkg Qty (e.g. 10000 / 52 = 192.31).
Recomputed whenever the Batch is saved so it always reflects the current batch qty.
"""

import frappe
from frappe.utils import flt


def set_batch_no_of_unit(doc, method=None):
	meta = doc.meta
	if not meta.has_field("custom_no_of_unit") or not meta.has_field("custom_standard_pkg_qty"):
		return

	pkg = flt(doc.get("custom_standard_pkg_qty"))
	batch_qty = flt(doc.get("batch_qty"))
	doc.custom_no_of_unit = (batch_qty / pkg) if pkg else 0


@frappe.whitelist()
def backfill_batch_no_of_unit():
	"""Recompute No of Unit for all batches that have a Standard Pkg Qty set."""
	batches = frappe.get_all(
		"Batch",
		filters={"custom_standard_pkg_qty": [">", 0]},
		fields=["name", "batch_qty", "custom_standard_pkg_qty"],
	)
	updated = 0
	for b in batches:
		pkg = flt(b.custom_standard_pkg_qty)
		if not pkg:
			continue
		frappe.db.set_value(
			"Batch",
			b.name,
			"custom_no_of_unit",
			flt(b.batch_qty) / pkg,
			update_modified=False,
		)
		updated += 1
	frappe.db.commit()
	return {"updated": updated}
