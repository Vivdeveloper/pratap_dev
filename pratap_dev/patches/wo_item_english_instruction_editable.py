# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Make the Work Order Item "Operation Instruction English" field editable on the Work Order
(including In-Process / submitted WOs) so the operator can type/override it; BOM only seeds
it. Both instruction fields are also made allow_on_submit so they can be edited / translated
after the WO is submitted. The Marathi field stays read-only (it is auto-filled by the live
English->Marathi translation — see work_order_override.js). Idempotent."""

import frappe

DT = "Work Order Item"
ENGLISH = "custom_operation_instruction"
MARATHI = "custom_operation_instruction_marathi"


def _set_property(fieldname, prop, value, property_type):
	"""Apply a field-property override via a Property Setter (get_meta applies it last, so it
	survives any re-sync of the Custom Field during migrate). Also mirror it on the Custom
	Field directly for good measure."""
	cf = frappe.db.get_value("Custom Field", {"dt": DT, "fieldname": fieldname}, "name")
	if cf:
		frappe.db.set_value("Custom Field", cf, prop, value, update_modified=False)

	existing = frappe.db.get_value(
		"Property Setter", {"doc_type": DT, "field_name": fieldname, "property": prop}, "name"
	)
	if existing:
		frappe.db.set_value("Property Setter", existing, "value", str(value))
	else:
		frappe.make_property_setter(
			{
				"doctype": DT,
				"fieldname": fieldname,
				"property": prop,
				"value": str(value),
				"property_type": property_type,
			}
		)


def execute():
	# English: editable + editable after submit.
	_set_property(ENGLISH, "read_only", 0, "Check")
	_set_property(ENGLISH, "allow_on_submit", 1, "Check")
	# Marathi: stays read-only, but allow_on_submit so the translation can write it post-submit.
	_set_property(MARATHI, "allow_on_submit", 1, "Check")
	frappe.clear_cache(doctype=DT)

	# Make the Required Items grid itself editable after submit, otherwise the grid is frozen
	# on an In-Process WO and a cell click only opens the row popup (no inline edit). With the
	# table allow_on_submit, ONLY the child fields that are themselves allow_on_submit become
	# editable inline (our instruction fields); qty / warehouse / transferred_qty stay frozen
	# because they are allow_on_submit = 0.
	existing = frappe.db.get_value(
		"Property Setter",
		{"doc_type": "Work Order", "field_name": "required_items", "property": "allow_on_submit"},
		"name",
	)
	if existing:
		frappe.db.set_value("Property Setter", existing, "value", "1")
	else:
		frappe.make_property_setter(
			{
				"doctype": "Work Order",
				"fieldname": "required_items",
				"property": "allow_on_submit",
				"value": "1",
				"property_type": "Check",
			}
		)
	frappe.clear_cache(doctype="Work Order")
