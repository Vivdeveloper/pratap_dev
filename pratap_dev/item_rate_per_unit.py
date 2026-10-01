# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Resolve an item's "Rate Per Unit" (Item Price custom_rate_per_unit) the same way ERPNext
resolves the Rate: within the transaction's selling price list, a CUSTOMER-specific Item Price
wins over the generic (no-customer) one. Used by the Sales Invoice item grid to fill the
Rate Per Unit column from whichever Item Price the Rate came from."""

import frappe
from frappe.utils import flt


@frappe.whitelist()
def get_rate_per_unit(item_code, price_list, customer=None):
	if not item_code or not price_list:
		return 0.0

	rows = frappe.get_all(
		"Item Price",
		filters={"item_code": item_code, "price_list": price_list, "selling": 1},
		fields=["customer", "custom_rate_per_unit"],
		order_by="valid_from desc, modified desc",
	)
	if not rows:
		return 0.0

	# Customer-specific price wins (matches how the Rate itself is picked for this customer).
	if customer:
		for r in rows:
			if r.customer == customer:
				return flt(r.custom_rate_per_unit)
	# Then the generic (no-customer) price in this price list.
	for r in rows:
		if not r.customer:
			return flt(r.custom_rate_per_unit)
	# Fallback: the most recent price in this list.
	return flt(rows[0].custom_rate_per_unit)
