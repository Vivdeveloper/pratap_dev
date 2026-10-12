# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Packing Material Requirement for a Work Order — mirrors the Forecast Club table.

For the WO's item to manufacture, list each packing option from the Item's "Packing
Material Details": the packed good (SF), its filling capacity and packing material, the
pack qty required for the WO, the pack qty available in the WO's SOURCE warehouse, and
the resulting MR (shortfall) qty. Read-only / display only — no stock movement.
"""

import frappe
from frappe.utils import flt


def _source_warehouse(wo):
	"""The WO's source warehouse used for 'Pack Qty in Source'."""
	return (
		wo.get("custom_custom_source_warehouse")
		or wo.get("source_warehouse")
		or wo.get("wip_warehouse")
	)


def _stock_in_warehouse(item_code, warehouse):
	if not item_code or not warehouse:
		return 0.0
	return flt(
		frappe.db.get_value(
			"Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty"
		)
	)


@frappe.whitelist()
def get_wo_packing_requirement(work_order):
	"""Return the packing-material requirement rows for a Work Order."""
	wo = frappe.get_doc("Work Order", work_order)
	fg = wo.production_item
	qty = flt(wo.qty)
	source_warehouse = _source_warehouse(wo)

	details = frappe.get_all(
		"Packing Material Details",
		filters={"parent": fg, "parenttype": "Item"},
		fields=["packing_item_code", "packing_item_name", "filling_capacity", "item"],
		order_by="idx",
	)

	rows = []
	for d in details:
		fc = flt(d.filling_capacity)
		packing_material = d.packing_item_code  # the PK… packing material
		packed_good = d.item  # the sellable SF SKU
		# Pack Qty required to pack the WO's output in this pack size.
		qty_sf = flt(qty / fc, 3) if fc else 0.0
		# Pack Qty available in the WO's source warehouse (of the packing material).
		source_qty = _stock_in_warehouse(packing_material, source_warehouse)
		mr_qty = max(0.0, flt(qty_sf) - flt(source_qty))
		rows.append(
			{
				"fg": fg,
				"packed_good": packed_good,
				"packed_good_name": frappe.db.get_value("Item", packed_good, "item_name")
				or packed_good
				if packed_good
				else "",
				"filling_capacity": fc,
				"packing_material": packing_material,
				"packing_material_name": d.packing_item_name or packing_material,
				"qty_sf": qty_sf,
				"source_qty": source_qty,
				"mr_qty": mr_qty,
			}
		)

	return {
		"fg": fg,
		"qty": qty,
		"source_warehouse": source_warehouse,
		"rows": rows,
	}
