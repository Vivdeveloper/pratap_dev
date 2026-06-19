# Copyright (c) 2026, saurabh@exacuer.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class GatePass(Document):
	def validate(self):
		if self.is_new():
			actual_received_qty = flt(self.actual_received_qty)
			received_qty = flt(self.received_qty)

			if actual_received_qty > received_qty:
				frappe.msgprint(
					_(
						"Actual Received Quantity ({0}) cannot be greater than Received Quantity ({1})"
					).format(actual_received_qty, received_qty)
				)
