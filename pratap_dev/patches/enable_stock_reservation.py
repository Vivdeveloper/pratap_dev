# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Configure Stock Settings for the Sales Order auto-reservation flow
(pratap_dev.sales_order_reservation).

- enable_stock_reservation: without this ERPNext refuses to create any Stock
  Reservation Entry and clears the `reserve_stock` flag on items.
- auto_reserve_serial_and_batch = 0: reserve batch/serial items by Qty (holding the
  quantity, with the actual batch resolved at delivery) instead of forcing a specific
  batch pick on submit. With it enabled, reservation fails for any batch item whose
  stock has no batch-wise availability.

Idempotent."""

import frappe


def execute():
	frappe.db.set_single_value("Stock Settings", "enable_stock_reservation", 1)
	frappe.db.set_single_value("Stock Settings", "auto_reserve_serial_and_batch", 0)
