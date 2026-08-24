# Copyright (c) 2026, pratap_dev contributors
# License: MIT

import frappe
from frappe.utils import flt


@frappe.whitelist()
def get_bundle_batches(bundle):
	"""Return the batches (and qty) inside a Serial and Batch Bundle.

	Used by the Stock Entry UI to show, per row, which batch(es) a bundle contains
	and how much each holds. Qty is shown as a magnitude (bundles on a source row
	store negative/outward qtys).
	"""
	if not bundle:
		return []

	rows = frappe.get_all(
		"Serial and Batch Entry",
		filters={"parent": bundle, "parenttype": "Serial and Batch Bundle"},
		fields=["batch_no", "qty", "warehouse"],
		order_by="idx asc",
	)

	# Sum per batch in case the same batch appears in more than one entry row.
	agg = {}
	order = []
	for r in rows:
		if not r.batch_no:
			continue
		if r.batch_no not in agg:
			agg[r.batch_no] = 0.0
			order.append(r.batch_no)
		agg[r.batch_no] += abs(flt(r.qty))

	return [{"batch_no": b, "qty": flt(agg[b], 3)} for b in order]
