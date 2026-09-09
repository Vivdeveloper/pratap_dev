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

    # Coverage from Material Requests already linked to these Work Orders:
    #   * submitted MR qty nets off the picker qty (item disappears once fully covered);
    #   * draft MRs don't reduce qty but are shown as an identifier/link so the user can
    #     see it's already in a draft MR (and it drops off once that MR is submitted).
    submitted_by_item, draft_mrs_by_wo_item = _mr_coverage(wo_names)

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

    items_by_wo = {}
    for it in items:
        items_by_wo.setdefault(it.parent, []).append(it)

    # Net off submitted MR qty per item, consumed greedily in Work Order fetch order, so
    # a fully-requested item drops off the earlier WO(s) first and any leftover shows as
    # the remaining short qty on the next WO.
    pool = dict(submitted_by_item)
    for wo in work_orders:
        for it in items_by_wo.get(wo.name, []):
            expected = flt(it.custom_qty_amount)
            if expected <= 0:
                continue  # nothing to request -> hide (expected/MR Qty = 0)

            covered = min(expected, flt(pool.get(it.item_code, 0.0)))
            pool[it.item_code] = flt(pool.get(it.item_code, 0.0)) - covered
            remaining = flt(expected - covered, 3)
            if remaining <= 0:
                continue  # fully covered by submitted MRs -> hide

            grouped[wo.name]["items"].append(
                {
                    "item_code": it.item_code,
                    "item_name": it.item_name,
                    "qty": remaining,
                    "draft_mrs": draft_mrs_by_wo_item.get((wo.name, it.item_code), []),
                }
            )

    # Drop Work Order cards whose items are all covered/zero.
    return [g for g in grouped.values() if g["items"]]


def _mr_coverage(wo_names):
    """Material Request coverage for items linked to a set of Work Orders.

    Links are read from Material Request Item.custom_work_order_connection (a comma-
    separated list of Work Order names). Returns:
        submitted_by_item      = {item_code: total qty in SUBMITTED MRs}
        draft_mrs_by_wo_item   = {(work_order, item_code): [draft MR names]}

    Submitted qty is counted once per (MR, item) even when the MR item links to several
    Work Orders, so the netting never double-counts a combined MR row.
    """
    submitted_by_item = {}
    draft_mrs_by_wo_item = {}
    if not wo_names:
        return submitted_by_item, draft_mrs_by_wo_item

    rows = frappe.db.sql(
        """
        SELECT mri.item_code, mri.qty, mri.custom_work_order_connection AS conn,
               mr.name AS mr_name, mr.docstatus
        FROM `tabMaterial Request Item` mri
        INNER JOIN `tabMaterial Request` mr ON mr.name = mri.parent
        WHERE mr.docstatus < 2
          AND IFNULL(mri.custom_work_order_connection, '') != ''
        """,
        as_dict=True,
    )

    wo_set = set(wo_names)
    counted = set()  # (mr_name, item_code) already added to submitted_by_item
    for r in rows:
        linked = [w.strip() for w in (r.conn or "").split(",") if w.strip()]
        relevant = [w for w in linked if w in wo_set]
        if not relevant:
            continue

        if r.docstatus == 1:
            key = (r.mr_name, r.item_code)
            if key not in counted:
                counted.add(key)
                submitted_by_item[r.item_code] = (
                    flt(submitted_by_item.get(r.item_code, 0.0)) + flt(r.qty)
                )
        else:
            for wo in relevant:
                lst = draft_mrs_by_wo_item.setdefault((wo, r.item_code), [])
                if r.mr_name not in lst:
                    lst.append(r.mr_name)

    return submitted_by_item, draft_mrs_by_wo_item
