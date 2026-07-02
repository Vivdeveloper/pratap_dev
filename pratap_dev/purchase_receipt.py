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
        if self.is_return:
            return

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

    def on_submit(self):
        super().on_submit()
        if self.is_return:
            # Return PRs (purchase returns / debit-note source) must not spawn a grouped PI.
            return
        create_grouped_purchase_invoice_if_ready(self)
        create_rejection_documents_if_any(self)

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
                ["reference_doctype", "reference_name", "production_item", "purchase_receipt_item", "docstatus"],
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

            if qc.get("purchase_receipt_item") and qc.purchase_receipt_item != row.name:
                frappe.throw(
                    _(
                        "Row {0}: Pratap Quality Inspection {1} is linked to a different GRN item row."
                    ).format(row.idx, qc_name)
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

        errors = _get_grn_qc_submit_errors(self)
        if errors:
            frappe.throw(
                "<br>".join(errors),
                title=_("Pratap Quality Inspection Required"),
            )

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

def create_grouped_purchase_invoice_if_ready(grn):
    """Create one combined Purchase Invoice once every GRN in the group is submitted.

    GRNs created together from a Purchase Order share `custom_grn_group_id`. When the
    last GRN of a group is submitted, all items across the group's GRNs are accumulated
    into a single draft Purchase Invoice (idempotent: only one PI per group).
    """
    group_id = grn.get("custom_grn_group_id")
    if not group_id:
        return

    if not grn.meta.has_field("custom_grn_group_id"):
        return

    # Idempotency: a (non-return) PI for this group must not already exist.
    # (is_return=0 so the clubbed debit note for rejected qty is not mistaken for it.)
    if frappe.db.exists(
        "Purchase Invoice", {"custom_grn_group_id": group_id, "is_return": 0, "docstatus": ["<", 2]}
    ):
        return

    # Only real receiving GRNs (is_return=0); return PRs also carry the group id.
    group_grns = frappe.get_all(
        "Purchase Receipt",
        filters={"custom_grn_group_id": group_id, "is_return": 0, "docstatus": ["<", 2]},
        fields=["name", "docstatus"],
        order_by="creation asc",
    )

    grn_names = []
    for row in group_grns:
        # `grn` is being submitted in this transaction; treat it as submitted.
        effective_docstatus = 1 if row.name == grn.name else row.docstatus
        if effective_docstatus != 1:
            # At least one GRN in the group is still a draft — wait for it.
            return
        grn_names.append(row.name)

    if not grn_names:
        return

    from erpnext.stock.doctype.purchase_receipt.purchase_receipt import make_purchase_invoice

    target = None
    for name in grn_names:
        target = make_purchase_invoice(name, target_doc=target)

    if not target or not target.get("items"):
        return

    if target.meta.has_field("custom_grn_group_id"):
        target.custom_grn_group_id = group_id

    bill_no = grn.get("custom_supplier_invoice_no")
    bill_date = grn.get("custom_supplier_invoice_date")
    if bill_no and target.meta.has_field("bill_no"):
        target.bill_no = bill_no
    if bill_date and target.meta.has_field("bill_date"):
        target.bill_date = bill_date

    target.flags.ignore_permissions = True
    target.save()

    frappe.msgprint(
        _("Purchase Invoice {0} created from {1} grouped GRN(s).").format(
            frappe.utils.get_link_to_form("Purchase Invoice", target.name), len(grn_names)
        ),
        indicator="green",
        alert=True,
    )


def create_rejection_documents_if_any(grn):
    """On GRN submit, handle rejected quantity.

    Behaviour depends on whether the GRN belongs to a Purchase Order group
    (`custom_grn_group_id`, shared by GRNs made together from one PO):

    * Grouped: wait until every GRN in the group is submitted, then create the
      per-GRN Purchase Returns and ONE clubbed draft Debit Note across the whole
      group (mirrors the accepted-side grouped Purchase Invoice).
    * Not grouped: create a Purchase Return + its own draft Debit Note for this GRN.

    Idempotent: re-running will not create duplicates.
    """
    if grn.get("is_return"):
        return

    group_id = grn.get("custom_grn_group_id")
    if group_id and grn.meta.has_field("custom_grn_group_id"):
        _create_grouped_rejection_documents_if_ready(grn, group_id)
        return

    _create_rejection_documents_for_grn(grn)


def _create_rejection_documents_for_grn(grn):
    """Single-GRN rejection flow: submitted Purchase Return + its own draft Debit Note."""
    total_rejected = sum(flt(row.get("rejected_qty")) for row in (grn.get("items") or []))
    if total_rejected <= 0:
        return

    return_pr = _create_submitted_purchase_return(grn)
    if not return_pr:
        return

    _create_draft_debit_note(grn, return_pr)


def _create_grouped_rejection_documents_if_ready(grn, group_id):
    """When every GRN of a PO group is submitted, create the per-GRN Purchase Returns
    and ONE clubbed draft Debit Note (Purchase Invoice return) across the group.
    """
    # Only real receiving GRNs (is_return=0); return PRs also carry the group id.
    group_grns = frappe.get_all(
        "Purchase Receipt",
        filters={"custom_grn_group_id": group_id, "is_return": 0, "docstatus": ["<", 2]},
        fields=["name", "docstatus"],
        order_by="creation asc",
    )

    for row in group_grns:
        # `grn` is being submitted in this transaction; treat it as submitted.
        effective_docstatus = 1 if row.name == grn.name else row.docstatus
        if effective_docstatus != 1:
            # A GRN in the group is still a draft — wait for the whole group.
            return

    # Ensure a submitted Purchase Return exists for every rejected GRN in the group.
    return_prs = []
    for row in group_grns:
        grn_doc = grn if row.name == grn.name else frappe.get_doc("Purchase Receipt", row.name)
        total_rejected = sum(flt(i.get("rejected_qty")) for i in (grn_doc.get("items") or []))
        if total_rejected <= 0:
            continue
        return_pr = _create_submitted_purchase_return(grn_doc)
        if return_pr:
            return_prs.append(return_pr)

    if not return_prs:
        return

    # Idempotency: only one clubbed debit note (is_return PI) per group.
    if frappe.db.exists(
        "Purchase Invoice",
        {"custom_grn_group_id": group_id, "is_return": 1, "docstatus": ["<", 2]},
    ):
        return

    _create_grouped_draft_debit_note(grn, group_id, return_prs)


def _create_grouped_draft_debit_note(grn, group_id, return_prs):
    """Create ONE draft Debit Note accumulating items from all the group's Purchase Returns."""
    from erpnext.stock.doctype.purchase_receipt.purchase_receipt import make_purchase_invoice

    try:
        target = None
        for return_pr in return_prs:
            target = make_purchase_invoice(return_pr.name, target_doc=target)

        if not target or not target.get("items"):
            return

        # Debit note spans multiple return PRs; header return_against stays empty
        # (each item links back via its own purchase_receipt).
        target.is_return = 1
        if target.meta.has_field("custom_grn_group_id"):
            target.custom_grn_group_id = group_id

        _copy_grn_reference_fields(grn, target)
        target.flags.ignore_permissions = True
        target.save()  # leave in Draft

        frappe.msgprint(
            _("Debit Note {0} created in Draft (clubbed from {1} rejected GRN(s)).").format(
                frappe.utils.get_link_to_form("Purchase Invoice", target.name), len(return_prs)
            ),
            indicator="orange",
            alert=True,
        )
    except Exception:
        frappe.log_error(
            title="Pratap: Clubbed Debit Note creation failed",
            message=frappe.get_traceback(),
        )
        frappe.msgprint(
            _(
                "Purchase Returns were submitted, but the clubbed draft Debit Note could not be "
                "created automatically. Please create it manually."
            ),
            indicator="red",
            alert=True,
        )


def _create_submitted_purchase_return(grn):
    """Create and submit a Purchase Return for the GRN's rejected-warehouse qty."""
    existing = frappe.db.get_value(
        "Purchase Receipt",
        {"return_against": grn.name, "is_return": 1, "docstatus": ["<", 2]},
        "name",
    )
    if existing:
        return frappe.get_doc("Purchase Receipt", existing)

    from erpnext.stock.doctype.purchase_receipt.purchase_receipt import (
        make_purchase_return_against_rejected_warehouse,
    )

    return_doc = make_purchase_return_against_rejected_warehouse(grn.name)
    return_doc.set("items", [row for row in return_doc.items if flt(row.qty) != 0])
    if not return_doc.items:
        return None

    _copy_grn_reference_fields(grn, return_doc)
    return_doc.flags.ignore_permissions = True
    return_doc.save()
    return_doc.submit()

    frappe.msgprint(
        _("Purchase Return {0} created and submitted for rejected quantity.").format(
            frappe.utils.get_link_to_form("Purchase Receipt", return_doc.name)
        ),
        indicator="orange",
        alert=True,
    )
    return return_doc


def _create_draft_debit_note(grn, return_pr):
    """Create a draft Debit Note (Purchase Invoice Return) from the submitted return."""
    # A debit note made from a return PR links back via its item's `purchase_receipt`
    # (its header `return_against` stays empty), so detect duplicates through the item.
    existing = frappe.db.get_value(
        "Purchase Invoice Item",
        {"purchase_receipt": return_pr.name, "docstatus": ["<", 2]},
        "parent",
    )
    if existing:
        return

    from erpnext.stock.doctype.purchase_receipt.purchase_receipt import make_purchase_invoice

    try:
        debit_note = make_purchase_invoice(return_pr.name)
        if not debit_note.get("is_return"):
            debit_note.is_return = 1
            debit_note.return_against = return_pr.name

        _copy_grn_reference_fields(grn, debit_note)
        debit_note.flags.ignore_permissions = True
        debit_note.save()  # leave in Draft

        frappe.msgprint(
            _("Debit Note {0} created in Draft for rejected quantity.").format(
                frappe.utils.get_link_to_form("Purchase Invoice", debit_note.name)
            ),
            indicator="orange",
            alert=True,
        )
    except Exception:
        frappe.log_error(
            title="Pratap: Debit Note creation failed",
            message=frappe.get_traceback(),
        )
        frappe.msgprint(
            _(
                "Purchase Return {0} was submitted, but the draft Debit Note could not be "
                "created automatically. Please create it manually."
            ).format(frappe.utils.get_link_to_form("Purchase Receipt", return_pr.name)),
            indicator="red",
            alert=True,
        )


def _copy_grn_reference_fields(grn, target):
    """Copy GRN group id and supplier invoice no/date onto a return/debit-note document."""
    group_id = grn.get("custom_grn_group_id")
    if group_id and target.meta.has_field("custom_grn_group_id"):
        target.custom_grn_group_id = group_id

    bill_no = grn.get("custom_supplier_invoice_no")
    bill_date = grn.get("custom_supplier_invoice_date")

    if bill_no and target.meta.has_field("bill_no"):
        target.bill_no = bill_no
    if bill_date and target.meta.has_field("bill_date"):
        target.bill_date = bill_date

    # Mirror onto the document's own supplier-invoice fields when they exist (e.g. return PR).
    if bill_no and target.meta.has_field("custom_supplier_invoice_no"):
        target.custom_supplier_invoice_no = bill_no
    if bill_date and target.meta.has_field("custom_supplier_invoice_date"):
        target.custom_supplier_invoice_date = bill_date


def _get_grn_qc_submit_errors(grn_doc):
    """Collect QC validation messages for every QC-required GRN line."""
    errors = []

    for row in grn_doc.get("items") or []:
        if not _grn_item_needs_qc(row):
            continue

        qc_name = row.get("custom_pratap_quality_inspection")
        item_label = row.item_code or row.item_name or row.idx

        if not qc_name:
            errors.append(
                _(
                    "Row {0} ({1}): Create and submit Pratap Quality Inspection before submitting GRN."
                ).format(row.idx, item_label)
            )
            continue

        error = _get_pratap_qc_row_error(qc_name, row, grn_doc.name)
        if error:
            errors.append(error)

    return errors


def _get_pratap_qc_row_error(qc_name, row, grn_name):
    if not frappe.db.exists("Pratap Quality Inspection", qc_name):
        return _("Row {0}: Pratap Quality Inspection {1} does not exist.").format(row.idx, qc_name)

    qc = frappe.get_doc("Pratap Quality Inspection", qc_name)

    if qc.reference_doctype != "Purchase Receipt" or qc.reference_name != grn_name:
        return _(
            "Row {0}: Pratap Quality Inspection {1} is not linked to this Purchase Receipt."
        ).format(row.idx, qc_name)

    if qc.production_item and row.item_code and qc.production_item != row.item_code:
        return _(
            "Row {0}: Pratap Quality Inspection {1} is for item {2}, not {3}."
        ).format(row.idx, qc_name, qc.production_item, row.item_code)

    if qc.get("purchase_receipt_item") and qc.purchase_receipt_item != row.name:
        return _(
            "Row {0}: Pratap Quality Inspection {1} is linked to a different GRN item row."
        ).format(row.idx, qc_name)

    submitting_qc = frappe.flags.get("submitting_pratap_qc") == qc_name

    if not submitting_qc and qc.docstatus != 1:
        return _(
            "Row {0} ({1}): Submit Pratap Quality Inspection {2} before submitting GRN."
        ).format(row.idx, row.item_code or row.item_name, qc_name)

    if (qc.status or "").strip() != "Accepted":
        return _(
            "Row {0} ({1}): Pratap Quality Inspection {2} must have status Accepted."
        ).format(row.idx, row.item_code or row.item_name, qc_name)

    return None


def _validate_pratap_qc_for_row(qc_name, row, grn_name):
    error = _get_pratap_qc_row_error(qc_name, row, grn_name)
    if error:
        frappe.throw(error)


def link_pratap_qc_to_grn_item(doc, method=None):
    """When Pratap QC is Accepted for a GRN, set QC link (and density) on the item row."""
    if not _is_grn_incoming_pratap_qc(doc):
        return

    if (doc.status or "").strip() != "Accepted":
        return

    if not doc.name:
        return

    target_row_name = _resolve_grn_item_row_name(doc)
    if not target_row_name:
        return

    values = {"custom_pratap_quality_inspection": doc.name}
    if doc.get("custom_density") not in (None, ""):
        values["custom_density"] = flt(doc.custom_density)

    frappe.db.set_value(
        "Purchase Receipt Item",
        target_row_name,
        values,
        update_modified=False,
    )


def sync_grn_item_density_from_pratap_qc(grn_name, item_code, qc_name, purchase_receipt_item=None):
    """Push custom_density from Pratap QC to the matching GRN item row."""
    if not grn_name or not qc_name:
        return

    density = frappe.db.get_value("Pratap Quality Inspection", qc_name, "custom_density")
    if density in (None, ""):
        return

    row_name = purchase_receipt_item
    if not row_name and item_code:
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
    query = frappe.qb.update(child).set(child.custom_pratap_quality_inspection, qc_link)

    if doc.get("purchase_receipt_item"):
        query = query.where(child.name == doc.purchase_receipt_item)
    else:
        query = query.where(
            (child.parent == doc.reference_name) & (child.item_code == doc.production_item)
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


def grn_ready_for_submit_after_qc(purchase_receipt):
    """Return True when every QC-required GRN line has a submitted Accepted Pratap QC."""
    if not purchase_receipt or not frappe.db.exists("Purchase Receipt", purchase_receipt):
        return False

    grn = frappe.get_doc("Purchase Receipt", purchase_receipt)
    if grn.docstatus != 0:
        return False

    needs_qc = False
    for row in grn.items:
        if not _grn_item_needs_qc(row):
            continue

        needs_qc = True
        qc_name = row.get("custom_pratap_quality_inspection")
        if not qc_name:
            return False

        qc = frappe.db.get_value(
            "Pratap Quality Inspection",
            qc_name,
            ["docstatus", "status"],
            as_dict=True,
        )
        if not qc or qc.docstatus != 1 or (qc.status or "").strip() != "Accepted":
            return False

    return needs_qc


def _grn_item_needs_qc(row):
    received_qty = flt(row.get("received_qty")) or flt(row.get("qty"))
    if received_qty <= 0 or not row.get("item_code"):
        return False

    if frappe.get_meta("Purchase Receipt Item").has_field("custom_qc_required"):
        return bool(row.get("custom_qc_required"))

    return True


def _resolve_grn_item_row_name(doc):
    if doc.get("purchase_receipt_item"):
        if frappe.db.exists(
            "Purchase Receipt Item",
            {"name": doc.purchase_receipt_item, "parent": doc.reference_name},
        ):
            return doc.purchase_receipt_item

    rows = frappe.get_all(
        "Purchase Receipt Item",
        filters={"parent": doc.reference_name, "item_code": doc.production_item},
        fields=["name", "custom_pratap_quality_inspection"],
        order_by="idx asc",
    )

    if not rows:
        return None

    for row in rows:
        if not row.custom_pratap_quality_inspection or row.custom_pratap_quality_inspection == doc.name:
            return row.name

    return rows[0].name


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
def get_grn_qc_submit_status(purchase_receipt):
    """Client-side GRN submit gate: all QC-required lines must have submitted Accepted QC."""
    if not frappe.db.exists("Purchase Receipt", purchase_receipt):
        frappe.throw(_("Purchase Receipt {0} does not exist.").format(purchase_receipt))

    grn = frappe.get_doc("Purchase Receipt", purchase_receipt)

    if grn.docstatus != 0:
        return {"can_submit": True, "pending_items": [], "message": ""}

    if grn.meta.has_field("custom_ignore_quality_inspection") and grn.get(
        "custom_ignore_quality_inspection"
    ):
        return {"can_submit": True, "pending_items": [], "message": ""}

    errors = _get_grn_qc_submit_errors(grn)
    if not errors:
        return {"can_submit": True, "pending_items": [], "message": ""}

    pending_items = []
    for row in grn.items:
        if not _grn_item_needs_qc(row):
            continue

        qc_name = row.get("custom_pratap_quality_inspection")
        error = None
        if not qc_name:
            error = True
        else:
            error = bool(_get_pratap_qc_row_error(qc_name, row, grn.name))

        if not error:
            continue

        qc_docstatus = None
        qc_status = None
        if qc_name and frappe.db.exists("Pratap Quality Inspection", qc_name):
            qc_values = frappe.db.get_value(
                "Pratap Quality Inspection",
                qc_name,
                ["docstatus", "status"],
                as_dict=True,
            )
            qc_docstatus = qc_values.docstatus
            qc_status = (qc_values.status or "").strip()

        pending_items.append(
            {
                "idx": row.idx,
                "item_code": row.item_code,
                "item_name": row.item_name,
                "row_name": row.name,
                "qc_name": qc_name,
                "qc_docstatus": qc_docstatus,
                "qc_status": qc_status,
            }
        )

    return {
        "can_submit": False,
        "pending_items": pending_items,
        "message": "<br>".join(errors),
    }


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
        fields=["name", "production_item", "purchase_receipt_item", "status", "docstatus"],
        order_by="creation desc",
    )

    qc_by_row = {}
    qc_by_item = {}
    for qc in qcs:
        if qc.get("purchase_receipt_item") and qc.purchase_receipt_item not in qc_by_row:
            qc_by_row[qc.purchase_receipt_item] = qc
        if qc.production_item and qc.production_item not in qc_by_item:
            qc_by_item[qc.production_item] = qc

    items_need_create = []
    open_qcs = []
    view_qcs = []
    seen_open = set()
    seen_view = set()

    for row in doc.items:
        if not _grn_item_needs_qc(row):
            continue

        linked_name = row.get("custom_pratap_quality_inspection")
        qc = None

        if linked_name and frappe.db.exists("Pratap Quality Inspection", linked_name):
            qc = frappe.db.get_value(
                "Pratap Quality Inspection",
                linked_name,
                ["name", "production_item", "purchase_receipt_item", "status", "docstatus"],
                as_dict=True,
            )
        elif row.name in qc_by_row:
            qc = qc_by_row[row.name]
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
        "received_qty": row.get("received_qty"),
        "uom": row.uom,
        "stock_uom": row.stock_uom,
        "work_order": row.get("work_order"),
    }
