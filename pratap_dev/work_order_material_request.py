# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Create a Material Request for a Work Order's short raw materials.

Each Required Items row carries an MR Qty (``custom_qty_amount``) = required qty minus the
qty already available at the source warehouse, floored at 0. Rows with MR Qty 0 need
nothing ordered, and including them made ERPNext reject the whole Material Request with
"Row #N: Quantity for Item X cannot be zero" -- so one fully-stocked item blocked the
request for every other item too. Those rows are skipped here instead.

This replaces the DB-resident Server Script ``create material request from work order``
and its companion Client Script ``Create Material Request``; disable both so the button is
not added twice.
"""

import frappe
from frappe import _
from frappe.utils import flt, nowdate

MR_QTY_FIELD = "custom_qty_amount"


@frappe.whitelist()
def create_and_submit_material_request(work_order_name):
	if not work_order_name:
		frappe.throw(_("Work Order Name is required"))

	work_order = frappe.get_doc("Work Order", work_order_name)
	work_order.check_permission("read")

	if work_order.docstatus != 1:
		frappe.throw(_("Work Order must be submitted"))

	existing = frappe.db.exists(
		"Material Request", {"work_order": work_order.name, "docstatus": ["!=", 2]}
	)
	if existing:
		frappe.throw(
			_("{0} already exists for this Work Order.").format(
				frappe.utils.get_link_to_form("Material Request", existing)
			),
			title=_("Material Request Already Created"),
		)

	short_rows = [row for row in work_order.required_items if flt(row.get(MR_QTY_FIELD)) > 0]
	if not short_rows:
		frappe.throw(
			_(
				"No items are short — every required item already has enough quantity at its source warehouse."
			),
			title=_("Nothing to Request"),
		)

	mr = frappe.new_doc("Material Request")
	mr.material_request_type = "Material Transfer"
	mr.company = work_order.company
	mr.transaction_date = nowdate()
	mr.schedule_date = nowdate()
	mr.set_warehouse = work_order.source_warehouse
	mr.work_order = work_order.name
	# frappe.session.user is always the login id (email), never the display name --
	# keep it that way so "Requested by user" stays a valid User link, not free text.
	mr.custom_requested_by_user = frappe.session.user

	for row in short_rows:
		mr.append(
			"items",
			{
				"item_code": row.item_code,
				"qty": flt(row.get(MR_QTY_FIELD)),
				"schedule_date": nowdate(),
				"warehouse": row.source_warehouse,
			},
		)

	mr.insert(ignore_permissions=True)
	mr.submit()

	skipped = len(work_order.required_items) - len(short_rows)
	return {"name": mr.name, "requested": len(short_rows), "skipped": skipped}
