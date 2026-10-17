# Copyright (c) 2026, pratap_dev contributors
# License: MIT

# Asset Maintenance Log — Maintenance Checklist copied from its Asset Maintenance.
# ERPNext creates/updates the logs itself when an Asset Maintenance is saved, so the
# copy happens server-side:
#   * a draft log with an empty checklist is filled from its Asset Maintenance;
#   * saving an Asset Maintenance refreshes its draft logs whose checklist has no
#     status/observation entered yet (so a template change reaches pending logs).
# Submitted logs and logs where the technician has started recording are never touched.

import frappe
from frappe import _

CHECKLIST_FIELD = "maintenance_checklists"
# Child tables behind CHECKLIST_FIELD on Asset Maintenance (plan) and its Log (results).
ASSET_MAINTENANCE_CHECKLIST = "Asset Maintenance Checklist"


def fill_log_checklist(doc, method=None):
	"""Asset Maintenance Log validate: fill an empty draft checklist from its Asset Maintenance."""
	if doc.docstatus != 0 or not doc.asset_maintenance or doc.get(CHECKLIST_FIELD):
		return
	_set_rows(doc, _checklist_rows(doc.asset_maintenance))


def sync_draft_log_checklists(doc, method=None):
	"""Asset Maintenance on_update: push the checklist to draft logs not yet started."""
	rows = [
		{"check_point": row.check_point, "description": row.description} for row in doc.get(CHECKLIST_FIELD)
	]
	# Same open statuses ERPNext's update_maintenance_log works on; Cancelled drafts are
	# logs whose task was removed and are left alone.
	for name in frappe.get_all(
		"Asset Maintenance Log",
		filters={
			"asset_maintenance": doc.name,
			"docstatus": 0,
			"maintenance_status": ("in", ["Planned", "Overdue"]),
		},
		pluck="name",
	):
		log = frappe.get_doc("Asset Maintenance Log", name)
		current = log.get(CHECKLIST_FIELD)
		if any(row.status or row.observation for row in current):
			continue
		if [row.check_point for row in current] == [row["check_point"] for row in rows]:
			continue
		_set_rows(log, rows)
		log.save()


def validate_unique_check_points(doc, method=None, table_field=CHECKLIST_FIELD):
	"""A check point may appear only once per checklist table (template, Asset Maintenance, log)."""
	seen = {}
	for row in doc.get(table_field):
		if not row.check_point:
			continue
		key = row.check_point.strip().casefold()
		if key in seen:
			frappe.throw(
				_("Row #{0}: Check Point {1} is already in row #{2}.").format(
					row.idx, frappe.bold(row.check_point), seen[key]
				),
				title=_("Duplicate Check Point"),
			)
		seen[key] = row.idx


@frappe.whitelist()
def get_asset_maintenance_checklist(asset_maintenance):
	"""Check points of an Asset Maintenance, in table order (used by the log form too)."""
	frappe.has_permission("Asset Maintenance", "read", asset_maintenance, throw=True)
	return _checklist_rows(asset_maintenance)


def _checklist_rows(asset_maintenance):
	return frappe.get_all(
		ASSET_MAINTENANCE_CHECKLIST,
		filters={
			"parent": asset_maintenance,
			"parenttype": "Asset Maintenance",
			"parentfield": CHECKLIST_FIELD,
		},
		fields=["check_point", "description"],
		order_by="idx asc",
	)


def _set_rows(doc, rows):
	doc.set(CHECKLIST_FIELD, [])
	for row in rows:
		doc.append(CHECKLIST_FIELD, {"check_point": row["check_point"], "description": row["description"]})
