import frappe
from erpnext.manufacturing.doctype.bom.bom import item_query as bom_item_query

RAW_MATERIAL_ROOT = "Raw Material"


def _get_raw_material_groups():
	if not frappe.db.exists("Item Group", RAW_MATERIAL_ROOT):
		return []
	groups = frappe.db.get_descendants("Item Group", RAW_MATERIAL_ROOT) or []
	return groups + [RAW_MATERIAL_ROOT]


@frappe.whitelist()
def raw_material_item_query(doctype, txt, searchfield, start, page_len, filters, **kwargs):
	import json

	if isinstance(filters, str):
		filters = json.loads(filters)
	filters = filters or {}

	raw_groups = _get_raw_material_groups()
	# Only restrict when the group tree exists; otherwise fall back to the standard
	# behaviour instead of returning an empty list.
	if raw_groups:
		filters["item_group"] = ["in", raw_groups]

	return bom_item_query(doctype, txt, searchfield, start, page_len, filters)
