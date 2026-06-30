# Copyright (c) 2026, pratap_dev contributors
# License: MIT

import frappe
from frappe.utils import flt


@frappe.whitelist()
def get_forecast_clubs_for_material_request():
    """Return Forecast Clubs (Sales Forecast) grouped with their material request items.

    Shape mirrors the Work Order picker so the Material Request dialog can reuse the
    same card/checkbox UI:
        [{ "forecast_club": <name>, "status": <status>,
           "items": [{ "item_code", "item_name", "qty", "uom" }] }]
    Only non-cancelled Forecast Clubs that actually have material request items are
    returned.
    """
    clubs = frappe.get_all(
        "Forecast Club",
        filters={"docstatus": ["<", 2]},
        fields=["name", "status"],
        order_by="modified desc",
    )
    if not clubs:
        return []

    club_names = [club.name for club in clubs]
    rows = frappe.get_all(
        "Forecast Club Material Request Item",
        filters={"parent": ["in", club_names]},
        fields=["parent", "item_code", "qty", "uom"],
        order_by="idx asc",
    )

    item_codes = list({row.item_code for row in rows if row.item_code})
    name_map = {}
    if item_codes:
        for item in frappe.get_all(
            "Item", filters={"name": ["in", item_codes]}, fields=["name", "item_name"]
        ):
            name_map[item.name] = item.item_name

    grouped = {
        club.name: {"forecast_club": club.name, "status": club.status, "items": []}
        for club in clubs
    }

    for row in rows:
        if not row.item_code or flt(row.qty) <= 0:
            continue
        grouped[row.parent]["items"].append(
            {
                "item_code": row.item_code,
                "item_name": name_map.get(row.item_code, ""),
                "qty": flt(row.qty),
                "uom": row.uom,
            }
        )

    return [group for group in grouped.values() if group["items"]]
