# Copyright (c) 2026, pratap_dev contributors
# License: MIT

import json

import frappe
from frappe import _
from frappe.utils import flt


@frappe.whitelist()
def get_rfq_matrix_data(material_request):
    """Return the Supplier x Item matrix data for the RFQ picker dialog on a
    submitted Purchase Material Request.

    Suppliers per item come from "Party Specific Item" (party_type=Supplier,
    restrict_based_on=Item, based_on_value=item_code) — this is the org's
    chosen source of supplier-item eligibility for RFQ purposes, distinct from
    Item Supplier (used elsewhere for the custom_supplier_ field).
    """
    mr = frappe.get_doc("Material Request", material_request)
    mr.check_permission("read")

    # Aggregate MR qty per item across all MR rows so each item card can show:
    # MR Qty, how much already has a PO, and how much is pending.
    items = []
    seen_items = set()
    agg = {}
    row_names_by_item = {}
    for row in mr.items:
        if not row.item_code:
            continue
        if row.item_code not in agg:
            agg[row.item_code] = {
                "item_code": row.item_code,
                "item_name": row.item_name,
                "uom": row.get("uom") or row.get("stock_uom") or "",
                "mr_qty": 0.0,
                "ordered_qty": 0.0,
            }
            items.append(agg[row.item_code])  # preserve first-seen order
            seen_items.add(row.item_code)
            row_names_by_item[row.item_code] = []
        agg[row.item_code]["mr_qty"] += flt(row.qty)
        row_names_by_item[row.item_code].append(row.name)

    # "PO Made" per item = qty of every SUBMITTED Purchase Order Item that links
    # back to this MR row (material_request_item). This counts supplier-variant POs
    # too (e.g. RM02498-J against a base RM02498 MR row), since the variant PO still
    # carries the base MR row's material_request_item — so the count stays correct
    # even though the RFQ renamed the item to its supplier variant.
    all_row_names = [n for names in row_names_by_item.values() for n in names]
    ordered_by_row = get_ordered_qty_by_mr_row(all_row_names)

    for it in items:
        it["ordered_qty"] = sum(
            ordered_by_row.get(n, 0.0) for n in row_names_by_item[it["item_code"]]
        )
        it["pending_qty"] = max(it["mr_qty"] - it["ordered_qty"], 0.0)
        it["over_ordered"] = it["ordered_qty"] > it["mr_qty"] + 0.0001

    item_codes = list(seen_items)
    if not item_codes:
        return {
            "items": [],
            "suppliers": [],
            "supplier_item_map": {},
            "already_created": [],
            "unmapped_items": [],
        }

    psi_rows = frappe.get_all(
        "Party Specific Item",
        filters={
            "party_type": "Supplier",
            "restrict_based_on": "Item",
            "based_on_value": ["in", item_codes],
        },
        fields=["party as supplier", "based_on_value as item_code"],
    )

    supplier_item_map = {}
    suppliers = set()
    for row in psi_rows:
        supplier_item_map.setdefault(row.item_code, set()).add(row.supplier)
        suppliers.add(row.supplier)

    supplier_names = {}
    if suppliers:
        for s in frappe.get_all(
            "Supplier", filters={"name": ["in", list(suppliers)]}, fields=["name", "supplier_name"]
        ):
            supplier_names[s.name] = s.supplier_name

    already_created = _get_already_created_pairs(material_request)

    supplier_list = sorted(suppliers, key=lambda s: (supplier_names.get(s) or s))

    # Items with no supplier mapped cannot appear under any supplier card. Returning them
    # separately lets the dialog call them out instead of silently dropping them, which
    # made it look like the Material Request had fewer items than it does.
    unmapped_items = [row for row in items if not supplier_item_map.get(row["item_code"])]

    return {
        "items": items,
        "suppliers": [
            {"supplier": s, "supplier_name": supplier_names.get(s) or s} for s in supplier_list
        ],
        "supplier_item_map": {item_code: sorted(v) for item_code, v in supplier_item_map.items()},
        "already_created": [list(pair) for pair in already_created],
        "unmapped_items": unmapped_items,
    }


def _get_already_created_pairs(material_request):
    """(item_code, supplier) pairs already covered by a non-cancelled RFQ for
    this Material Request. An RFQ's item list is shared across all of its
    suppliers, so every item in an existing RFQ is "already created" for
    every supplier on that same RFQ.
    """
    rfq_items = frappe.db.sql(
        """
        SELECT rqi.parent AS rfq, rqi.item_code
        FROM `tabRequest for Quotation Item` rqi
        INNER JOIN `tabRequest for Quotation` rq ON rq.name = rqi.parent
        WHERE rqi.material_request = %(mr)s AND rq.docstatus < 2
        """,
        {"mr": material_request},
        as_dict=True,
    )
    if not rfq_items:
        return set()

    rfq_names = list({row.rfq for row in rfq_items})
    rfq_suppliers = frappe.get_all(
        "Request for Quotation Supplier",
        filters={"parent": ["in", rfq_names]},
        fields=["parent", "supplier"],
    )

    suppliers_by_rfq = {}
    for row in rfq_suppliers:
        suppliers_by_rfq.setdefault(row.parent, set()).add(row.supplier)

    already_created = set()
    for row in rfq_items:
        for supplier in suppliers_by_rfq.get(row.rfq, set()):
            already_created.add((row.item_code, supplier))

    return already_created


def _resolve_supplier_variant(item_code, supplier):
    """Return the supplier-specific variant item for (item_code, supplier), or None to
    keep the item unchanged.

      - If the item is itself a supplier-item (custom_supplier_item_of set) -> None
        (Case B: already a variant, leave as-is).
      - Else if it is a base item with supplier items (custom_has_supplier_item) -> the
        custom_supplier_item from its Item Supplier row for this supplier, if mapped
        (Case A). If no variant is mapped for this exact supplier -> None (keep base).
      - Else -> None (Case C: plain item, keep own code).
    """
    info = frappe.db.get_value(
        "Item", item_code, ["custom_has_supplier_item", "custom_supplier_item_of"], as_dict=True
    )
    if not info:
        return None
    if info.custom_supplier_item_of:
        return None  # Case B
    if not info.custom_has_supplier_item:
        return None  # Case C
    return frappe.db.get_value(
        "Item Supplier",
        {"parent": item_code, "parenttype": "Item", "supplier": supplier},
        "custom_supplier_item",
    ) or None


def _apply_supplier_variant(row, supplier):
    """Swap an RFQ item row to the supplier-specific variant item (code, name,
    description) when one is mapped for this supplier. Qty/UOM/required date are kept."""
    variant = _resolve_supplier_variant(row.item_code, supplier)
    if not variant or variant == row.item_code:
        return
    detail = frappe.db.get_value("Item", variant, ["item_name", "description"], as_dict=True) or {}
    row.item_code = variant
    row.item_name = detail.get("item_name") or variant
    if detail.get("description"):
        row.description = detail.get("description")


@frappe.whitelist()
def create_request_for_quotation(material_request, supplier_items):
    """Create one Request for Quotation per supplier, each carrying only the
    items selected for that supplier. Left as drafts (not submitted/emailed)
    so the user can review them first.
    """
    if isinstance(supplier_items, str):
        supplier_items = json.loads(supplier_items)

    if not supplier_items:
        frappe.throw(_("Please select at least one item/supplier combination."))

    from erpnext.stock.doctype.material_request.material_request import make_request_for_quotation

    rfq_names = []
    for supplier, item_codes in supplier_items.items():
        item_codes = set(item_codes or [])
        if not item_codes:
            continue

        doc = make_request_for_quotation(material_request)
        doc.items = [row for row in doc.items if row.item_code in item_codes]
        for idx, row in enumerate(doc.items):
            row.idx = idx + 1
            # Show the supplier-specific item code (X -> X-A) for this supplier, if any.
            _apply_supplier_variant(row, supplier)

        if not doc.items:
            continue

        doc.append("suppliers", {"supplier": supplier, "send_email": 1})
        doc.insert()
        rfq_names.append(doc.name)

    if not rfq_names:
        frappe.throw(_("Selected items were not found on this Material Request."))

    return rfq_names


def get_ordered_qty_by_mr_row(row_names):
    """Submitted Purchase Order qty per Material Request Item row name.

    Variant-aware: a supplier-variant PO (e.g. RM02498-J) still carries the base
    MR row's material_request_item, so it is counted against that row here. Shared
    by the RFQ picker (PO progress) and the Supplier Quotation partial-PO cap.
    """
    row_names = [n for n in (row_names or []) if n]
    result = {}
    if not row_names:
        return result
    po_rows = frappe.db.sql(
        """
        SELECT poi.material_request_item AS mri, SUM(poi.qty) AS qty
        FROM `tabPurchase Order Item` poi
        INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
        WHERE po.docstatus = 1 AND poi.material_request_item IN %(names)s
        GROUP BY poi.material_request_item
        """,
        {"names": row_names},
        as_dict=True,
    )
    for r in po_rows:
        result[r.mri] = flt(r.qty)
    return result
