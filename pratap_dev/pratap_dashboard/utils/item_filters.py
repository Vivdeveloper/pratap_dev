# Copyright (c) 2026, saurabh@exacuer.com and contributors
# For license information, please see license.txt

import frappe


ITEM_ATTR_FILTERS = (
	"item_code",
	"custom_erp",
	"custom_category_type",
	"custom_material_base",
	"custom_product_type",
	"custom_product_category",
)


def get_parents_for_item_filters(filters, child_doctype, parenttype, parentfield=None, item_link_field="item_code"):
	"""Return parent names matching item / item-master attribute filters, or None if unused."""
	if not any(filters.get(field) for field in ITEM_ATTR_FILTERS):
		return None

	ItemRow = frappe.qb.DocType(child_doctype)
	Item = frappe.qb.DocType("Item")
	query = (
		frappe.qb.from_(ItemRow)
		.inner_join(Item)
		.on(Item.name == ItemRow[item_link_field])
		.select(ItemRow.parent)
		.distinct()
		.where(ItemRow.parenttype == parenttype)
	)
	if parentfield:
		query = query.where(ItemRow.parentfield == parentfield)

	field_map = {
		"item_code": ItemRow[item_link_field],
		"custom_erp": Item.custom_erp,
		"custom_category_type": Item.custom_category_type,
		"custom_material_base": Item.custom_material_base,
		"custom_product_type": Item.custom_product_type,
		"custom_product_category": Item.custom_product_category,
	}
	for filter_name, field in field_map.items():
		if filters.get(filter_name):
			query = query.where(field == filters[filter_name])

	return query.run(pluck=True)
