import frappe
from frappe import _


def validate_manufacture_batch_with_work_order(doc, method=None):
    if not _is_pratap_batch_series_enabled():
        return

    if doc.stock_entry_type != "Manufacture" or not doc.work_order:
        return

    expected_batch_id = doc.work_order
    finished_rows = [row for row in doc.items if row.is_finished_item]

    if not finished_rows:
        return

    for row in finished_rows:
        _validate_bundle_batches(row, expected_batch_id)
        _set_or_validate_batch_for_row(doc, row, expected_batch_id)


def _set_or_validate_batch_for_row(stock_entry, row, expected_batch_id):
    if not row.batch_no:
        row.batch_no = _get_or_create_batch(expected_batch_id, row.item_code, stock_entry)
        return

    if row.batch_no != expected_batch_id:
        frappe.throw(
            _(
                "Row {0}: Batch ID must match Work Order {1}. Found Batch ID {2}."
            ).format(row.idx, expected_batch_id, row.batch_no)
        )


def _get_or_create_batch(batch_id, item_code, stock_entry):
    existing_item = frappe.db.get_value("Batch", batch_id, "item")

    if existing_item:
        if existing_item != item_code:
            frappe.throw(
                _(
                    "Batch {0} already exists for Item {1}. It cannot be used for Item {2}."
                ).format(batch_id, existing_item, item_code)
            )
        _update_missing_batch_reference(batch_id, stock_entry)
        return batch_id

    batch = frappe.new_doc("Batch")
    batch.batch_id = batch_id
    batch.item = item_code
    batch.reference_doctype = "Stock Entry"
    batch.reference_name = stock_entry.name
    batch.manufacturing_date = stock_entry.posting_date
    batch.insert(ignore_permissions=True)
    return batch.name


def _update_missing_batch_reference(batch_id, stock_entry):
    reference_doctype, reference_name = frappe.db.get_value(
        "Batch", batch_id, ["reference_doctype", "reference_name"]
    )
    if reference_doctype or reference_name:
        return

    frappe.db.set_value(
        "Batch",
        batch_id,
        {
            "reference_doctype": "Stock Entry",
            "reference_name": stock_entry.name,
        },
        update_modified=False,
    )


def _is_pratap_batch_series_enabled():
    return frappe.db.get_single_value("Pratap Settings", "enable_pratap_batch_series")


def _validate_bundle_batches(row, expected_batch_id):
    if not row.serial_and_batch_bundle:
        return

    bundle_batch_rows = frappe.get_all(
        "Serial and Batch Entry",
        filters={"parent": row.serial_and_batch_bundle},
        fields=["batch_no"],
    )
    bundle_batch_ids = {d.batch_no for d in bundle_batch_rows if d.batch_no}

    for batch_id in bundle_batch_ids:
        if batch_id != expected_batch_id:
            frappe.throw(
                _(
                    "Row {0}: Batch ID in bundle must match Work Order {1}. Found Batch ID {2}."
                ).format(row.idx, expected_batch_id, batch_id)
            )
