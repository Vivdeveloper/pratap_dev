# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Auto-create Stock Reservation Entries for a Sales Order on submission.

On submit, every stock Item on the Sales Order is reserved (FIFO, qty-based) from a
single fixed warehouse (``RESERVE_WAREHOUSE``) -- this replicates what the standard
"Reserve Stock" dialog does, but runs automatically behind the scenes. The outcome is
reflected in the read-only ``custom_stock_reservation_status`` field on the Sales Order.

Reservation is best-effort: if the warehouse has insufficient stock, whatever is
available is reserved (partial) and submission is never blocked.
"""

import frappe
from frappe.utils import cint, flt

# Stock is always reserved from this warehouse, regardless of the item source warehouse.
RESERVE_WAREHOUSE = "Pune Warehouse - PTPL"


def _is_stock_item(item_code):
	return cint(frappe.get_cached_value("Item", item_code, "is_stock_item"))


def before_submit(doc, method=None):
	"""Disable ERPNext's native on-submit auto-reservation.

	The standard flow (SO ``reserve_stock`` checkbox) reserves from each item's own
	warehouse. We want the reservation to come only from ``RESERVE_WAREHOUSE``, so we
	clear the flag here -- our ``on_submit`` handler is then the only one that reserves.
	"""
	doc.reserve_stock = 0


def reserve_stock_on_submit(doc, method=None):
	"""Reserve stock for all stock items from ``RESERVE_WAREHOUSE`` and set the status."""

	if not frappe.db.get_single_value("Stock Settings", "enable_stock_reservation"):
		return

	if not frappe.db.exists("Warehouse", RESERVE_WAREHOUSE):
		frappe.log_error(
			f"Stock reservation skipped for {doc.name}: warehouse '{RESERVE_WAREHOUSE}' not found.",
			"Sales Order Auto Stock Reservation",
		)
		return

	items_details = []
	for item in doc.items:
		if not _is_stock_item(item.item_code):
			continue
		if flt(item.qty) <= 0:
			continue

		# create_stock_reservation_entries_for_so_items reloads each Sales Order Item from
		# the DB and skips it unless its `reserve_stock` flag is set, so make sure it is.
		if not cint(item.reserve_stock):
			frappe.db.set_value(
				"Sales Order Item", item.name, "reserve_stock", 1, update_modified=False
			)
			item.reserve_stock = 1

		items_details.append(
			{
				"sales_order_item": item.name,
				"item_code": item.item_code,
				"warehouse": RESERVE_WAREHOUSE,
				# qty in the item UOM; the reservation fn multiplies by conversion_factor.
				"qty_to_reserve": flt(item.qty),
				"conversion_factor": flt(item.conversion_factor) or 1,
			}
		)

	if items_details:
		try:
			# notify=False -> no popups; partial reservation is allowed via Stock Settings.
			doc.create_stock_reservation_entries(items_details=items_details, notify=False)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(), f"Sales Order Auto Stock Reservation ({doc.name})"
			)

	_update_reservation_status(doc)


def _update_reservation_status(doc):
	"""Set custom_stock_reservation_status from the actual reserved qty vs ordered qty."""

	from erpnext.stock.doctype.stock_reservation_entry.stock_reservation_entry import (
		get_sre_reserved_qty_details_for_voucher,
	)

	# {sales_order_item_name: reserved_qty (stock uom)}
	reserved = get_sre_reserved_qty_details_for_voucher("Sales Order", doc.name)

	total_ordered = 0.0
	total_reserved = 0.0
	for item in doc.items:
		if not _is_stock_item(item.item_code):
			continue
		total_ordered += flt(item.stock_qty)
		total_reserved += flt(reserved.get(item.name))

	if total_reserved <= 0:
		status = "Not Reserved"
	elif total_reserved + 1e-6 >= total_ordered:
		status = "Reserved"
	else:
		status = "Partially Reserved"

	doc.db_set("custom_stock_reservation_status", status, update_modified=False)


def reset_reservation_status_on_cancel(doc, method=None):
	"""Native on_cancel already cancels the SREs; reflect that in the status field."""
	doc.db_set("custom_stock_reservation_status", "Not Reserved", update_modified=False)
