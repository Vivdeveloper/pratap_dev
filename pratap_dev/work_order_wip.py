# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Drive Work Order warehouses from the production item master.

The production Item carries a "Processing Location" (Item.custom_job_work_warehouse) and a
"Raw Material Location" (Item.custom_raw_material_location). The Work Order's WIP warehouse
mirrors the Processing Location and the Custom Source Warehouse mirrors the Raw Material
Location, so the operator never has to pick them by hand and they always match where that
item is actually processed / sourced from.
"""

import frappe


def set_wip_warehouse_from_item(doc, method=None):
    """Set the Work Order's `wip_warehouse` from the production item's Processing Location
    (Item.custom_job_work_warehouse) and `custom_custom_source_warehouse` from its Raw
    Material Location (Item.custom_raw_material_location). Runs before_validate so ERPNext
    validates the correct warehouse. Only overrides when the item actually defines the
    location — items without one keep the existing value."""
    if not doc.get("production_item"):
        return
    processing_location, raw_material_location = frappe.db.get_value(
        "Item",
        doc.production_item,
        ["custom_job_work_warehouse", "custom_raw_material_location"],
    )
    if processing_location:
        doc.wip_warehouse = processing_location
    if raw_material_location:
        doc.custom_custom_source_warehouse = raw_material_location
