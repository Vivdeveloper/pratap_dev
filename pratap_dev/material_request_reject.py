import json

import frappe
from frappe import _

# Child-row fields that must never be carried onto the new document (identity /
# system columns). Everything else on the selected rows is copied as-is.
_ROW_SKIP_FIELDS = {
	"name",
	"owner",
	"creation",
	"modified",
	"modified_by",
	"docstatus",
	"idx",
	"parent",
	"parentfield",
	"parenttype",
}


@frappe.whitelist()
def reject_items_to_new_mr(source_name, item_rows):
	"""Move the given item rows off ``source_name`` onto a fresh Material Request.

	Returns the name of the newly created (draft) Material Request. The selected
	rows are removed from the source and the source is saved.
	"""
	if isinstance(item_rows, str):
		item_rows = json.loads(item_rows)
	item_rows = set(item_rows or [])
	if not item_rows:
		frappe.throw(_("No items selected"))

	source = frappe.get_doc("Material Request", source_name)
	source.check_permission("write")

	selected = [d for d in source.items if d.name in item_rows]
	if not selected:
		frappe.throw(_("Selected items were not found on {0}").format(source_name))
	if len(selected) == len(source.items):
		frappe.throw(
			_("Cannot reject all items — at least one item must remain on this Material Request.")
		)

	# --- Build the new Material Request carrying the selected rows.
	new_mr = frappe.new_doc("Material Request")
	new_mr.material_request_type = source.material_request_type
	new_mr.company = source.company
	new_mr.transaction_date = frappe.utils.nowdate()
	new_mr.schedule_date = source.schedule_date
	if source.get("set_warehouse"):
		new_mr.set_warehouse = source.set_warehouse

	# Pre-fill "Requested by user" with a valid User id so the site's before-save
	# server script (which otherwise stuffs a full name into this User link) is
	# skipped and insert doesn't hit a LinkValidationError.
	if new_mr.meta.has_field("custom_requested_by_user"):
		requested_by = source.get("custom_requested_by_user")
		if not requested_by or not frappe.db.exists("User", requested_by):
			requested_by = frappe.session.user
		new_mr.custom_requested_by_user = requested_by

	for row in selected:
		new_row = new_mr.append("items", {})
		for fieldname, value in row.as_dict().items():
			if fieldname in _ROW_SKIP_FIELDS:
				continue
			new_row.set(fieldname, value)

	new_mr.insert()

	# --- Drop the selected rows from the source and renumber the rest.
	remaining = [d for d in source.items if d.name not in item_rows]
	source.items = remaining
	for idx, row in enumerate(remaining):
		row.idx = idx + 1
	# The source may already carry a stale "Requested by user" (the site's server
	# script stores a full name into this User link); don't let re-validating a
	# field we didn't touch block the item move.
	source.flags.ignore_links = True
	source.save()

	frappe.db.commit()
	return new_mr.name
