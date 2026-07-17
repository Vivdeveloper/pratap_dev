import json

import frappe
from erpnext.manufacturing.doctype.bom.bom import item_query as bom_item_query


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
