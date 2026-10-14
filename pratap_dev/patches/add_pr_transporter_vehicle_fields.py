# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Add a 'Supplier & Vehicle Details' section to the GRN (Purchase Receipt) that mirrors the
Gate Pass doctype's transporter/vehicle fields. These are captured in the "Create GRN" popup
(auto-filled from the linked Gate Pass, editable) and stored on the GRN. Idempotent."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Purchase Receipt": [
				{
					"fieldname": "custom_supplier_vehicle_section",
					"label": "Supplier & Vehicle Details",
					"fieldtype": "Section Break",
					"insert_after": "custom_gate_pass",
					"collapsible": 1,
					"module": "pratap",
				},
				{
					"fieldname": "custom_actual_received_qty",
					"label": "Actual Received Qty",
					"fieldtype": "Data",
					"insert_after": "custom_supplier_vehicle_section",
					"module": "pratap",
				},
				{
					"fieldname": "custom_transporter_id",
					"label": "Transporter ID",
					"fieldtype": "Data",
					"insert_after": "custom_actual_received_qty",
					"module": "pratap",
				},
				{
					"fieldname": "custom_vehicle_no",
					"label": "Vehicle No",
					"fieldtype": "Data",
					"insert_after": "custom_transporter_id",
					"module": "pratap",
				},
				{
					"fieldname": "custom_driver_id",
					"label": "Driver ID",
					"fieldtype": "Link",
					"options": "Driver",
					"insert_after": "custom_vehicle_no",
					"module": "pratap",
				},
				{
					"fieldname": "custom_driver_full_name",
					"label": "Driver Full Name",
					"fieldtype": "Data",
					"insert_after": "custom_driver_id",
					"module": "pratap",
				},
				{
					"fieldname": "custom_driver_contact",
					"label": "Driver Contact",
					"fieldtype": "Data",
					"insert_after": "custom_driver_full_name",
					"module": "pratap",
				},
				{
					"fieldname": "custom_vehicle_col_break",
					"fieldtype": "Column Break",
					"insert_after": "custom_driver_contact",
					"module": "pratap",
				},
				{
					"fieldname": "custom_vehicle_fitness_certificate",
					"label": "Vehicle Fitness Certificate",
					"fieldtype": "Select",
					"options": "\nValid\nInvalid",
					"insert_after": "custom_vehicle_col_break",
					"module": "pratap",
				},
				{
					"fieldname": "custom_puc",
					"label": "PUC",
					"fieldtype": "Select",
					"options": "\nValid\nInvalid",
					"insert_after": "custom_vehicle_fitness_certificate",
					"module": "pratap",
				},
				{
					"fieldname": "custom_insurance",
					"label": "Insurance",
					"fieldtype": "Select",
					"options": "\nValid\nInvalid",
					"insert_after": "custom_puc",
					"module": "pratap",
				},
			]
		},
		ignore_validate=True,
	)
	frappe.clear_cache(doctype="Purchase Receipt")
