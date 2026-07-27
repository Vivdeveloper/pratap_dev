"""Retire the DB-resident Work Order → Material Request scripts.

The button and its server method now live in the app:
``pratap_dev/public/js/work_order_override.js`` and
``pratap_dev.work_order_material_request.create_and_submit_material_request``.

The site copies were created by hand and are not in git, so each site drifted on its own —
production still ran a version that put MR Qty 0 rows into the Material Request and hit
"Row #N: Quantity for Item X cannot be zero", blocking the request for every other item.
Leaving them enabled would also add the "Material Request" button twice.

They are disabled rather than deleted so the original code stays inspectable; delete the
records by hand once the app version has been running for a while.
"""

import frappe

CLIENT_SCRIPT = "Create Material Request"
SERVER_SCRIPT_API_METHOD = "create_and_submit_material_request"


def execute():
	disable_client_script()
	disable_server_scripts()


def disable_client_script():
	name = frappe.db.get_value(
		"Client Script", {"name": CLIENT_SCRIPT, "dt": "Work Order"}, "name"
	)
	if name and frappe.db.get_value("Client Script", name, "enabled"):
		frappe.db.set_value("Client Script", name, "enabled", 0)


def disable_server_scripts():
	# Matched on api_method, not name -- the record is titled differently on each site.
	for name in frappe.get_all(
		"Server Script",
		filters={
			"script_type": "API",
			"api_method": SERVER_SCRIPT_API_METHOD,
			"disabled": 0,
		},
		pluck="name",
	):
		frappe.db.set_value("Server Script", name, "disabled", 1)
