# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""RFQ supplier portal (/rfq/<name>) → Supplier Quotation.

The portal lets a supplier enter, per item, a Standard Pkg Qty and No of Unit; Qty
is auto-computed (pkg x units). ERPNext's core ``create_supplier_quotation`` copies
only a fixed field list when mapping RFQ items to the Supplier Quotation and drops
these two custom fields, so we wrap it here and write them onto the created Supplier
Quotation items afterwards (matched by request_for_quotation_item).
"""

import json

import frappe
from frappe.utils import flt


@frappe.whitelist()
def create_supplier_quotation(doc):
	from erpnext.buying.doctype.request_for_quotation.request_for_quotation import (
		create_supplier_quotation as _core_create_supplier_quotation,
	)

	if isinstance(doc, str):
		doc = json.loads(doc)

	sq_name = _core_create_supplier_quotation(doc)
	if not sq_name:
		return sq_name

	# Map the portal-entered Std Pkg Qty / No of Unit onto the new SQ items.
	src_by_rqi = {}
	for item in doc.get("items") or []:
		rqi = item.get("name")
		if rqi:
			src_by_rqi[rqi] = item

	sq = frappe.get_doc("Supplier Quotation", sq_name)
	changed = False
	for row in sq.items:
		src = src_by_rqi.get(row.request_for_quotation_item)
		if not src:
			continue
		pkg = flt(src.get("custom_packing_qty"))
		units = flt(src.get("custom_total_qty"))
		if pkg and row.meta.has_field("custom_packing_qty"):
			row.custom_packing_qty = flt(pkg, 3)
			changed = True
		if units and row.meta.has_field("custom_total_qty"):
			row.custom_total_qty = flt(units, 3)
			changed = True

	if changed:
		sq.flags.ignore_permissions = True
		sq.save()

	return sq_name
