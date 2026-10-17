# Copyright (c) 2026, pratap_dev contributors
# License: MIT

from frappe.model.document import Document


class AssetChecklist(Document):
	def before_insert(self):
		# Named by Check Point (unique): trim so "Check oil " cannot sit beside "Check oil".
		self.check_point = (self.check_point or "").strip()
