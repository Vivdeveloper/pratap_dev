import frappe
from frappe import _
from frappe.utils import flt


def disable_inspection_required(doc, method=None):
	"""Quality Inspection is not used on Stock Entries here — force the flag off before
	validate so ERPNext's inspection check never triggers, regardless of what the BOM /
	make_stock_entry set or the checkbox shows (the field is also read-only in the UI)."""
	if doc.get("inspection_required"):
		doc.inspection_required = 0


def prevent_over_transfer_for_manufacture(doc, method=None):
	"""Hard-block a "Material Transfer for Manufacture" that would push a Work Order
	past 100% of its required quantity.

	A double-click / duplicate transfer used to move raw materials twice (transferred
	qty = 2x required, e.g. 10,000 against a 5,000 Work Order). ERPNext only prevents
	this when the "allow over-transfer" setting is off; this guard enforces it
	regardless. Runs on ``before_submit`` — at that point the Work Order's
	``material_transferred_for_manufacturing`` reflects only the already-submitted
	transfers (not this one), so we add this entry's FG qty and compare to the target.
	"""
	if doc.purpose != "Material Transfer for Manufacture" or not doc.work_order:
		return

	# Per-item batch transfers (pratap_dev.work_order_transfer) enforce per-item
	# remaining themselves and set fg_completed_qty to the whole WO qty, so the
	# fg_completed_qty comparison below doesn't apply — skip it for those.
	if doc.flags.get("pratap_partial_item_transfer"):
		return

	wo = frappe.db.get_value(
		"Work Order",
		doc.work_order,
		["qty", "material_transferred_for_manufacturing"],
		as_dict=True,
	)
	if not wo:
		return

	already_transferred = flt(wo.material_transferred_for_manufacturing)
	this_transfer = flt(doc.fg_completed_qty)
	target_qty = flt(wo.qty)

	# Tiny epsilon so floating-point noise doesn't false-trigger at exactly 100%.
	if already_transferred + this_transfer > target_qty + 1e-6:
		remaining = max(target_qty - already_transferred, 0)
		frappe.throw(
			_(
				"Work Order {0} already has {1} of {2} transferred for manufacture. "
				"This transfer of {3} would exceed the required quantity — only {4} is "
				"left to transfer. Over-transfer is not allowed."
			).format(
				doc.work_order,
				already_transferred,
				target_qty,
				this_transfer,
				remaining,
			),
			title=_("Over-Transfer Blocked"),
		)


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
