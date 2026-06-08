# Copyright (c) 2026, pratap_dev contributors
# License: MIT

import frappe
from frappe import _
from frappe.utils import flt

from erpnext.stock.doctype.purchase_receipt.purchase_receipt import PurchaseReceipt

from pratap_dev.purchase_receipt_batch import _set_batch_from_insert_batch_number


class PratapPurchaseReceipt(PurchaseReceipt):
    def validate(self):
        super().validate()
        self._validate_items_pratap_quality_inspection()
        self._sync_density_from_pratap_qc_on_items()

    def before_save(self):
        for row in self.items:
            _set_batch_from_insert_batch_number(self, row)
    
    def before_cancel(self):
        super().before_cancel()
        self._check_pratap_quality_inspection_before_cancel()

    def before_submit(self):
        self._validate_pratap_quality_inspection_on_items()

    def on_update(self):
        if self.items:
            self.items = self._create_uom_in_items(self.items)

    def _check_pratap_quality_inspection_before_cancel(self):
        if self.is_return:
            return

        for row in self.get("items") or []:
            qc_name = row.get("custom_pratap_quality_inspection")
            if not qc_name:
                continue

            if frappe.db.get_value("Pratap Quality Inspection", qc_name, "docstatus") == 1:
                frappe.throw(
                    _(
                        "Row {0}: Cancel Pratap Quality Inspection {1} before cancelling this Purchase Receipt."
                    ).format(row.idx, qc_name)
                )

    def _validate_items_pratap_quality_inspection(self):
        for row in self.get("items") or []:
            qc_name = row.get("custom_pratap_quality_inspection")
            if not qc_name:
                continue

            if not frappe.db.exists("Pratap Quality Inspection", qc_name):
                frappe.throw(
                    _("Row {0}: Pratap Quality Inspection {1} does not exist.").format(row.idx, qc_name)
                )

            qc = frappe.db.get_value(
                "Pratap Quality Inspection",
                qc_name,
                ["reference_doctype", "reference_name", "production_item", "docstatus"],
                as_dict=True,
            )

            if qc.reference_doctype != self.doctype or qc.reference_name != self.name:
                frappe.throw(
                    _(
                        "Row {0}: Pratap Quality Inspection {1} must reference this Purchase Receipt."
                    ).format(row.idx, qc_name)
                )

            if qc.production_item and row.item_code and qc.production_item != row.item_code:
                frappe.throw(
                    _(
                        "Row {0}: Pratap Quality Inspection {1} is for item {2}, not {3}."
                    ).format(row.idx, qc_name, qc.production_item, row.item_code)
                )

    def _sync_density_from_pratap_qc_on_items(self):
        for row in self.get("items") or []:
            qc_name = row.get("custom_pratap_quality_inspection")
            if not qc_name:
                continue
            density = frappe.db.get_value("Pratap Quality Inspection", qc_name, "custom_density")
            if density not in (None, ""):
                row.custom_density = flt(density)

    def _validate_pratap_quality_inspection_on_items(self):
        if self.is_return:
            return

        for row in self.items:
            if flt(row.qty) <= 0:
                continue
            if row.get("custom_qc_required"):
                frappe.throw(
                    _(
                        "Row {0}: Quality Inspection is required on item {1} before submitting GRN."
                    ).format(row.idx, row.item_code or row.item_name)
                )

            # _validate_pratap_qc_for_row(qc_name, row, self.name)

    def _create_uom_in_items(self, items: list):
        for item in items:
            if item.get("custom_insert_batch_number") and not item.get("batch_no"):
                item["batch_no"] = self._generate_batch_number(item)
        return items
    
    def _generate_batch_number(self, item):
        batch = frappe.get_doc({
            "doctype": "Batch",
            "batch_id": item.get("custom_insert_batch_number") + "-" + str(frappe.utils.now()),
            "item": item.get("item_code"),
            "stock_uom": frappe.db.get_value("Item", item.get("item_code"), "stock_uom"),
        })
        batch.insert()
        return batch.name

def _validate_pratap_qc_for_row(qc_name, row, grn_name):
    if not frappe.db.exists("Pratap Quality Inspection", qc_name):
        frappe.throw(
            _("Row {0}: Pratap Quality Inspection {1} does not exist.").format(row.idx, qc_name)
        )

    qc = frappe.get_doc("Pratap Quality Inspection", qc_name)

    if qc.reference_doctype != "Purchase Receipt" or qc.reference_name != grn_name:
        frappe.throw(
            _(
                "Row {0}: Pratap Quality Inspection {1} is not linked to this Purchase Receipt."
            ).format(row.idx, qc_name)
        )

    if qc.production_item and row.item_code and qc.production_item != row.item_code:
        frappe.throw(
            _(
                "Row {0}: Pratap Quality Inspection {1} is for item {2}, not {3}."
            ).format(row.idx, qc_name, qc.production_item, row.item_code)
        )

    submitting_qc = frappe.flags.get("submitting_pratap_qc") == qc_name

    if not submitting_qc and qc.docstatus != 1:
        frappe.throw(
            _(
                "Row {0}: Pratap Quality Inspection {1} must be submitted before GRN can be submitted."
            ).format(row.idx, qc_name)
        )

    if (qc.status or "").strip() != "Accepted":
        frappe.throw(
            _(
                "Row {0}: Pratap Quality Inspection {1} must have status Accepted."
            ).format(row.idx, qc_name)
        )


def link_pratap_qc_to_grn_item(doc, method=None):
    """When Pratap QC is Accepted for a GRN, set QC link (and density) on the item row."""
    if not _is_grn_incoming_pratap_qc(doc):
        return

    if (doc.status or "").strip() != "Accepted":
        return

    if not doc.name:
        return

    rows = frappe.get_all(
        "Purchase Receipt Item",
        filters={"parent": doc.reference_name, "item_code": doc.production_item},
        fields=["name", "custom_pratap_quality_inspection"],
        order_by="idx asc",
    )

    if not rows:
        return

    target_row = None
    for row in rows:
        if not row.custom_pratap_quality_inspection or row.custom_pratap_quality_inspection == doc.name:
            target_row = row
            break

    if not target_row:
        target_row = rows[0]

    values = {"custom_pratap_quality_inspection": doc.name}
    if doc.get("custom_density") not in (None, ""):
        values["custom_density"] = flt(doc.custom_density)

    frappe.db.set_value(
        "Purchase Receipt Item",
        target_row.name,
        values,
        update_modified=False,
    )


def sync_grn_item_density_from_pratap_qc(grn_name, item_code, qc_name):
    """Push custom_density from Pratap QC to the matching GRN item row."""
    if not grn_name or not item_code or not qc_name:
        return

    density = frappe.db.get_value("Pratap Quality Inspection", qc_name, "custom_density")
    if density in (None, ""):
        return

    row_name = frappe.db.get_value(
        "Purchase Receipt Item",
        {"parent": grn_name, "item_code": item_code},
        "name",
        order_by="idx asc",
    )

    if row_name:
        frappe.db.set_value(
            "Purchase Receipt Item",
            row_name,
            "custom_density",
            flt(density),
            update_modified=False,
        )


def clear_pratap_qc_from_grn_item(doc, remove_reference=False):
    """Clear custom_pratap_quality_inspection on GRN item (like ERPNext Quality Inspection)."""
    if not _is_grn_incoming_pratap_qc(doc):
        return

    qc_link = ""
    if doc.docstatus < 2 and not remove_reference:
        qc_link = doc.name

    child = frappe.qb.DocType("Purchase Receipt Item")
    query = (
        frappe.qb.update(child)
        .set(child.custom_pratap_quality_inspection, qc_link)
        .where(
            (child.parent == doc.reference_name) & (child.item_code == doc.production_item)
        )
    )

    if doc.docstatus == 2 or remove_reference:
        query = query.where(child.custom_pratap_quality_inspection == doc.name)

    query.run()

    frappe.db.set_value(
        "Purchase Receipt",
        doc.reference_name,
        "modified",
        doc.modified,
        update_modified=False,
    )


def _is_grn_incoming_pratap_qc(doc):
    return (
        getattr(doc, "doctype", None) == "Pratap Quality Inspection"
        and (doc.inspection_type or "").strip() == "Incoming"
        and (doc.reference_type or "").strip() == "GRN"
        and doc.reference_doctype == "Purchase Receipt"
        and doc.reference_name
        and doc.production_item
    )


@frappe.whitelist()
def get_pratap_qc_status_for_grn(purchase_receipt):
    """QC button context for GRN: which items need new QC vs open existing draft."""
    if not frappe.db.exists("Purchase Receipt", purchase_receipt):
        frappe.throw(_("Purchase Receipt {0} does not exist.").format(purchase_receipt))

    doc = frappe.get_doc("Purchase Receipt", purchase_receipt)

    if doc.meta.has_field("custom_ignore_quality_inspection") and doc.get("custom_ignore_quality_inspection"):
        return {"skip": True}

    qcs = frappe.get_all(
        "Pratap Quality Inspection",
        filters={
            "reference_doctype": "Purchase Receipt",
            "reference_name": purchase_receipt,
            "reference_type": "GRN",
            "inspection_type": "Incoming",
            "docstatus": ["<", 2],
        },
        fields=["name", "production_item", "status", "docstatus"],
        order_by="creation desc",
    )

    qc_by_item = {}
    for qc in qcs:
        if qc.production_item and qc.production_item not in qc_by_item:
            qc_by_item[qc.production_item] = qc

    items_need_create = []
    open_qcs = []
    view_qcs = []
    seen_open = set()
    seen_view = set()

    for row in doc.items:
        if not row.item_code or flt(row.qty) <= 0:
            continue

        linked_name = row.get("custom_pratap_quality_inspection")
        qc = None

        if linked_name and frappe.db.exists("Pratap Quality Inspection", linked_name):
            qc = frappe.db.get_value(
                "Pratap Quality Inspection",
                linked_name,
                ["name", "production_item", "status", "docstatus"],
                as_dict=True,
            )
        elif row.item_code in qc_by_item:
            qc = qc_by_item[row.item_code]

        if not qc:
            items_need_create.append(_grn_item_row_for_qc(row))
            continue

        if qc.docstatus == 2:
            items_need_create.append(_grn_item_row_for_qc(row))
            continue

        if qc.docstatus == 0:
            if qc.name not in seen_open:
                seen_open.add(qc.name)
                open_qcs.append(
                    {
                        "name": qc.name,
                        "item_code": row.item_code,
                        "status": (qc.status or "Pending").strip(),
                    }
                )
            continue

        if qc.name not in seen_view:
            seen_view.add(qc.name)
            view_qcs.append(
                {
                    "name": qc.name,
                    "item_code": qc.production_item or row.item_code,
                    "status": (qc.status or "").strip(),
                }
            )

    return {
        "skip": False,
        "items_need_create": items_need_create,
        "open_qcs": open_qcs,
        "view_qcs": view_qcs,
        "can_create": bool(items_need_create),
    }


def _grn_item_row_for_qc(row):
    return {
        "name": row.name,
        "item_code": row.item_code,
        "item_name": row.item_name,
        "qty": row.qty,
        "uom": row.uom,
        "stock_uom": row.stock_uom,
        "work_order": row.get("work_order"),
    }
