import json

import frappe
from frappe import _
from frappe.utils import flt
from erpnext.manufacturing.doctype.bom.bom import item_query as bom_item_query


def validate_bom_total_qty(doc, method=None):
	"""Ensure the sum of BOM Item quantities equals the BOM's total Quantity.

	Pratap BOMs are formulations, so the produced Quantity must equal the sum of
	the ingredient quantities. Runs on validate (before save), so a mismatch blocks
	the save.
	"""
	total_qty = flt(doc.quantity)
	items_qty = sum(flt(row.qty) for row in (doc.items or []))

	# tolerance for float rounding
	if abs(items_qty - total_qty) > 0.001:
		frappe.throw(
			_(
				"Total of BOM Item quantities ({0}) must equal the BOM Quantity ({1}). "
				"Difference: {2}."
			).format(items_qty, total_qty, abs(items_qty - total_qty)),
			title=_("BOM Quantity Mismatch"),
		)


@frappe.whitelist()
def item_group_filtered_item_query(doctype, txt, searchfield, start, page_len, filters, **kwargs):
	if isinstance(filters, str):
		filters = json.loads(filters)
	filters = filters or {}

	item_group = filters.pop("item_group_filter", None)
	if item_group and frappe.db.exists("Item Group", item_group):
		groups = frappe.db.get_descendants("Item Group", item_group) or []
		filters["item_group"] = ["in", groups + [item_group]]

	return bom_item_query(doctype, txt, searchfield, start, page_len, filters)
