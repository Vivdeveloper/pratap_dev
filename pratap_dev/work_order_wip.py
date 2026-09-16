# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Drive the Work Order's Work-in-Progress Warehouse from the production item master.

The production Item carries a "Processing Location" (Item.custom_job_work_warehouse). The
Work Order's WIP warehouse should mirror it, so the operator never has to pick it by hand
and it always matches where that item is actually processed.
"""

import frappe


def set_wip_warehouse_from_item(doc, method=None):
    """Set the Work Order's `wip_warehouse` from the production item's Processing Location
    (Item.custom_job_work_warehouse). Runs before_validate so ERPNext validates the correct
    warehouse. Only overrides when the item actually defines a Processing Location — items
    without one keep the ERPNext/Manufacturing-Settings default."""
    if not doc.get("production_item"):
        return
    processing_location = frappe.db.get_value(
        "Item", doc.production_item, "custom_job_work_warehouse"
    )
    if processing_location:
        doc.wip_warehouse = processing_location
