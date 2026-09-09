"""Alternate-item Repack for Work Orders (Pratap).

From a Work Order, the user selects one or more required items, picks batches of
their ALTERNATE items (with quantities), and clicks Insert. This consumes the
picked alternate batches and produces the total into a batch of the MAIN item,
via an auto-submitted **Repack** Stock Entry linked to the Work Order.

Batch nomenclature (default convention; confirm with business):
    <main_item>-<sorted alternate tags>
where an alternate's "tag" is its code with the "<main_item>-" prefix stripped
(so RM0035 + RM0035-A -> "RM0035-A"), else the full alternate code.
The name is deterministic, so repeating the same combination produces into the
SAME batch and the quantities sum in the stock ledger.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt


@frappe.whitelist()
def get_item_alternatives(item_code):
	"""Return alternate item codes configured for item_code (two-way aware)."""
	alts = set()
	for r in frappe.get_all(
		"Item Alternative", filters={"item_code": item_code}, fields=["alternative_item_code"]
	):
		alts.add(r.alternative_item_code)
	for r in frappe.get_all(
		"Item Alternative",
		filters={"alternative_item_code": item_code, "two_way": 1},
		fields=["item_code"],
	):
		alts.add(r.item_code)
	return sorted(alts)


def get_batch_availability(item_code, warehouse, batch_no):
	"""Available qty of a batch in a warehouse (internal helper)."""
	from erpnext.stock.doctype.batch.batch import get_batch_qty

	return flt(get_batch_qty(batch_no=batch_no, warehouse=warehouse, item_code=item_code))


@frappe.whitelist()
def get_alternate_batch_options(main_items, warehouse):
	"""For each selected main item, return every alternate-item batch that has
	stock in ``warehouse``, with its available qty — pre-computed server-side so
	the modal can show it directly (no fragile client-side lookups).

	Returns list of dicts: {main_item, alternate_item, warehouse, batch_no, available_qty}
	"""
	from erpnext.stock.doctype.batch.batch import get_batch_qty

	if isinstance(main_items, str):
		main_items = json.loads(main_items)

	name_cache = {}

	def item_name(code):
		if code not in name_cache:
			name_cache[code] = frappe.db.get_value("Item", code, "item_name") or ""
		return name_cache[code]

	rows = []
	for main_item in main_items:
		for alt in get_item_alternatives(main_item):
			# batches of this alternate that currently have stock in the warehouse
			batches = get_batch_qty(warehouse=warehouse, item_code=alt) or []
			for b in batches:
				qty = flt(b.get("qty"))
				if qty > 0 and b.get("batch_no"):
					rows.append(
						{
							"main_item": main_item,
							"main_item_name": item_name(main_item),
							"alternate_item": alt,
							"alternate_item_name": item_name(alt),
							"warehouse": warehouse,
							"batch_no": b.get("batch_no"),
							"available_qty": qty,
						}
					)
	return rows


def _batch_tag(main_item, alt_code):
	prefix = f"{main_item}-"
	return alt_code[len(prefix):] if alt_code.startswith(prefix) else alt_code


def target_batch_name(main_item, alt_codes):
	"""Deterministic batch id for a group. The group identity is
	(main_item, set of alternates) — so the SAME alternates always map to the SAME
	batch, and repeat inserts accumulate qty there. A different alternate set yields
	a different batch.
	"""
	tags = sorted({_batch_tag(main_item, a) for a in alt_codes})
	return f"{main_item}-" + "-".join(tags)


@frappe.whitelist()
def create_alternate_repack(work_order, picks):
	"""Create + submit a Repack Stock Entry from the picked alternate batches.

	picks: JSON list of dicts with keys:
	    main_item, alternate_item, warehouse, batch_no, pick_qty
	"""
	# This endpoint creates and submits Stock Entries, so require the same
	# permissions a user would need to do that manually.
	if not frappe.has_permission("Stock Entry", "create"):
		frappe.throw(_("Not permitted to create Stock Entries."), frappe.PermissionError)

	if isinstance(picks, str):
		picks = json.loads(picks)

	picks = [p for p in picks if flt(p.get("pick_qty")) > 0]
	if not picks:
		frappe.throw(_("Enter a Pick Quantity for at least one row."))

	wo = frappe.get_doc("Work Order", work_order)

	# validate availability
	for p in picks:
		avail = get_batch_availability(p["alternate_item"], p["warehouse"], p["batch_no"])
		if flt(p["pick_qty"]) > avail:
			frappe.throw(
				_("Row for {0} / batch {1}: pick qty {2} exceeds available {3}.").format(
					p["alternate_item"], p["batch_no"], flt(p["pick_qty"]), avail
				)
			)

	# group by main item -> one Repack Stock Entry per main item.
	# (A single Repack with multiple finished goods would require manual basic rates
	# in ERPNext; one finished good per entry lets ERPNext value it automatically.)
	groups = {}
	for p in picks:
		groups.setdefault(p["main_item"], []).append(p)

	entry_names = []
	for main_item, grp in groups.items():
		total = sum(flt(p["pick_qty"]) for p in grp)
		warehouse = grp[0]["warehouse"]
		batch = target_batch_name(main_item, [p["alternate_item"] for p in grp])

		se = frappe.new_doc("Stock Entry")
		# "Material Club" is a custom Stock Entry Type (purpose = Repack) defined on the site.
		se.stock_entry_type = "Material Club"
		se.purpose = "Repack"
		se.company = wo.company
		# ERPNext clears the standard work_order field for Repack, so link via a custom field
		se.custom_work_order = wo.name
		se.remarks = _("Alternate-item repack for Work Order {0} ({1})").format(wo.name, main_item)

		# consume each picked alternate batch
		for p in grp:
			se.append(
				"items",
				{
					"item_code": p["alternate_item"],
					"qty": flt(p["pick_qty"]),
					"s_warehouse": p["warehouse"],
					"use_serial_batch_fields": 1,
					"batch_no": p["batch_no"],
				},
			)

		# ensure the target batch exists for the main item (reused on repeat inserts
		# with the same alternates, so qty accumulates in the same batch)
		if not frappe.db.exists("Batch", batch):
			frappe.get_doc(
				{"doctype": "Batch", "batch_id": batch, "item": main_item}
			).insert(ignore_permissions=True)

		# produce the combined qty into the main item's batch (single finished good)
		se.append(
			"items",
			{
				"item_code": main_item,
				"qty": total,
				"t_warehouse": warehouse,
				"is_finished_item": 1,
				"use_serial_batch_fields": 1,
				"batch_no": batch,
			},
		)

		se.insert(ignore_permissions=True)
		se.submit()
		entry_names.append(se.name)

	# return a single name if one entry, else the list (client handles both)
	return entry_names[0] if len(entry_names) == 1 else entry_names
