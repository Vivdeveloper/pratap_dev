# Copyright (c) 2026, saurabh@exacuer.com and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import cint
from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry
from erpnext.stock.doctype.quality_inspection_template.quality_inspection_template import (
	get_template_details,
)


class PratapQualityInspection(Document):
	def before_submit(self):
		self._validate_custom_density()
		self._validate_readings_status_mandatory()
		self._validate_status_for_submit()

	def on_cancel(self):
		self._cancel_stock_entry()

	def on_submit(self):
		self._create_stock_entry()

	def validate(self):
		self._set_inspector()
		self._validate_inspected_qty()
		self._validate_total_raw_material_percentage()
		self._set_raw_material_required_qty()
		self._set_density_qty()
		self._set_finished_qty()
		self._set_readings_from_template()
		self._inspect_and_set_status()

	def _validate_custom_density(self):
		if self.custom_density in (None, ""):
			frappe.throw("Custom Density is required before submit.")

		try:
			self.custom_density = float(self.custom_density)
		except (TypeError, ValueError):
			frappe.throw("Custom Density must be a valid float value.")

		if self.custom_density <= 0:
			frappe.throw("Density must be greater than 0 before submit.")

	def _set_inspector(self):
		if not self.inspector or self.inspector == "frappe.session.user":
			self.inspector = frappe.session.user

	def _validate_inspected_qty(self):
		if frappe.utils.flt(self.inspected_qty) <= 0:
			frappe.throw("Inspected Qty must be greater than 0.")

	def _set_density_qty(self):
		reference_qty = frappe.utils.flt(self.reference_qty)
		custom_density = frappe.utils.flt(self.custom_density)

		if custom_density > 0:
			self.density_qty = reference_qty / custom_density
		else:
			self.density_qty = 0

	def _set_finished_qty(self):
		density_qty = frappe.utils.flt(self.density_qty)
		process_loss = frappe.utils.flt(self.process_loss)
		multiplier = 1 - (process_loss / 100.0)
		self.finished_qty = density_qty * multiplier if multiplier > 0 else 0

	def _set_raw_material_required_qty(self):
		reference_qty = frappe.utils.flt(self.reference_qty)
		for row in self.raw_materials or []:
			percentage = frappe.utils.flt(row.mat_req_in_pecentage)
			row.total_req_qty = reference_qty * (percentage / 100.0)

	def _validate_total_raw_material_percentage(self):
		total_percentage = sum(
			frappe.utils.flt(row.mat_req_in_pecentage) for row in (self.raw_materials or [])
		)
		if total_percentage > 100:
			frappe.throw(
				f"Total Raw Material % cannot be greater than 100. Current total is {total_percentage}."
			)

	def _set_readings_from_template(self):
		if self.readings:
			return

		if not self.quality_inspection_template and self.production_item:
			self.quality_inspection_template = frappe.db.get_value(
				"Item", self.production_item, "quality_inspection_template"
			)

		if not self.quality_inspection_template:
			return

		parameters = get_template_details(self.quality_inspection_template)
		self.set("readings", [])
		for parameter in parameters:
			row = self.append("readings", {})
			row.update(parameter)
			row.status = "Accepted"
			row.parameter_group = frappe.get_value(
				"Quality Inspection Parameter", parameter.get("specification"), "parameter_group"
			)

	@frappe.whitelist()
	def get_item_specification_details(self):
		"""Populate readings from selected template or item default template."""
		if not self.quality_inspection_template and self.production_item:
			self.quality_inspection_template = frappe.db.get_value(
				"Item", self.production_item, "quality_inspection_template"
			)

		self.set("readings", [])
		if not self.quality_inspection_template:
			return

		parameters = get_template_details(self.quality_inspection_template)
		for parameter in parameters:
			row = self.append("readings", {})
			row.update(parameter)
			row.status = "Accepted"
			row.parameter_group = frappe.get_value(
				"Quality Inspection Parameter", parameter.get("specification"), "parameter_group"
			)

	def _create_stock_entry(self):
		if self.stock_entry:
			return

		if (self.status or "").strip() != "Accepted":
			return

		if (self.reference_type or "").strip() != "Work Order":
			return

		if not self.work_order or not self.production_item:
			return

		qty = frappe.utils.flt(self.finished_qty) or frappe.utils.flt(self.reference_qty)
		qty_precision = frappe.get_precision("Stock Entry Detail", "qty") or 3
		qty = frappe.utils.flt(qty, qty_precision)
		if qty <= 0:
			return

		stock_entry_data = make_stock_entry(
			work_order_id=self.work_order,
			purpose="Manufacture",
			qty=qty,
		)
		stock_entry = frappe.get_doc(stock_entry_data)
		stock_entry.insert(ignore_permissions=True)
		stock_entry.submit()
		self._set_batch_custom_density()
		self.db_set("stock_entry", stock_entry.name, update_modified=False)

	def _set_batch_custom_density(self):
		batch_name = frappe.db.get_value(
			"Batch",
			{"batch_id": self.work_order, "item": self.production_item},
			"name",
		)
		if not batch_name and frappe.db.exists("Batch", self.work_order):
			batch_name = self.work_order

		if not batch_name:
			return

		frappe.db.set_value(
			"Batch",
			batch_name,
			"custom_density",
			frappe.utils.flt(self.custom_density),
			update_modified=False,
		)

	def _cancel_stock_entry(self):
		if not self.stock_entry:
			return

		stock_entry = frappe.get_doc("Stock Entry", self.stock_entry)
		if stock_entry.docstatus == 1:
			stock_entry.cancel()

	def _inspect_and_set_status(self):
		if not self.readings:
			return

		if cint(self.manual_inspection):
			# In manual mode, keep row/document status as user-selected.
			return

		if self.status == "Rework":
			# Keep explicit Rework status set by user.
			return

		for reading in self.readings:
			if cint(reading.manual_inspection):
				continue

			if cint(reading.formula_based_criteria):
				self._set_status_based_on_formula(reading)
			else:
				self._set_status_based_on_acceptance_values(reading)

		self.status = "Accepted"
		for reading in self.readings:
			if reading.status == "Rejected":
				self.status = "Rejected"
				break

	def _set_status_based_on_acceptance_values(self, reading):
		if cint(reading.numeric):
			result = self._min_max_criteria_passed(reading)
		else:
			reading_value = (reading.get("reading_value") or "").strip()
			accepted_value = (reading.get("value") or "").strip()

			if not reading_value:
				frappe.throw(
					f"Row #{reading.idx}: Reading Value is required for value-based inspection."
				)
			if not accepted_value:
				frappe.throw(
					f"Row #{reading.idx}: Acceptance Criteria Value is required for value-based inspection."
				)

			result = reading_value.lower() == accepted_value.lower()

		reading.status = "Accepted" if result else "Rejected"

	def _min_max_criteria_passed(self, reading):
		has_reading = False
		min_value = frappe.utils.flt(reading.get("min_value"))
		max_value = frappe.utils.flt(reading.get("max_value"))

		for i in range(1, 11):
			field = f"reading_{i}"
			reading_value = (reading.get(field) or "").strip()
			if not reading_value:
				continue

			has_reading = True
			parsed_value = _parse_float(reading_value)
			if parsed_value < min_value or parsed_value > max_value:
				return False

		return has_reading

	def _set_status_based_on_formula(self, reading):
		if not reading.acceptance_formula:
			frappe.throw(f"Row #{reading.idx}: Acceptance Criteria Formula is required.")

		try:
			result = frappe.safe_eval(reading.acceptance_formula, None, self._get_formula_data(reading))
		except Exception:
			frappe.throw(f"Row #{reading.idx}: Acceptance Criteria Formula is incorrect.")

		reading.status = "Accepted" if result else "Rejected"

	def _get_formula_data(self, reading):
		if not cint(reading.numeric):
			return {"reading_value": reading.get("reading_value")}

		data = {}
		values = []
		for i in range(1, 11):
			field = f"reading_{i}"
			reading_value = (reading.get(field) or "").strip()
			parsed_value = _parse_float(reading_value) if reading_value else 0.0
			data[field] = parsed_value
			if reading_value:
				values.append(parsed_value)

		data["mean"] = sum(values) / len(values) if values else 0.0
		return data

	def _validate_readings_status_mandatory(self):
		for reading in self.readings or []:
			if not reading.status:
				frappe.throw(f"Row #{reading.idx}: Status is mandatory.")

	def _validate_status_for_submit(self):
		if (self.status or "").strip() != "Accepted":
			frappe.throw("Only Accepted Pratap Quality Inspection can be submitted.")


def _parse_float(value):
	try:
		return float(str(value).replace(",", ""))
	except (TypeError, ValueError):
		return 0.0

