# Copyright (c) 2026, pratap_dev contributors
# License: MIT

# Pratap Downtime Entry — machine downtime (breakdown / work order) with the maintenance
# items consumed while it was down. Replaces the core Downtime Entry for Pratap.
#   * validate: To Time after From Time, Downtime in minutes, default company, status Open;
#     consumed items: default Source Warehouse, allowed Item Groups, Available Qty;
#   * before_submit: Source Warehouse / stock checks for the consumed items;
#   * on_submit: status Completed, and the Material Issue Stock Entry in Auto mode
#     (Pratap Asset Settings); Manual mode shows a Create Stock Entry button instead;
#   * on_cancel: status Cancelled (a submitted Stock Entry must be cancelled first).

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, time_diff_in_hours

from pratap_dev.pratap_maintenance.server import maintenance_stock_entry


class PratapDowntimeEntry(Document):
	def validate(self):
		if not self.company:
			self.company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
				"Global Defaults", "default_company"
			)
		if self.from_time and self.to_time:
			if get_datetime(self.to_time) <= get_datetime(self.from_time):
				frappe.throw(_("To Time must be after From Time"))
			self.downtime = time_diff_in_hours(self.to_time, self.from_time) * 60
		if self.ownership != "Third-Party":
			self.purchase_order = self.supplier_name = self.po_date = None
		if self.docstatus == 0:
			self.status = "Open"
		maintenance_stock_entry.validate_consumed_items(self)

	def before_submit(self):
		maintenance_stock_entry.validate_ready(self)
		self.status = "Completed"

	def on_submit(self):
		maintenance_stock_entry.on_ready_create_stock_entry(self)

	def on_cancel(self):
		self.db_set("status", "Cancelled")
