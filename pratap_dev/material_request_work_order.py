# Copyright (c) 2026, pratap_dev contributors
# License: MIT

import frappe
from frappe.utils import flt


@frappe.whitelist()
def get_work_orders_for_material_request():
    """Return submitted, Not Started Work Orders grouped with their required items,
    including the Plant and Forecast Type (fetched from the linked Forecast Club).

    Shape mirrors the Sales Forecast picker so the Material Request dialog can show
    the same Plant / Forecast Type chips on the group header:
        [{ "work_order": <name>, "status": <status>,
           "plant": <plant>, "forecast_type": <type>,
           "items": [{ "item_code", "item_name", "qty" }] }]
    """
    work_orders = frappe.get_all(
        "Work Order",
        filters={"status": "Not Started", "docstatus": 1},
        fields=["name", "status", "custom_forecast_club"],
        order_by="modified desc",
    )
    if not work_orders:
        return []

    # Fetch Plant + Forecast Type from each WO's linked Forecast Club (one query).
    club_names = list({wo.custom_forecast_club for wo in work_orders if wo.custom_forecast_club})
    club_map = {}
    if club_names:
        for fc in frappe.get_all(
            "Forecast Club",
            filters={"name": ["in", club_names]},
            fields=["name", "plant", "forecast_type"],
        ):
            club_map[fc.name] = fc

    wo_names = [wo.name for wo in work_orders]
    items = frappe.get_all(
        "Work Order Item",
        filters={"parent": ["in", wo_names]},
        fields=["parent", "item_code", "item_name", "custom_qty_amount"],
        order_by="idx asc",
    )

    grouped = {}
    for wo in work_orders:
        fc = club_map.get(wo.custom_forecast_club) or {}
        grouped[wo.name] = {
            "work_order": wo.name,
            "status": wo.status,
            "plant": fc.get("plant"),
            "forecast_type": fc.get("forecast_type"),
            "items": [],
        }

    for it in items:
        grouped[it.parent]["items"].append(
            {
                "item_code": it.item_code,
                "item_name": it.item_name,
                "qty": flt(it.custom_qty_amount) or 0,
            }
        )

    return list(grouped.values())
