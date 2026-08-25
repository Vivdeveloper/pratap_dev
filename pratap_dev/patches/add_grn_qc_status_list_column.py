# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Show a "QC Status" column on the GRN (Purchase Receipt) list.

If the site has a pinned List View Settings for Purchase Receipt, insert the
custom_qc_status column right after the Status column. Idempotent.
"""

import json

import frappe


def execute():
	if not frappe.db.exists("List View Settings", "Purchase Receipt"):
		return

	lvs = frappe.get_doc("List View Settings", "Purchase Receipt")
	try:
		fields = json.loads(lvs.fields or "[]")
	except (ValueError, TypeError):
		return

	if any(f.get("fieldname") == "custom_qc_status" for f in fields):
		return

	idx = next(
		(i for i, f in enumerate(fields) if f.get("fieldname") == "status_field"), len(fields) - 1
	)
	fields.insert(idx + 1, {"fieldname": "custom_qc_status", "label": "QC Status"})
	lvs.fields = json.dumps(fields)
	lvs.save(ignore_permissions=True)
