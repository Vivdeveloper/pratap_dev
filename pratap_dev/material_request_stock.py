# Copyright (c) 2026, pratap_dev contributors
# License: MIT

import frappe
from frappe.utils import flt


@frappe.whitelist()
def get_item_pipeline_status(item_code, company):
    """Return in-pipeline purchase qty for an item, split by GRN stage.

    Mirrors the draft-GRN-qty logic in purchase_order_grn.get_grn_stats_for_po,
    but rolled up across every open Purchase Order for the item (company-wide)
    instead of a single PO:
        - pending_pr_for_grn: ordered (submitted PO) but no GRN raised at all yet.
        - pending_grn_qc: GRN raised (Purchase Receipt entered) but that receipt
          is still in draft, i.e. awaiting Quality Inspection approval before
          it becomes usable stock (see pratap_dev's GRN-QC auto-submit flow).
    """
    if not item_code or not company:
        return {"pending_pr_for_grn": 0, "pending_grn_qc": 0}

    rows = frappe.db.sql(
        """
        SELECT
            poi.qty AS po_qty,
            poi.received_qty AS received_qty,
            COALESCE(draft.draft_grn_qty, 0) AS draft_grn_qty
        FROM `tabPurchase Order Item` poi
        INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
        LEFT JOIN (
            SELECT pri.purchase_order_item, SUM(pri.qty) AS draft_grn_qty
            FROM `tabPurchase Receipt Item` pri
            INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
            WHERE pr.docstatus = 0
            GROUP BY pri.purchase_order_item
        ) draft ON draft.purchase_order_item = poi.name
        WHERE poi.item_code = %(item_code)s
            AND po.docstatus = 1
            AND po.company = %(company)s
        """,
        {"item_code": item_code, "company": company},
        as_dict=True,
    )

    pending_pr_for_grn = 0.0
    pending_grn_qc = 0.0

    for row in rows:
        draft_qty = flt(row.draft_grn_qty)
        pending_grn_qc += draft_qty
        pending_pr_for_grn += max(flt(row.po_qty) - flt(row.received_qty) - draft_qty, 0)

    return {"pending_pr_for_grn": pending_pr_for_grn, "pending_grn_qc": pending_grn_qc}


# Raw-material stock warehouses shown/summed on Purchase Material Requests. "Plant 1/2
# WIP RM" as a prefix also matches the "…- JOB WORK" warehouse, so JOB WORK is excluded
# and only leaf warehouses are used (mirrors the Work Order stock lookup).
RM_STOCK_WAREHOUSE_PREFIXES = ["Main Store RM", "Plant 1 WIP RM", "Plant 2 WIP RM"]


def _resolve_stock_warehouse(prefix, company):
    rows = frappe.get_all(
        "Warehouse",
        filters=[
            ["warehouse_name", "like", prefix + "%"],
            ["warehouse_name", "not like", "%JOB WORK%"],
            ["company", "=", company],
            ["is_group", "=", 0],
        ],
        fields=["name"],
        order_by="name asc",
        limit=1,
    )
    return rows[0].name if rows else None


def _total_rm_stock(item_code, company):
    from erpnext.stock.utils import get_latest_stock_qty

    total = 0.0
    for prefix in RM_STOCK_WAREHOUSE_PREFIXES:
        wh = _resolve_stock_warehouse(prefix, company)
        if wh:
            total += flt(get_latest_stock_qty(item_code, wh))
    return total


def update_pipeline_fields(doc, method=None):
    """Server-side compute of the Purchase Material Request Item pipeline columns so they
    ALWAYS update on save — not only when the client-side script happens to run.

    Per item:
      * custom_pending_pr_for_grn  — ordered on submitted POs, no GRN raised yet.
      * custom_pending_grn_qc      — GRN entered but still draft (awaiting QC approval).
      * custom_total_stock_qty     — on-hand across the 3 RM warehouses (excl. JOB WORK).
      * custom_required_qty_for_pr — expected − stock − pending PR − pending GRN (floored 0).

    Hooked on validate (drafts) and before_update_after_submit (submitted), so the columns
    reflect the POs raised for the order in every state. The fields are allow_on_submit so
    the after-submit recompute persists.
    """
    if (doc.get("material_request_type") or "") != "Purchase":
        return

    for row in doc.get("items") or []:
        if not row.item_code:
            continue

        pipe = get_item_pipeline_status(row.item_code, doc.company)
        pending_pr = flt(pipe.get("pending_pr_for_grn"))
        pending_grn = flt(pipe.get("pending_grn_qc"))
        total_stock = _total_rm_stock(row.item_code, doc.company)

        row.custom_pending_pr_for_grn = pending_pr
        row.custom_pending_grn_qc = pending_grn
        row.custom_total_stock_qty = total_stock

        expected = flt(row.get("custom_expected_qty")) or flt(row.qty)
        required = expected - total_stock - pending_pr - pending_grn
        row.custom_required_qty_for_pr = required if required > 0 else 0
