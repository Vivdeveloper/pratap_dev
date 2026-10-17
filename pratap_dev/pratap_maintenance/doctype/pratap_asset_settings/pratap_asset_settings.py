# Copyright (c) 2026, pratap_dev contributors
# License: MIT

import frappe
from frappe import _
from frappe.model.document import Document


class PratapAssetSettings(Document):
	def validate(self):
		if self.stock_entry_type:
			purpose = frappe.db.get_value("Stock Entry Type", self.stock_entry_type, "purpose")
			if purpose != "Material Issue":
				frappe.throw(
					_("Stock Entry Type {0} must have purpose Material Issue (it is {1}).").format(
						frappe.bold(self.stock_entry_type), purpose or "-"
					)
				)
