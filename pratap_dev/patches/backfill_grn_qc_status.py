# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Backfill custom_qc_status on existing GRNs.

Adding the field defaulted every existing Purchase Receipt (including already-submitted
ones) to "Draft". Set submitted GRNs to "Submitted" so the QC lifecycle status is
accurate for the list indicator and the standard filter.
"""

import frappe


def execute():
	if not frappe.db.has_column("Purchase Receipt", "custom_qc_status"):
		return

	# Submitted GRNs -> Submitted.
	frappe.db.sql(
		"update `tabPurchase Receipt` set custom_qc_status = 'Submitted' where docstatus = 1"
	)
