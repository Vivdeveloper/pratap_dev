# Copyright (c) 2026, pratap_dev contributors
# License: MIT
"""Allow a supplier-variant child item on a Purchase Order to satisfy its
Material Request Item link.

The RFQ flow renames a base item (e.g. RM02498) to a supplier-specific variant
(e.g. RM02498-J, linked via Item.custom_supplier_item_of). ERPNext's PO then fails
validation with "Item Code must be equal to 'RM02498'" because it compares the PO
item_code to the linked Material Request Item's item_code.

We relax ONLY that Material Request Item item_code compare, and replace it with a
same-family check (PO item must equal the MR item or be a supplier-variant of the
same base). Every other core check (project, company, Supplier Quotation item_code,
maintain_same_rate, ...) is preserved exactly.
"""

import frappe
from frappe import _
from frappe.utils import cint

from erpnext.buying.doctype.purchase_order.purchase_order import PurchaseOrder


def _base_item(item_code):
	"""Base item of a (possibly variant) item — its custom_supplier_item_of, or
	itself when it is already a base item."""
	if not item_code:
		return item_code
	parent = frappe.db.get_value("Item", item_code, "custom_supplier_item_of")
	return parent or item_code


class PratapPurchaseOrder(PurchaseOrder):
	def validate_with_previous_doc(self):
		# Identical to core PurchaseOrder.validate_with_previous_doc EXCEPT the
		# Material Request Item compare drops ["item_code", "="] — that case is
		# handled by _validate_mr_item_family() below so supplier variants pass.
		# We call the framework method directly (super of PurchaseOrder) to bypass
		# core's hardcoded item_code compare.
		super(PurchaseOrder, self).validate_with_previous_doc(
			{
				"Supplier Quotation": {
					"ref_dn_field": "supplier_quotation",
					"compare_fields": [["supplier", "="], ["company", "="], ["currency", "="]],
				},
				"Supplier Quotation Item": {
					"ref_dn_field": "supplier_quotation_item",
					"compare_fields": [
						["project", "="],
						["item_code", "="],
						["uom", "="],
						["conversion_factor", "="],
					],
					"is_child_table": True,
				},
				"Material Request": {
					"ref_dn_field": "material_request",
					"compare_fields": [["company", "="]],
				},
				"Material Request Item": {
					"ref_dn_field": "material_request_item",
					"compare_fields": [["project", "="]],
					"is_child_table": True,
				},
			}
		)

		self._validate_mr_item_family()

		if cint(frappe.db.get_single_value("Buying Settings", "maintain_same_rate")):
			self.validate_rate_with_reference_doc(
				[["Supplier Quotation", "supplier_quotation", "supplier_quotation_item"]]
			)

	def _validate_mr_item_family(self):
		"""PO item must be the same base-item family as its linked MR item —
		equal, or a supplier-variant of the same base. Keeps the safety net that
		the dropped item_code compare used to provide."""
		for row in self.get("items") or []:
			if not row.get("material_request_item"):
				continue
			mr_item_code = frappe.db.get_value(
				"Material Request Item", row.material_request_item, "item_code"
			)
			if not mr_item_code or row.item_code == mr_item_code:
				continue
			if _base_item(row.item_code) == _base_item(mr_item_code):
				continue
			frappe.throw(
				_(
					"Row #{0}: Item {1} is not the same item (or a supplier variant of it) "
					"as the linked Material Request item {2}."
				).format(row.idx, row.item_code, mr_item_code)
			)
