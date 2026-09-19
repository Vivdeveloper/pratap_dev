# Copyright (c) 2026, pratap_dev contributors
# License: MIT

import frappe
from frappe import _
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


# JOB WORK warehouses whose OUTs (consumption) feed the Last Month / 3-month consumption
# columns. Naming varies slightly ("Plant 1 WIP RM- JOB WORK - PTPL"), so match by the
# plant prefix AND "JOB WORK".
JOB_WORK_CONSUMPTION_PREFIXES = ["Plant 1 WIP RM", "Plant 2 WIP RM"]


def _job_work_warehouses(company):
    out = []
    for prefix in JOB_WORK_CONSUMPTION_PREFIXES:
        rows = frappe.get_all(
            "Warehouse",
            filters=[
                ["warehouse_name", "like", prefix + "%"],
                ["warehouse_name", "like", "%JOB WORK%"],
                ["company", "=", company],
                ["is_group", "=", 0],
            ],
            fields=["name"],
        )
        out.extend(r.name for r in rows)
    return out


def _month_window(months_back):
    """(first_day, last_day) of the calendar month `months_back` months before today."""
    from frappe.utils import getdate, nowdate, add_months, get_first_day, get_last_day

    ref = add_months(getdate(nowdate()), -months_back)
    return get_first_day(ref), get_last_day(ref)


def _consumption_out(item_code, warehouses, start, end):
    """Total outward (consumed) qty for an item across `warehouses` in [start, end].
    Sums the absolute value of negative Stock Ledger movements (issues/consumption)."""
    if not (item_code and warehouses):
        return 0.0
    rows = frappe.db.sql(
        """
        SELECT COALESCE(SUM(-actual_qty), 0)
        FROM `tabStock Ledger Entry`
        WHERE item_code = %(item)s
          AND warehouse IN %(whs)s
          AND is_cancelled = 0
          AND actual_qty < 0
          AND posting_date BETWEEN %(start)s AND %(end)s
        """,
        {"item": item_code, "whs": tuple(warehouses), "start": start, "end": end},
    )
    return flt(rows[0][0]) if rows else 0.0


@frappe.whitelist()
def get_item_rfq_metrics(item_code, company):
    """Live values for the RFQ/planning columns so the grid fills on item entry (before
    save), mirroring the pipeline/stock live-fill. Server `update_pipeline_fields` remains
    the authoritative compute on save."""
    if not item_code or not company:
        return {}
    cons = _consumption_metrics(item_code, company)
    return {
        "last_month_consumption": cons["last_month"],
        "min_level_avg_consumption": cons["avg_3m"],
        "max_level_consumption": cons["max_3m"],
        "last_month_purchase": _last_month_purchase_qty(item_code, company),
        "current_requirement": _wo_requirement(item_code, company),
    }


def _wo_requirement(item_code, company):
    """Current Requirement (as per BOM / Forecast vs Planning): the gross RM qty the active
    production plan needs. Sums Work Order Item.required_qty (BOM-exploded) across submitted
    Work Orders that are still open (not Completed / Stopped / Closed) for the item. WIP/store
    stock is netted off later in 'Requirement generate for the Month' (= this − stock)."""
    rows = frappe.db.sql(
        """
        SELECT COALESCE(SUM(woi.required_qty), 0)
        FROM `tabWork Order Item` woi
        INNER JOIN `tabWork Order` wo ON wo.name = woi.parent
        WHERE woi.item_code = %(item)s
          AND wo.docstatus = 1
          AND wo.company = %(company)s
          AND wo.status NOT IN ('Completed', 'Stopped', 'Closed')
        """,
        {"item": item_code, "company": company},
    )
    return flt(rows[0][0]) if rows else 0.0


def _last_month_purchase_qty(item_code, company):
    """Qty ordered on submitted Purchase Orders whose transaction date falls in last
    calendar month (company-wide, for the item)."""
    start, end = _month_window(1)
    rows = frappe.db.sql(
        """
        SELECT COALESCE(SUM(poi.qty), 0)
        FROM `tabPurchase Order Item` poi
        INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
        WHERE poi.item_code = %(item)s
          AND po.docstatus = 1
          AND po.company = %(company)s
          AND po.transaction_date BETWEEN %(start)s AND %(end)s
        """,
        {"item": item_code, "company": company, "start": start, "end": end},
    )
    return flt(rows[0][0]) if rows else 0.0


def _consumption_metrics(item_code, company):
    """Last-month consumption plus 3-month average and max monthly consumption, using the
    JOB WORK warehouses' outward movements."""
    whs = _job_work_warehouses(company)
    if not whs:
        return {"last_month": 0.0, "avg_3m": 0.0, "max_3m": 0.0}

    # last month (m-1)
    ls, le = _month_window(1)
    last_month = _consumption_out(item_code, whs, ls, le)

    # last 3 months (m-1, m-2, m-3) for avg + max
    monthly = []
    for m in (1, 2, 3):
        s, e = _month_window(m)
        monthly.append(_consumption_out(item_code, whs, s, e))

    avg_3m = sum(monthly) / 3.0 if monthly else 0.0
    max_3m = max(monthly) if monthly else 0.0
    return {"last_month": last_month, "avg_3m": avg_3m, "max_3m": max_3m}


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
        required = required if required > 0 else 0
        row.custom_required_qty_for_pr = required

        # RFQ/Purchase columns (from the RM-requirement sheet):
        #   Last Month Consumption / 3-month Avg & Max — JOB WORK warehouse OUTs.
        #   Last Month Purchase — qty ordered on last month's POs.
        if hasattr(row, "custom_last_month_consumption") or hasattr(row, "custom_last_month_purchase"):
            cons = _consumption_metrics(row.item_code, doc.company)
            row.custom_last_month_consumption = cons["last_month"]
            row.custom_min_level_avg_consumption = cons["avg_3m"]
            row.custom_max_level_consumption = cons["max_3m"]
            row.custom_last_month_purchase = _last_month_purchase_qty(row.item_code, doc.company)

            # Current Requirement As per BOM / Forecast vs Planning — from active Work Orders
            # (BOM-exploded RM qty). Falls back to the row's expected/forecast qty when the
            # item is in no open Work Order yet.
            wo_req = _wo_requirement(row.item_code, doc.company)
            row.custom_current_requirement = wo_req if wo_req > 0 else expected

            # Actual Requirement for RFQ/P.O is editable ("Edit Option for Qty"); seed it with
            # the sheet formula  N = G + L - M  = Max Level Consumption + Requirement generate
            # for the Month - Pipe Line (PO/GRN pending), only when the user hasn't entered one.
            if not flt(row.get("custom_actual_requirement_rfq_po")):
                row.custom_actual_requirement_rfq_po = flt(cons["max_3m"]) + required - pending_pr


def move_fulfilled_items(doc, method=None):
    """For a Purchase Material Request, remove rows whose warehouse stock already covers the
    expected qty (the "Already Fulfilled — No PO" set) from the Items child table so they do
    NOT move forward to a PO. The removed rows are snapshotted to custom_fulfilled_items_json
    so they still show in the "Already Fulfilled" box below.

    Runs on validate (drafts) only — items can't be changed after submit. Idempotent and
    additive: the snapshot accumulates across saves, de-duplicated by item_code.
    """
    import json

    if (doc.get("material_request_type") or "") != "Purchase":
        return

    # existing snapshot (keyed by item_code) so it persists across repeated saves
    snapshot = {}
    if doc.get("custom_fulfilled_items_json"):
        try:
            for s in json.loads(doc.custom_fulfilled_items_json) or []:
                if s.get("item_code"):
                    snapshot[s["item_code"]] = s
        except (ValueError, TypeError):
            snapshot = {}

    keep = []
    for row in doc.get("items") or []:
        expected = flt(row.get("custom_expected_qty")) or flt(row.qty)
        stock = flt(row.get("custom_total_stock_qty"))
        is_fulfilled = expected > 0 and stock + 1e-9 >= expected
        if is_fulfilled and row.item_code:
            snapshot[row.item_code] = {
                "item_code": row.item_code,
                "item_name": row.item_name,
                "custom_expected_qty": expected,
                "custom_total_stock_qty": stock,
                "custom_required_qty_for_pr": 0,
            }
        else:
            keep.append(row)

    doc.custom_fulfilled_items_json = json.dumps(list(snapshot.values()))

    if len(keep) != len(doc.get("items") or []):
        # Don't leave the MR with zero items (ERPNext rejects that) — if EVERYTHING is
        # fulfilled, stop with a clear message rather than a generic error.
        if not keep:
            frappe.throw(
                _(
                    "All requested items are already fulfilled from stock — no Purchase "
                    "Material Request is needed."
                )
            )
        # renumber idx and replace the table
        for i, row in enumerate(keep, start=1):
            row.idx = i
        doc.set("items", keep)
