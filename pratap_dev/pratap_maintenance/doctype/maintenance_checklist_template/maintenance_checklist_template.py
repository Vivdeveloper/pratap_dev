# Copyright (c) 2026, pratap_dev contributors
# License: MIT

from frappe.model.document import Document

from pratap_dev.pratap_maintenance.server.asset_maintenance_checklist import validate_unique_check_points


class MaintenanceChecklistTemplate(Document):
	def validate(self):
		validate_unique_check_points(self, table_field="checklist_items")
