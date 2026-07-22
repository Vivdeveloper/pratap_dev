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
