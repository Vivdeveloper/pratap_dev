# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Batch of manager-requested field changes (Oct 2026):

 - Hide 'GRN Created' and 'Gate Pass' on Purchase Order (custom fields).
 - Hide 'Supplier Delivery Note' and 'Apply Putaway Rule' on GRN (standard fields, via
   property setter).
 - Stop the computed warehouse/qty columns on Material Request Item from being editable
   after submit (allow_on_submit = 0) so the 'Update' button no longer appears post-submit.
 - Add a read-only 'Source Document' field on Material Request showing which doc the data
   was fetched from (e.g. the Forecast Club).

Idempotent."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


# MR Item computed warehouse/qty columns that should be frozen after submit.
MR_ITEM_FREEZE_AFTER_SUBMIT = [
	"custom_last_month_consumption",
	"custom_last_month_purchase",
	"custom_min_level_avg_consumption",
	"custom_max_level_consumption",
	"custom_current_requirement",
	"custom_total_stock_qty",
	"custom_pending_pr_for_grn",
	"custom_pending_po_qty",
	"custom_pending_grn_qc",
	"custom_required_qty_for_pr",
	"custom_actual_requirement_rfq_po",
	"custom_pack_size",
	"custom_nos",
	"custom_total_issue_qty",
	"custom_balance_qty",
]


def _hide_custom_field(doctype, fieldname):
	cf = frappe.db.get_value("Custom Field", {"dt": doctype, "fieldname": fieldname}, "name")
	if cf:
		frappe.db.set_value("Custom Field", cf, "hidden", 1)


def _hide_standard_field(doctype, fieldname):
	frappe.make_property_setter(
		{
			"doctype": doctype,
			"fieldname": fieldname,
			"property": "hidden",
			"value": 1,
			"property_type": "Check",
		},
		is_system_generated=False,
	)


def execute():
	# --- Task 4: hide PO custom fields ---
	_hide_custom_field("Purchase Order", "custom_grn_created")
	_hide_custom_field("Purchase Order", "custom_gate_pass_available")
	frappe.clear_cache(doctype="Purchase Order")

	# --- Task 6: hide GRN standard fields ---
	_hide_standard_field("Purchase Receipt", "supplier_delivery_note")
	_hide_standard_field("Purchase Receipt", "apply_putaway_rule")
	frappe.clear_cache(doctype="Purchase Receipt")

	# --- Task 8: freeze MR Item computed columns after submit (no Update button) ---
	# Use Property Setters (not Custom Field edits) so the change survives fixture re-sync
	# for fields owned by other apps' fixtures.
	for fieldname in MR_ITEM_FREEZE_AFTER_SUBMIT:
		if frappe.get_meta("Material Request Item").get_field(fieldname):
			frappe.make_property_setter(
				{
					"doctype": "Material Request Item",
					"fieldname": fieldname,
					"property": "allow_on_submit",
					"value": 0,
					"property_type": "Check",
				},
				is_system_generated=False,
			)
	frappe.clear_cache(doctype="Material Request Item")

	# --- Task 7: Material Request 'Source Document' reference field ---
	create_custom_fields(
		{
			"Material Request": [
				{
					"fieldname": "custom_source_document",
					"label": "Source Document",
					"fieldtype": "Data",
					"read_only": 1,
					"insert_after": "custom_requested_by_user",
					"module": "pratap",
					"description": "The document this request's data was fetched from (e.g. a Forecast Club).",
				}
			]
		},
		ignore_validate=True,
	)
	frappe.clear_cache(doctype="Material Request")

	# Backfill Source Document on existing MRs from their items' linked Forecast Club.
	frappe.db.sql(
		"""
		update `tabMaterial Request` mr
		set mr.custom_source_document = (
			select concat('Forecast Club: ', group_concat(distinct mri.custom_forecast_club separator ', '))
			from `tabMaterial Request Item` mri
			where mri.parent = mr.name and ifnull(mri.custom_forecast_club, '') != ''
		)
		where exists (
			select 1 from `tabMaterial Request Item` mri2
			where mri2.parent = mr.name and ifnull(mri2.custom_forecast_club, '') != ''
		)
		"""
	)
