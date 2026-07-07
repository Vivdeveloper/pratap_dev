# Copyright (c) 2026, saurabh@exacuer.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint
# from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry
from erpnext.stock.doctype.quality_inspection_template.quality_inspection_template import (
	get_template_details
)

# GRN QC outcomes that still count as "passed enough" to flow to the GRN
# (fully accepted, or partially accepted/rejected across batches).
QC_GRN_OK_STATUSES = {"Accepted", "Partially Accepted", "Partially Rejected"}


class PratapQualityInspection(Document):
	def before_submit(self):
		self._ensure_density_for_submit()
		self._validate_custom_density()
		self._validate_inspected_qty()
		self._validate_all_batches_qc_done()
		self._validate_readings_status_mandatory()
		self._validate_status_for_submit()
		self._freeze_batch_qc_json()

	def _validate_all_batches_qc_done(self):
		"""GRN: block submit until every batch has an Accept/Reject decision (batch-wise readings)."""
		if (self.reference_type or "").strip() != "GRN":
			return

		import json

		def _parse(value):
			try:
				data = json.loads(value or "[]")
				return data if isinstance(data, list) else []
			except Exception:
				return []

		batch_rows = _parse(self.batch_qc_json)
		if not batch_rows:
			return

		status_by_batch = {
			row.get("batch_no"): (row.get("status") or "").strip()
			for row in _parse(self.batch_readings_json)
		}
		pending = [
			str(row.get("batch_no"))
			for row in batch_rows
			if status_by_batch.get(row.get("batch_no")) not in ("Accepted", "Rejected")
		]
		if pending:
			frappe.throw(
				_(
					"Accept/Reject readings are pending for {0} batch(es): {1}. "
					"Complete all batches before submit."
				).format(len(pending), ", ".join(pending))
			)

	def on_cancel(self):
		self.ignore_linked_doctypes = ["Serial and Batch Bundle"]
		self._cancel_stock_entry()
		self._clear_grn_qc_reference()

	def on_trash(self):
		self._clear_grn_qc_reference(remove_reference=True)

	def on_submit(self):
		if self.reference_type == "GRN":
			self._update_grn_item()
		self._create_stock_entry()
		self._submit_linked_grn()

	def on_update(self):
		if self.status == "Rework" and self.reference_type == "Work Order":
			self._update_rework_qc_in_work_order()

	def validate(self):
		self._set_inspector()
		self._validate_grn_reference()
		self._ensure_density_for_grn()
		self._set_density_for_same_uom()
		self._validate_inspected_qty()
		self._validate_total_raw_material_percentage()
		self._set_raw_material_required_qty()
		self._set_density_qty()
		self._set_finished_qty()
		self._set_readings_from_template()
		self._inspect_and_set_status()
		self._sync_accepted_qc_to_grn()
		self._sync_density_to_grn_item()

	def _sync_accepted_qc_to_grn(self):
		if not self.name:
			return

		if (self.status or "").strip() not in QC_GRN_OK_STATUSES:
			return

		from pratap_dev.purchase_receipt import link_pratap_qc_to_grn_item

		link_pratap_qc_to_grn_item(self)

	def _sync_density_to_grn_item(self):
		if not self.name:
			return

		if (self.inspection_type or "").strip() != "Incoming":
			return

		if (self.reference_type or "").strip() != "GRN":
			return

		if self.reference_doctype != "Purchase Receipt" or not self.reference_name or not self.production_item:
			return

		from pratap_dev.purchase_receipt import sync_grn_item_density_from_pratap_qc

		sync_grn_item_density_from_pratap_qc(
			self.reference_name,
			self.production_item,
			self.name,
			purchase_receipt_item=self.get("purchase_receipt_item"),
		)

	def _validate_grn_reference(self):
		if (self.inspection_type or "").strip() != "Incoming":
			return

		if (self.reference_type or "").strip() != "GRN":
			return

		if self.reference_doctype != "Purchase Receipt":
			frappe.throw(_("Reference DocType must be Purchase Receipt when Reference Type is GRN."))

		if not self.reference_name:
			frappe.throw(_("Reference Name (GRN) is required for Incoming inspection."))

		if not frappe.db.exists("Purchase Receipt", self.reference_name):
			frappe.throw(_("Purchase Receipt {0} does not exist.").format(self.reference_name))

		grn = frappe.get_doc("Purchase Receipt", self.reference_name)
		if grn.docstatus == 2:
			frappe.throw(_("Purchase Receipt {0} is cancelled.").format(self.reference_name))

		if self.production_item:
			item_row = _get_grn_item_row(grn, self.production_item, self.get("purchase_receipt_item"))
			if not item_row:
				frappe.throw(
					_("Item {0} is not found in Purchase Receipt {1}.").format(
						self.production_item, self.reference_name
					)
				)

			if self.get("purchase_receipt_item") and item_row.name != self.purchase_receipt_item:
				frappe.throw(
					_("Purchase Receipt Item {0} does not belong to {1}.").format(
						self.purchase_receipt_item, self.reference_name
					)
				)

	def _set_density_for_same_uom(self):
		purchase_uom = (self.purchase_uom or "").strip().lower()
		sales_uom = (self.sales_uom or "").strip().lower()

		if purchase_uom and sales_uom and purchase_uom == sales_uom:
			self.custom_density = 1

	def _submit_linked_grn(self):
		if (self.inspection_type or "").strip() != "Incoming":
			return

		if (self.reference_type or "").strip() != "GRN":
			return

		if self.reference_doctype != "Purchase Receipt" or not self.reference_name:
			return

		if (self.status or "").strip() not in QC_GRN_OK_STATUSES:
			return

		if not frappe.db.exists("Purchase Receipt", self.reference_name):
			return

		from pratap_dev.purchase_receipt import (
			grn_ready_for_submit_after_qc,
			link_pratap_qc_to_grn_item,
		)

		link_pratap_qc_to_grn_item(self)

		if not grn_ready_for_submit_after_qc(self.reference_name):
			return

		grn = frappe.get_doc("Purchase Receipt", self.reference_name)
		if grn.docstatus == 0:
			frappe.flags.submitting_pratap_qc = self.name
			try:
				grn.submit()
			finally:
				frappe.flags.submitting_pratap_qc = None

	def _ensure_density_for_grn(self):
		"""Default density for GRN QC during validate/submit when UOM conversion is missing."""
		if (self.reference_type or "").strip() != "GRN":
			return

		self._set_density_for_same_uom()
		if not frappe.utils.flt(self.custom_density):
			self.custom_density = 1

	def _ensure_density_for_submit(self):
		"""Default density for GRN QC when purchase UOM is missing or matches sales UOM."""
		self._ensure_density_for_grn()
		if not frappe.utils.flt(self.custom_density):
			self.custom_density = 1
		self._set_density_qty()

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
			frappe.throw(_("Inspected Qty must be greater than 0."))

	def _set_density_qty(self):
		reference_qty = frappe.utils.flt(self.reference_qty)
		custom_density = frappe.utils.flt(self.custom_density)

		if custom_density > 0:
			# (batch_qty - inspected_qty - process_loss%reference_qty)/ custom_density
			self.density_qty = reference_qty / custom_density
		else:
			self.density_qty = 0

	def _set_finished_qty(self):
		batch_qty = frappe.utils.flt(self.reference_qty)
		inspected_qty = frappe.utils.flt(self.inspected_qty)
		process_loss = frappe.utils.flt(self.process_loss)
		if self.reference_type == "Work Order":
			custom_density = frappe.utils.flt(self.custom_density)
			if custom_density <= 0:
				return
			self.finished_qty = (
				(batch_qty - inspected_qty - (batch_qty * process_loss / 100)) / custom_density
			)
		else:
			self.finished_qty = (batch_qty - inspected_qty) * (1 - process_loss / 100)
		# Round to 3 decimal places
		self.finished_qty = round(self.finished_qty)


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
			row.status = ""
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
			row.status = ""
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

		if not self.reference_name or not self.production_item:
			# from UI ity is not a work order field and it reference_name 
			return

		qty = frappe.utils.flt(self.finished_qty) or frappe.utils.flt(self.reference_qty)
		qty_precision = frappe.get_precision("Stock Entry Detail", "qty") or 3
		qty = frappe.utils.flt(qty, qty_precision)
		if qty <= 0:
			return

		# A Manufacture stock entry needs a submitted Work Order, so auto-submit the
		# linked WO (if still draft) once the QC is Accepted.
		self._submit_linked_work_order()

		stock_entry_data = self.make_stock_entry(
			work_order_id=self.reference_name,
			purpose="Manufacture",
			qty=qty,
		)
		stock_entry = frappe.get_doc(stock_entry_data)
		stock_entry.insert(ignore_permissions=True)
		stock_entry.submit()
		self._set_batch_custom_density()
		self.db_set("stock_entry", stock_entry.name, update_modified=False)

	def _submit_linked_work_order(self):
		"""Auto-submit the linked Work Order if it is still in draft.

		Only reached from the Accepted QC path in _create_stock_entry, so we submit
		exactly when a Manufacture stock entry is about to be created against the WO.
		"""
		if not self.reference_name:
			return

		wo_docstatus = frappe.db.get_value("Work Order", self.reference_name, "docstatus")
		if wo_docstatus != 0:
			return

		work_order = frappe.get_doc("Work Order", self.reference_name)
		work_order.submit()

	def _set_batch_custom_density(self):
		batch_name = frappe.db.get_value(
			"Batch",
			{"batch_id": self.reference_name, "item": self.production_item},
			"name",
		)
		if not batch_name and frappe.db.exists("Batch", self.reference_name):
			batch_name = self.reference_name

		if not batch_name:
			return

		frappe.db.set_value(
			"Batch",
			batch_name,
			"custom_density",
			frappe.utils.flt(self.custom_density),
			update_modified=False,
		)

	def _clear_grn_qc_reference(self, remove_reference=False):
		from pratap_dev.purchase_receipt import clear_pratap_qc_from_grn_item

		clear_pratap_qc_from_grn_item(self, remove_reference=remove_reference)

	def _cancel_stock_entry(self):
		if not self.stock_entry:
			return

		stock_entry = frappe.get_doc("Stock Entry", self.stock_entry)
		if stock_entry.docstatus == 1:
			stock_entry.cancel()

	def _inspect_and_set_status(self):
		if not self.readings:
			return

		if (self.reference_type or "").strip() == "GRN":
			# GRN QC: per-parameter readings are auto-accepted & manual-inspected; the real
			# accept/reject is driven by the Batch-wise Readings (per-batch status), so the
			# parent status is left untouched here (client rolls it up, incl. partial).
			for reading in self.readings:
				reading.manual_inspection = 1
				reading.status = "Accepted"
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

		self._set_parent_status_from_readings()

	def _set_parent_status_from_readings(self):
		"""Parent status from readings: all Accepted → Accepted, any Rejected → Rejected, else Pending."""
		if not self.readings:
			return

		statuses = [(reading.status or "").strip() for reading in self.readings]

		if any(status == "Rejected" for status in statuses):
			self.status = "Rejected"
		elif statuses and all(status == "Accepted" for status in statuses):
			self.status = "Accepted"
		else:
			self.status = "Pending"

	def _set_status_based_on_acceptance_values(self, reading):
		if cint(reading.numeric):
			self._set_status_from_observe_value_range(reading)
			return

		observe_value = (reading.get("observe_value") or "").strip()
		reading_value = observe_value or (reading.get("reading_value") or "").strip()
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

	def _set_status_from_observe_value_range(self, reading):
		observe_value = (reading.get("observe_value") or "").strip()
		if not observe_value:
			reading.status = ""
			return

		min_value = frappe.utils.flt(reading.get("min_value"))
		max_value = frappe.utils.flt(reading.get("max_value"))
		parsed_value = _parse_float(observe_value)
		reading.status = (
			"Accepted" if min_value <= parsed_value <= max_value else "Rejected"
		)

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
		# The status-must-be-Accepted gate applies only to GRN inspections.
		if (self.reference_type or "").strip() != "GRN":
			return

		status = (self.status or "").strip()
		# Accepted and partial outcomes (some accepted, some rejected batches) are submittable.
		if status in ("Accepted", "Partially Accepted", "Partially Rejected"):
			return

		if status == "Rejected":
			frappe.throw(_("Rejected Pratap Quality Inspection cannot be submitted."))

		frappe.throw(
			_(
				"Status must be Accepted (or Partially Accepted/Rejected) before submit. "
				"For GRN QC, add readings for every batch."
			)
		)

	def _freeze_batch_qc_json(self):
		"""Snapshot batch QC rows to JSON on submit; no further GRN fetch after this."""
		if (self.reference_type or "").strip() != "GRN":
			return

		from pratap_dev.purchase_receipt_batch_qc import (
			apply_density_to_batch_qc_rows,
			parse_batch_qc_json,
		)

		rows = parse_batch_qc_json(self.batch_qc_json)
		if not rows:
			for batch in get_grn_batch_list(
				self.reference_name,
				self.production_item,
				self.get("purchase_receipt_item"),
			):
				batch_qty = frappe.utils.flt(batch.get("batch_qty"))
				standard_pkg_qty = frappe.utils.flt(batch.get("standard_pkg_qty")) or 1
				no_of_unit = frappe.utils.flt(batch.get("no_of_unit"))
				if not no_of_unit and standard_pkg_qty:
					no_of_unit = batch_qty / standard_pkg_qty
				rows.append(
					{
						"batch_no": batch.get("batch_no"),
						"batch_qty": batch_qty,
						"standard_pkg_qty": standard_pkg_qty,
						"no_of_unit": no_of_unit,
						"accepted_unit": 0,
						"rejected_unit": no_of_unit,
						"accepted_qty": 0,
						"rejected_qty": batch_qty,
						"density": frappe.utils.flt(batch.get("density")),
					}
				)

		if rows:
			import json

			# Freeze density-converted qtys from each batch's own (GRN-fetched) density.
			apply_density_to_batch_qc_rows(rows)
			self.batch_qc_json = json.dumps(rows)

	def _update_grn_item(self):
		from pratap_dev.purchase_receipt_batch_qc import parse_batch_qc_json, update_grn_from_batch_qc

		grn_doc = frappe.get_doc("Purchase Receipt", self.reference_name)
		# A QC covers every GRN row of the item, so write results back to each row.
		item_rows = _get_grn_item_rows(
			grn_doc, self.production_item, self.get("purchase_receipt_item")
		)
		if not item_rows:
			return

		batch_rows = parse_batch_qc_json(self.batch_qc_json)

		if batch_rows:
			# Route each batch's accept/reject decision to the GRN row that owns it.
			rows_by_batch = _map_grn_batches_to_rows(item_rows)
			grouped = {}
			for batch_row in batch_rows:
				owner = rows_by_batch.get(batch_row.get("batch_no")) or item_rows[0]
				grouped.setdefault(owner.name, (owner, []))[1].append(batch_row)

			for owner, owner_batch_rows in grouped.values():
				# Density is per-batch (fetched from the GRN row); use the row's own value.
				owner_density = _first_row_density(owner_batch_rows)
				update_grn_from_batch_qc(
					grn_doc, owner, owner_batch_rows, custom_density=owner_density
				)
				self._apply_grn_item_qc_meta(owner, owner_density)
		else:
			for item_row in item_rows:
				self._update_batch_custom_density(grn_doc, item_row)
				self._apply_grn_item_qc_meta(item_row, frappe.utils.flt(self.custom_density))

		grn_doc.save(ignore_permissions=True)

	def _apply_grn_item_qc_meta(self, item_row, density):
		# conversion_factor = 1 / density (density_qty / reference_qty reduces to this).
		density = frappe.utils.flt(density)
		if density > 0:
			item_row.conversion_factor = 1.0 / density
			item_row.custom_density = density

		item_row.custom_pratap_quality_inspection = self.name

	def _update_batch_custom_density(self, grn_doc, item_row=None):
		item = item_row or (grn_doc.items[0] if grn_doc.items else None)
		if not item:
			return

		batch_name = item.batch_no
		if batch_name:
			frappe.db.set_value(
				"Batch",
				batch_name,
				"custom_density",
				frappe.utils.flt(self.custom_density),
				update_modified=False,
			)

	def _update_rework_qc_in_work_order(self):
		if not self.reference_name:
			return

		if (self.reference_type or "").strip() != "Work Order":
			return
		
		frappe.db.set_value(
			"Work Order",
			self.reference_name,
			"custom_rework_qc",
			self.name,
			update_modified=False,
		)


	def make_stock_entry(
		self,
		work_order_id: str,
		purpose: str,
		qty: float | None = None,
		target_warehouse: str | None = None,
		source_stock_entry: str | None = None,
	):
		work_order = frappe.get_doc("Work Order", work_order_id)
		if not frappe.db.get_value("Warehouse", work_order.wip_warehouse, "is_group"):
			wip_warehouse = work_order.wip_warehouse
		else:
			wip_warehouse = None

		stock_entry = frappe.new_doc("Stock Entry")
		stock_entry.purpose = purpose
		stock_entry.work_order = work_order_id
		stock_entry.company = work_order.company
		stock_entry.from_bom = 1
		stock_entry.bom_no = work_order.bom_no
		stock_entry.use_multi_level_bom = work_order.use_multi_level_bom
		finished_qty = frappe.utils.flt(self.finished_qty)
		reference_qty = frappe.utils.flt(self.reference_qty)
		# ERPNext requires fg_completed_qty to match finished item qty.
		stock_entry.fg_completed_qty = finished_qty or reference_qty

		# The Pratap Quality Inspection IS the quality gate for this stock entry (it is
		# only created once the QC is Accepted), so never inherit BOM.inspection_required
		# here — doing so makes ERPNext demand a separate native Quality Inspection and
		# blocks submit with "Quality Inspection required".
		stock_entry.inspection_required = 0

		if purpose == "Material Transfer for Manufacture":
			stock_entry.to_warehouse = wip_warehouse
			stock_entry.project = work_order.project
		else:
			stock_entry.from_warehouse = (
				work_order.source_warehouse
				if work_order.skip_transfer and not work_order.from_wip_warehouse
				else wip_warehouse
			)
			stock_entry.to_warehouse = work_order.fg_warehouse
			stock_entry.project = work_order.project

		if purpose == "Disassemble":
			stock_entry.from_warehouse = work_order.fg_warehouse
			stock_entry.to_warehouse = target_warehouse or work_order.source_warehouse
			if source_stock_entry:
				stock_entry.source_stock_entry = source_stock_entry

		stock_entry.set_stock_entry_type()
		stock_entry.get_items()
		# FG uses density-based finished_qty; WO batch row always consumes full reference (batch) qty.
		rm_scale = 1
		if reference_qty > 0 and finished_qty > 0:
			if abs(finished_qty - reference_qty) > 0.0001:
				rm_scale = reference_qty / finished_qty

		for item in stock_entry.items:
			if item.is_finished_item and finished_qty > 0:
				item.qty = finished_qty
			elif item.serial_and_batch_bundle and reference_qty > 0:
				self._sync_batch_row_with_reference_qty(item, reference_qty)
			elif not item.is_finished_item and item.s_warehouse and rm_scale != 1:
				item.qty = frappe.utils.flt(item.qty) * rm_scale

		if purpose != "Disassemble":
			stock_entry.set_serial_no_batch_for_finished_good()

		return stock_entry.as_dict()

	def _sync_batch_row_with_reference_qty(self, row, reference_qty):
		"""Consume full WO batch qty and align draft Serial and Batch Bundle."""
		target_qty = frappe.utils.flt(reference_qty)
		if target_qty <= 0:
			return

		row.qty = target_qty
		bundle_name = row.serial_and_batch_bundle
		if not bundle_name or not frappe.db.exists("Serial and Batch Bundle", bundle_name):
			return

		bundle = frappe.get_doc("Serial and Batch Bundle", bundle_name)
		if bundle.docstatus != 0 or not bundle.entries:
			return

		current_total = abs(frappe.utils.flt(bundle.total_qty))
		if abs(current_total - target_qty) <= 0.0001:
			return

		is_outward = frappe.utils.flt(bundle.total_qty) < 0
		target_entry_qty = -target_qty if is_outward else target_qty

		if len(bundle.entries) == 1:
			bundle.entries[0].qty = target_entry_qty
		else:
			per_entry = target_entry_qty / len(bundle.entries)
			for entry in bundle.entries:
				entry.qty = per_entry

		bundle.flags.ignore_voucher_validation = True
		bundle.calculate_total_qty(save=False)
		bundle.save(ignore_permissions=True)
	
@frappe.whitelist()
def get_grn_batch_list(purchase_receipt, item_code=None, purchase_receipt_item=None):
	"""Return batch rows from GRN item serial_and_batch_bundle (or legacy batch_no).

	A GRN QC covers EVERY GRN row of the same item (their qtys are summed into one
	QC), so batches are collected from all matching rows — not just the linked row —
	otherwise batches sitting on the other rows would be silently dropped from QC.
	"""
	if not purchase_receipt:
		return []

	if not frappe.db.exists("Purchase Receipt", purchase_receipt):
		frappe.throw(_("Purchase Receipt {0} does not exist.").format(purchase_receipt))

	pr = frappe.get_doc("Purchase Receipt", purchase_receipt)
	item_rows = _get_grn_item_rows(pr, item_code, purchase_receipt_item)
	if not item_rows:
		return []

	batches = []
	for item_row in item_rows:
		batches.extend(_batches_for_grn_item_row(item_row))

	return batches


def _first_row_density(batch_rows):
	"""First non-zero density among a GRN row's batch QC rows (they share one row density)."""
	for row in batch_rows or []:
		density = frappe.utils.flt(row.get("density"))
		if density > 0:
			return density
	return 0


def _batches_for_grn_item_row(item_row):
	"""Batch rows (batch_no/qty/pkg/units/density) for a single GRN item row.

	Density is fetched from the GRN item row's own density field, so every batch of
	that row carries the row's density into the QC table.
	"""
	standard_pkg_qty = frappe.utils.flt(item_row.get("custom_packing_qty")) or 1
	purchase_receipt_item = item_row.name
	row_density = frappe.utils.flt(item_row.get("custom_density"))

	batches = []

	if item_row.get("serial_and_batch_bundle"):
		seen_batches = {}
		entries = frappe.get_all(
			"Serial and Batch Entry",
			filters={"parent": item_row.serial_and_batch_bundle, "batch_no": ["is", "set"]},
			fields=["batch_no", "qty"],
			order_by="idx asc",
		)
		for entry in entries:
			batch_no = entry.batch_no
			if not batch_no:
				continue
			qty = frappe.utils.flt(entry.qty)
			if batch_no in seen_batches:
				seen_batches[batch_no] += qty
			else:
				seen_batches[batch_no] = qty

		for batch_no, qty in seen_batches.items():
			batches.append(
				{
					"batch_no": batch_no,
					"batch_qty": qty,
					"standard_pkg_qty": standard_pkg_qty,
					"no_of_unit": qty / standard_pkg_qty if standard_pkg_qty else 0,
					"purchase_receipt_item": purchase_receipt_item,
					"density": row_density,
				}
			)

	elif item_row.get("batch_no"):
		batch_qty = frappe.utils.flt(item_row.qty)
		batches.append(
			{
				"batch_no": item_row.batch_no,
				"batch_qty": batch_qty,
				"standard_pkg_qty": standard_pkg_qty,
				"no_of_unit": batch_qty / standard_pkg_qty if standard_pkg_qty else 0,
				"purchase_receipt_item": purchase_receipt_item,
				"density": row_density,
			}
		)

	return batches


def _get_grn_item_row(purchase_receipt_doc, item_code=None, purchase_receipt_item=None):
	items = purchase_receipt_doc.get("items") or []
	if not items:
		return None

	if purchase_receipt_item:
		for row in items:
			if row.name == purchase_receipt_item:
				return row

	if item_code:
		for row in items:
			if row.item_code == item_code:
				return row

	return items[0]


def _get_grn_item_rows(purchase_receipt_doc, item_code=None, purchase_receipt_item=None):
	"""All GRN rows a QC spans: every row of the item (GRN QC is item-level).

	Falls back to the single linked row / first row when no item_code is given.
	"""
	items = purchase_receipt_doc.get("items") or []
	if not items:
		return []

	if item_code:
		rows = [row for row in items if row.item_code == item_code]
		if rows:
			return rows

	if purchase_receipt_item:
		rows = [row for row in items if row.name == purchase_receipt_item]
		if rows:
			return rows

	return [items[0]]


def _map_grn_batches_to_rows(item_rows):
	"""batch_no -> owning GRN item row, scanning accepted & rejected bundles (and legacy batch_no)."""
	mapping = {}
	for row in item_rows:
		for field in ("serial_and_batch_bundle", "rejected_serial_and_batch_bundle"):
			bundle = row.get(field)
			if not bundle:
				continue
			entries = frappe.get_all(
				"Serial and Batch Entry",
				filters={"parent": bundle, "batch_no": ["is", "set"]},
				fields=["batch_no"],
			)
			for entry in entries:
				mapping.setdefault(entry.batch_no, row)

		if row.get("batch_no"):
			mapping.setdefault(row.batch_no, row)

	return mapping


@frappe.whitelist()
def get_rework_stock_entry(work_order_name):
	if not work_order_name:
		frappe.throw(_("Work Order is required."))

	work_order = frappe.get_doc("Work Order", work_order_name)
	qc_name = work_order.custom_rework_qc
	if not qc_name:
		frappe.throw(_("No Rework QC is linked to this Work Order."))

	qc = frappe.get_doc("Pratap Quality Inspection", qc_name)
	items = []
	for row in qc.raw_materials or []:
		qty = frappe.utils.flt(row.total_req_qty)
		if not row.item_code or qty <= 0:
			continue

		items.append(
			{
				"doctype": "Stock Entry Detail",
				"item_code": row.item_code,
				"item_name": row.item_name or "",
				"qty": qty,
				"uom": row.uom or "",
				"stock_uom": row.uom or "",
				"s_warehouse": row.source_warehouse or work_order.source_warehouse or "",
				"conversion_factor": 1,
			}
		)

	if not items:
		frappe.throw(_("No raw materials with quantity were found in the linked Pratap Quality Inspection."))

	stock_entry = frappe.new_doc("Stock Entry")
	stock_entry.company = work_order.company
	stock_entry.work_order = work_order.name
	stock_entry.posting_date = frappe.utils.today()
	stock_entry.posting_time = frappe.utils.nowtime()
	stock_entry.stock_entry_type = "Material Transfer for Manufacture"
	stock_entry.purpose = "Material Transfer for Manufacture"
	for item in items:
		stock_entry.append("items", item)
	stock_entry.set_stock_entry_type()
	stock_entry.set_missing_values()
	return stock_entry.as_dict()


def _parse_float(value):
	try:
		return float(str(value).replace(",", ""))
	except (TypeError, ValueError):
		return 0.0
