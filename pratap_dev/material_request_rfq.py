# Copyright (c) 2026, pratap_dev contributors
# License: MIT

import json

import frappe
from frappe import _


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

    items = []
    seen_items = set()
    for row in mr.items:
        if not row.item_code or row.item_code in seen_items:
            continue
        seen_items.add(row.item_code)
        items.append({"item_code": row.item_code, "item_name": row.item_name})

    item_codes = list(seen_items)
    if not item_codes:
        return {"items": [], "suppliers": [], "supplier_item_map": {}, "already_created": []}

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

    return {
        "items": items,
        "suppliers": [
            {"supplier": s, "supplier_name": supplier_names.get(s) or s} for s in supplier_list
        ],
        "supplier_item_map": {item_code: sorted(v) for item_code, v in supplier_item_map.items()},
        "already_created": [list(pair) for pair in already_created],
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

        if not doc.items:
            continue

        doc.append("suppliers", {"supplier": supplier, "send_email": 1})
        doc.insert()
        rfq_names.append(doc.name)

    if not rfq_names:
        frappe.throw(_("Selected items were not found on this Material Request."))

    return rfq_names
