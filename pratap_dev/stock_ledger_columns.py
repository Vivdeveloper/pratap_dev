# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Add three columns to the standard ERPNext "Stock Ledger" query report WITHOUT editing
erpnext core: we wrap its execute() and inject the columns + per-row values.

  1. Opening Balance  — the balance BEFORE the transaction (= Balance Qty - Actual Qty),
                        placed right before "Balance Qty".
  2. Transaction UOM  — the UOM entered on the voucher's item row (e.g. KGS on the Stock
                        Entry Detail), which may differ from the Stock UOM.
  3. QC Sample Issue  — the qty moved into the dedicated QC sample warehouse
                        (SAMPLE_RND_WAREHOUSE) by the QC-submit sample flow.

The wrap is applied idempotently from the before_request hook (see hooks.py), so every
worker process patches erpnext.stock.report.stock_ledger.stock_ledger.execute exactly once.
"""

import frappe
from frappe.utils import flt

_PATCH_FLAG = "_pratap_sl_patched"

# Voucher type -> its item child doctype (default is "<Voucher Type> Item").
_CHILD_DOCTYPE_OVERRIDE = {
	"Stock Entry": "Stock Entry Detail",
}


def ensure_patched():
	"""Monkey-patch the Stock Ledger report's execute() once per process (idempotent)."""
	try:
		from erpnext.stock.report.stock_ledger import stock_ledger as sl
	except Exception:
		return

	if getattr(sl.execute, _PATCH_FLAG, False):
		return

	original_execute = sl.execute

	def patched_execute(filters=None):
		result = original_execute(filters)
		if not result:
			return result
		columns = result[0] if len(result) > 0 else []
		data = result[1] if len(result) > 1 else []
		try:
			_add_columns(columns)
			_add_row_values(data)
		except Exception:
			# Never break the core report if our augmentation fails.
			frappe.log_error(title="Stock Ledger extra columns failed", message=frappe.get_traceback())
		return (columns, data) + tuple(result[2:])

	setattr(patched_execute, _PATCH_FLAG, True)
	sl.execute = patched_execute


def _add_columns(columns):
	"""Insert Opening Balance (before Balance Qty), then Transaction UOM + QC Sample Issue."""
	if any(c.get("fieldname") == "custom_opening_balance" for c in columns):
		return  # already injected

	opening_col = {
		"label": "Opening Balance",
		"fieldname": "custom_opening_balance",
		"fieldtype": "Float",
		"width": 110,
		"convertible": "qty",
	}
	txn_uom_col = {
		"label": "Transaction UOM",
		"fieldname": "custom_transaction_uom",
		"fieldtype": "Link",
		"options": "UOM",
		"width": 110,
	}
	qc_sample_col = {
		"label": "QC Sample Issue",
		"fieldname": "custom_qc_sample_issue",
		"fieldtype": "Float",
		"width": 120,
		"convertible": "qty",
	}

	idx = next(
		(i for i, c in enumerate(columns) if c.get("fieldname") == "qty_after_transaction"),
		None,
	)
	if idx is None:
		# Fallback: append all three if the balance column isn't found.
		columns.extend([opening_col, txn_uom_col, qc_sample_col])
		return

	columns.insert(idx, opening_col)  # Opening Balance right before Balance Qty
	# Balance Qty is now at idx+1; put the other two right after it.
	columns.insert(idx + 2, txn_uom_col)
	columns.insert(idx + 3, qc_sample_col)


def _add_row_values(data):
	uom_map = _build_transaction_uom_map(data)
	qc_sample_vouchers = _qc_sample_stock_entries(data)

	try:
		from pratap_dev.purchase_receipt_batch_qc import SAMPLE_RND_WAREHOUSE
	except Exception:
		SAMPLE_RND_WAREHOUSE = None

	for row in data:
		if not isinstance(row, dict):
			continue

		# 1) Opening Balance = Balance Qty - Actual Qty (balance before this transaction).
		balance = flt(row.get("qty_after_transaction"))
		if "actual_qty" in row:
			actual = flt(row.get("actual_qty"))
		else:
			actual = flt(row.get("in_qty")) + flt(row.get("out_qty"))
		row["custom_opening_balance"] = balance - actual

		# 2) Transaction UOM — voucher item-row UOM, falling back to Stock UOM.
		key = (row.get("voucher_type"), row.get("voucher_no"), row.get("item_code"))
		row["custom_transaction_uom"] = uom_map.get(key) or row.get("stock_uom")

		# 3) QC Sample Issue — qty moved into the dedicated QC sample warehouse.
		in_qty = flt(row.get("in_qty"))
		is_sample = (
			SAMPLE_RND_WAREHOUSE
			and row.get("warehouse") == SAMPLE_RND_WAREHOUSE
			and in_qty > 0
			and row.get("voucher_no") in qc_sample_vouchers
		)
		row["custom_qc_sample_issue"] = in_qty if is_sample else 0


def _build_transaction_uom_map(data):
	"""Map (voucher_type, voucher_no, item_code) -> UOM from each voucher's item child table."""
	vnos_by_type = {}
	for row in data:
		if not isinstance(row, dict):
			continue
		vt = row.get("voucher_type")
		vno = row.get("voucher_no")
		if vt and vno:
			vnos_by_type.setdefault(vt, set()).add(vno)

	uom_map = {}
	for vt, vnos in vnos_by_type.items():
		child_dt = _CHILD_DOCTYPE_OVERRIDE.get(vt, "{0} Item".format(vt))
		if not frappe.db.exists("DocType", child_dt):
			continue
		meta = frappe.get_meta(child_dt)
		if not meta.has_field("uom") or not meta.has_field("item_code"):
			continue
		child_rows = frappe.get_all(
			child_dt,
			filters={"parent": ["in", list(vnos)]},
			fields=["parent", "item_code", "uom"],
		)
		for cr in child_rows:
			uom_map.setdefault((vt, cr.parent, cr.item_code), cr.uom)
	return uom_map


def _qc_sample_stock_entries(data):
	"""Set of Stock Entry names in the data that are QC-sample receipts (created by the QC
	submit flow — tagged via their remarks)."""
	se_nos = {
		row.get("voucher_no")
		for row in data
		if isinstance(row, dict) and row.get("voucher_type") == "Stock Entry" and row.get("voucher_no")
	}
	if not se_nos:
		return set()
	return set(
		frappe.get_all(
			"Stock Entry",
			filters={"name": ["in", list(se_nos)], "remarks": ["like", "QC Sample moved%"]},
			pluck="name",
		)
	)
