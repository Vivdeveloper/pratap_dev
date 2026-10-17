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

    items_by_wo = {}
    for it in items:
        items_by_wo.setdefault(it.parent, []).append(it)

    # Coverage from Material Requests already linked to these Work Orders:
    #   * submitted MR qty nets off the picker qty PER LINKED WORK ORDER — only MRs linked to
    #     a specific WO (via custom_work_order_connection) reduce THAT WO's demand, so a brand-
    #     new WO is never hidden by MRs raised for other WOs that share the same item.
    #   * draft MRs don't reduce qty but are shown as an identifier/link (drops off on submit).
    submitted_by_wo_item, draft_mrs_by_wo_item = _mr_coverage(
        work_orders, items_by_wo
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

    for wo in work_orders:
        for it in items_by_wo.get(wo.name, []):
            expected = flt(it.custom_qty_amount)
            if expected <= 0:
                continue  # nothing to request -> hide (expected/MR Qty = 0)

            covered = flt(submitted_by_wo_item.get((wo.name, it.item_code), 0.0))
            remaining = flt(expected - covered, 3)
            if remaining <= 0:
                continue  # fully covered by submitted MRs linked to THIS WO -> hide

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


def _mr_coverage(work_orders, items_by_wo):
    """Material Request coverage for items linked to a set of Work Orders.

    Links are read from Material Request Item.custom_work_order_connection (a comma-separated
    list of Work Order names). Returns:
        submitted_by_wo_item   = {(work_order, item_code): submitted qty NETTED to that WO}
        draft_mrs_by_wo_item   = {(work_order, item_code): [draft MR names]}

    A submitted MR item nets off ONLY the Work Orders it is linked to — never an unrelated WO
    that merely shares the same item. A combined MR row (linked to several WOs) has its qty
    allocated greedily across just those linked WOs' demand, so it is never double-counted.
    """
    submitted_by_wo_item = {}
    draft_mrs_by_wo_item = {}
    wo_names = [wo.name for wo in work_orders]
    if not wo_names:
        return submitted_by_wo_item, draft_mrs_by_wo_item

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
    # Fetch order so a combined MR covers the earlier WO(s) first (matches the card order).
    wo_order = {wo.name: i for i, wo in enumerate(work_orders)}
    # Per-WO per-item demand (MR Qty) used to cap greedy allocation of a submitted MR row.
    demand = {}
    for wo in work_orders:
        for it in items_by_wo.get(wo.name, []):
            demand[(wo.name, it.item_code)] = flt(it.custom_qty_amount)

    counted = set()  # (mr_name, item_code) — one MR row contributes once
    for r in rows:
        linked = [w.strip() for w in (r.conn or "").split(",") if w.strip()]
        relevant = [w for w in linked if w in wo_set]
        if not relevant:
            continue

        if r.docstatus == 1:
            key = (r.mr_name, r.item_code)
            if key in counted:
                continue
            counted.add(key)
            # Allocate this MR row's qty greedily across ITS linked WOs only, capped at each
            # WO's remaining demand so we never credit more than that WO actually needs.
            remaining_qty = flt(r.qty)
            for wo in sorted(relevant, key=lambda w: wo_order.get(w, 1e9)):
                if remaining_qty <= 0:
                    break
                k = (wo, r.item_code)
                already = flt(submitted_by_wo_item.get(k, 0.0))
                need = max(0.0, flt(demand.get(k, 0.0)) - already)
                take = min(remaining_qty, need)
                if take > 0:
                    submitted_by_wo_item[k] = already + take
                    remaining_qty -= take
        else:
            for wo in relevant:
                lst = draft_mrs_by_wo_item.setdefault((wo, r.item_code), [])
                if r.mr_name not in lst:
                    lst.append(r.mr_name)

    return submitted_by_wo_item, draft_mrs_by_wo_item
