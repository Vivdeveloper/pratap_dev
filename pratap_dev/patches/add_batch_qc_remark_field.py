# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Add a "QC Remark" (custom_qc_remark) Data field on the Batch doctype. The per-batch QC
Remark entered in the Pratap Quality Inspection "Batch QC Details" table is mirrored here.
Idempotent — safe to re-run."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Batch": [
				{
					"fieldname": "custom_qc_remark",
					"label": "QC Remark",
					"fieldtype": "Data",
					"insert_after": "custom_density",
					"read_only": 0,
					"module": "pratap",
					"description": "Remark captured per batch during QC (from the Batch QC Details table).",
				}
			]
		},
		ignore_validate=True,
	)
	frappe.clear_cache(doctype="Batch")
