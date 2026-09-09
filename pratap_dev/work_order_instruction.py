import frappe

INSTRUCTION_FIELDS = ("custom_operation_instruction", "custom_operation_instruction_marathi")


def _instructions_by_item_code(bom_no):
	return {
		d.item_code: d
		for d in frappe.get_all(
			"BOM Item",
			filters={"parent": bom_no, "parenttype": "BOM"},
			fields=["item_code", *INSTRUCTION_FIELDS],
		)
	}


@frappe.whitelist()
def get_bom_operation_instructions(bom_no):
	"""Instructions keyed by item_code, so the form can fill the grid before saving."""
	if not bom_no:
		return {}

	return _instructions_by_item_code(bom_no)


def set_operation_instructions(doc, method=None):
	"""Copy the Operation Instruction columns from BOM Item onto Required Items.

	ERPNext builds required_items via get_bom_items_as_dict, which selects a fixed
	column list and so never carries custom fields across.
	"""
	rows = doc.get("required_items") or []
	if not doc.bom_no or not rows:
		return

	instructions = _instructions_by_item_code(doc.bom_no)

	for row in rows:
		# A multi-level BOM explodes sub-assemblies, so some rows have no BOM Item
		# row on this BOM; leave those blank rather than clearing nothing.
		source = instructions.get(row.item_code)
		for fieldname in INSTRUCTION_FIELDS:
			row.set(fieldname, source.get(fieldname) if source else None)
