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
    # Exclude Forecast Clubs whose Material Request is already created
    # (status "Material Requested") so they no longer show in the picker.
    clubs = frappe.get_all(
        "Forecast Club",
        filters={"docstatus": ["<", 2], "status": ["!=", "Material Requested"]},
        fields=["name", "status", "plant", "forecast_type"],
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

    # (forecast club, item) pairs already procured -> hide them from the picker.
    procured = _get_procured_forecast_items(club_names)

    item_codes = list({row.item_code for row in rows if row.item_code})
    name_map = {}
    if item_codes:
        for item in frappe.get_all(
            "Item", filters={"name": ["in", item_codes]}, fields=["name", "item_name"]
        ):
            name_map[item.name] = item.item_name

    grouped = {
        club.name: {
            "forecast_club": club.name,
            "status": club.status,
            "plant": club.plant,
            "forecast_type": club.forecast_type,
            "items": [],
        }
        for club in clubs
    }

    for row in rows:
        if not row.item_code or flt(row.qty) <= 0:
            continue
        # Skip items already procured (a Purchase Order was raised for this forecast
        # club + item), so they don't reappear in the picker.
        if (row.parent, row.item_code) in procured:
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


def _get_procured_forecast_items(club_names):
    """Return a set of (forecast_club, item_code) pairs that already have a Purchase
    Order raised against them.

    Chain: Forecast Club item -> Material Request Item (custom_forecast_club = club) ->
    Purchase Order Item (material_request_item). A non-cancelled PO (docstatus < 2) on
    any quantity is enough to hide the item from the Sales Forecast picker.
    """
    if not club_names:
        return set()

    rows = frappe.db.sql(
        """
        SELECT DISTINCT mri.custom_forecast_club AS club, mri.item_code AS item_code
        FROM `tabPurchase Order Item` poi
        INNER JOIN `tabMaterial Request Item` mri ON mri.name = poi.material_request_item
        INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
        WHERE po.docstatus < 2
          AND mri.custom_forecast_club IN %(clubs)s
          AND IFNULL(mri.item_code, '') != ''
        """,
        {"clubs": tuple(club_names)},
        as_dict=True,
    )
    return {(r.club, r.item_code) for r in rows}
