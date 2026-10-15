# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Move the QC sample fields (inspected_qty = "Sample Issued Qty for QC", sample_issued_by)
into the new collapsible "Qc Section" at the very TOP of Pratap Quality Inspection.

The doctype JSON already defines the section + the new order, but a doctype-level
`field_order` Property Setter (created by Customize Form on prod) overrides the JSON order.
This patch rewrites that Property Setter so the Qc Section + its two fields lead the form.
No-op when the Property Setter is absent (then the JSON order already governs). Idempotent."""

import json

import frappe

DOCTYPE = "Pratap Quality Inspection"
TOP = ["custom_qc_section", "inspected_qty", "sample_issued_by", "custom_qc_section_end"]
DROP = ["column_break_1"]  # removed when the sample fields moved out


def execute():
	ps_name = frappe.db.get_value(
		"Property Setter",
		{"doc_type": DOCTYPE, "property": "field_order", "doctype_or_field": "DocType"},
		"name",
	)
	if not ps_name:
		# No override -> the doctype JSON field_order already places the Qc Section on top.
		return

	value = frappe.db.get_value("Property Setter", ps_name, "value")
	try:
		order = json.loads(value or "[]")
	except (ValueError, TypeError):
		return
	if not isinstance(order, list):
		return

	rest = [f for f in order if f not in TOP and f not in DROP]
	new_order = TOP + rest
	if new_order == order:
		return

	frappe.db.set_value("Property Setter", ps_name, "value", json.dumps(new_order))
	frappe.clear_cache(doctype=DOCTYPE)
