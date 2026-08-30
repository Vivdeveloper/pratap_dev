# Copyright (c) 2026, pratap_dev contributors
# License: MIT
"""Supplier Quotation -> partial Purchase Order.

The custom "Create Purchase Order" dialog on a Supplier Quotation lets the user
enter, per item, HOW MANY UNITS to order now. The PO is created only for that
quantity (units x standard pkg qty), and never more than what is still pending on
the source Material Request (MR row qty - already ordered, variant-aware).
"""

import json

import frappe
from frappe import _
from frappe.utils import flt

from pratap_dev.material_request_rfq import get_ordered_qty_by_mr_row


def _pending_by_mri(mri_names):
	"""Pending qty per Material Request Item row = row qty - already ordered."""
	mri_names = list({n for n in (mri_names or []) if n})
	if not mri_names:
		return {}
	ordered = get_ordered_qty_by_mr_row(mri_names)
	pending = {}
	for r in frappe.get_all(
		"Material Request Item", filters={"name": ["in", mri_names]}, fields=["name", "qty"]
	):
		pending[r.name] = max(flt(r.qty) - ordered.get(r.name, 0.0), 0.0)
	return pending


@frappe.whitelist()
def get_sq_po_context(supplier_quotation):
	"""Per SQ item: standard pkg qty, no of unit, and pending (None = no MR cap)."""
	sq = frappe.get_doc("Supplier Quotation", supplier_quotation)
	sq.check_permission("read")

	mri_by_item = {
		it.name: it.material_request_item for it in sq.items if it.get("material_request_item")
	}
	pending_by_mri = _pending_by_mri(list(mri_by_item.values()))

	# Which SQ rows already have a submitted Purchase Order. Done server-side (raw SQL,
	# no Purchase Order Item permission check) so restricted Buying users who lack
	# Purchase Order read access don't hit "No permission for Purchase Order Item".
	po_by_row = _po_by_sq_item(supplier_quotation)

	out = {}
	for it in sq.items:
		mri = mri_by_item.get(it.name)
		std_pkg = flt(it.get("custom_packing_qty")) or 1.0
		# No of Unit flows from the row when set; otherwise derive it from qty so the
		# popup isn't blank (same qty = std pkg x no of unit invariant as the MR).
		no_of_unit = flt(it.get("custom_total_qty")) or (flt(it.qty) / std_pkg if std_pkg else 0.0)
		out[it.name] = {
			"std_pkg": std_pkg,
			"no_of_unit": flt(no_of_unit, 3),
			"sq_qty": flt(it.qty),
			"material_request_item": mri,
			"pending": pending_by_mri.get(mri) if mri else None,  # None => no cap
			"purchase_orders": po_by_row.get(it.name, []),
			# Required Date carried from the RFQ item (shown in the Create-PO popup).
			"required_date": str(it.get("custom_required_date") or "") or None,
		}
	return out


def set_required_date_from_rfq(doc, method=None):
	"""Carry each item's Required Date (RFQ Item.schedule_date) onto the Supplier
	Quotation item (custom_required_date) — works for desk/portal/any creation path,
	keyed on request_for_quotation_item."""
	if not doc.meta.get_field("items"):
		return
	item_meta = frappe.get_meta("Supplier Quotation Item")
	if not item_meta.has_field("custom_required_date"):
		return
	for it in doc.items:
		if it.get("custom_required_date") or not it.get("request_for_quotation_item"):
			continue
		rfq_date = frappe.db.get_value(
			"Request for Quotation Item", it.request_for_quotation_item, "schedule_date"
		)
		if rfq_date:
			it.custom_required_date = rfq_date


@frappe.whitelist()
def get_rfq_required_dates(rfq_item_names):
	"""Map RFQ Item name -> its Required Date (schedule_date). Used by the SQ form to
	fill custom_required_date on a freshly-created (unsaved) draft, before the save-time
	hook runs, so the column isn't blank until first save."""
	if isinstance(rfq_item_names, str):
		rfq_item_names = json.loads(rfq_item_names)
	names = list({n for n in (rfq_item_names or []) if n})
	if not names:
		return {}
	out = {}
	for r in frappe.get_all(
		"Request for Quotation Item",
		filters={"name": ["in", names]},
		fields=["name", "schedule_date"],
	):
		if r.schedule_date:
			out[r.name] = str(r.schedule_date)
	return out


def _po_by_sq_item(supplier_quotation):
	"""Map each SQ item -> list of submitted Purchase Orders raised from it."""
	rows = frappe.db.sql(
		"""
		SELECT poi.supplier_quotation_item AS sq_item, poi.parent AS po
		FROM `tabPurchase Order Item` poi
		INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
		WHERE poi.supplier_quotation = %(sq)s AND po.docstatus = 1
		""",
		{"sq": supplier_quotation},
		as_dict=True,
	)
	out = {}
	for r in rows:
		if not r.sq_item:
			continue
		out.setdefault(r.sq_item, [])
		if r.po not in out[r.sq_item]:
			out[r.sq_item].append(r.po)
	return out


@frappe.whitelist()
def make_partial_purchase_order(source_name, rows, required_date=None):
	"""Create a PO for only the entered units per item (qty = units x std pkg),
	capped at each Material Request row's pending qty. Returns the unsaved PO.

	`required_date` (chosen in the popup) flows to the PO's Required By (schedule_date),
	including each PO item's Required By."""
	from erpnext.buying.doctype.supplier_quotation.supplier_quotation import make_purchase_order

	if isinstance(rows, str):
		rows = json.loads(rows)

	units_by_item = {}
	for r in rows or []:
		name = r.get("sq_item")
		units = flt(r.get("units"))
		if name and units > 0:
			units_by_item[name] = units
	if not units_by_item:
		frappe.throw(_("Enter No of Unit to order for at least one item."))

	sq = frappe.get_doc("Supplier Quotation", source_name)
	sq.check_permission("read")

	pkg_by_item = {it.name: (flt(it.get("custom_packing_qty")) or 1.0) for it in sq.items}
	mri_by_item = {
		it.name: it.material_request_item for it in sq.items if it.get("material_request_item")
	}
	qty_by_item = {name: units * pkg_by_item.get(name, 1.0) for name, units in units_by_item.items()}

	# Server-side pending cap (don't trust the client): total requested qty per MR
	# row must not exceed that row's pending.
	pending_by_mri = _pending_by_mri(list(mri_by_item.values()))
	req_by_mri = {}
	for name, qty in qty_by_item.items():
		mri = mri_by_item.get(name)
		if mri:
			req_by_mri[mri] = req_by_mri.get(mri, 0.0) + qty
	for mri, req in req_by_mri.items():
		pend = pending_by_mri.get(mri)
		if pend is not None and req > pend + 0.0001:
			frappe.throw(
				_(
					"Cannot order {0} against Material Request item {1}: only {2} is pending."
				).format(req, mri, pend)
			)

	# Map only the selected SQ rows, then override each PO item's qty.
	po = make_purchase_order(source_name, args={"filtered_children": list(units_by_item.keys())})
	for item in po.items:
		sqi = item.get("supplier_quotation_item")
		if sqi in qty_by_item:
			item.qty = qty_by_item[sqi]
			item.stock_qty = item.qty * flt(item.get("conversion_factor") or 1)
			if item.meta.has_field("custom_total_qty"):
				item.custom_total_qty = units_by_item[sqi]

	# Flow the chosen Required Date to the PO's Required By (header + each item).
	if required_date:
		po.schedule_date = required_date
		for item in po.items:
			if item.meta.has_field("schedule_date"):
				item.schedule_date = required_date
	return po
