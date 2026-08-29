# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Work Order subclass for the editable-qty-after-submit feature.

When Qty To Manufacture changes on a SUBMITTED Work Order, the ERPNext client calls
get_items_and_operations_from_bom -> set_required_items() (a full rebuild). That rebuild
reassigns fresh names to the Required Items rows, and on the next Update the after-submit
save can't find those rows in the DB ("Work Order Item <hash> not found").

Here we override that method so a submitted Work Order updates the existing rows' qty
IN PLACE (reset_only_qty) — preserving row names — instead of rebuilding. Combined with
the server-side rescale/persist in work_order_qty.py, editing qty after submit works
end to end without the "not found" error. Drafts keep the standard rebuild behaviour.
"""

import frappe

from erpnext.manufacturing.doctype.work_order.work_order import (
	WorkOrder,
	check_if_scrap_warehouse_mandatory,
)


class PratapWorkOrder(WorkOrder):
	# Re-apply @frappe.whitelist() — it does not carry over when overriding the base
	# method, and this is called from the client via frm.call.
	@frappe.whitelist()
	def get_items_and_operations_from_bom(self):
		if self.docstatus == 1 and self.get("required_items"):
			# Update required_qty on existing rows only (keeps their names); do NOT
			# rebuild operations either, so nothing else changes after submit.
			self.set_required_items(reset_only_qty=len(self.get("required_items")))
			return check_if_scrap_warehouse_mandatory(self.bom_no)
		return super().get_items_and_operations_from_bom()
