# Copyright (c) 2026, pratap_dev contributors
# For license information, please see license.txt

"""Quotation Comparison Sheet.

Follows one procurement chain end-to-end and presents it as a comparison matrix:

    Material Request (PR)  ->  RFQ  ->  Supplier Quotation  ->  Purchase Order

One row per (Material Request item, RFQ). For each row the supplier quotations
(Draft + Submitted) are ranked by rate per unit ascending -> L1 (lowest), L2, L3,
and the Purchase Order raised against the winning Supplier Quotation is shown
together with the rank at which it was placed (L1/L2/L3).
"""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 130},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 160},
		{"label": _("Material Request (PR)"), "fieldname": "material_request", "fieldtype": "Link", "options": "Material Request", "width": 150},
		{"label": _("PR Qty"), "fieldname": "pr_qty", "fieldtype": "Float", "width": 85},
		{"label": _("RFQ"), "fieldname": "request_for_quotation", "fieldtype": "Link", "options": "Request for Quotation", "width": 150},
		{"label": _("RFQ Status"), "fieldname": "rfq_status", "fieldtype": "Data", "width": 90},
		{"label": _("L1 Supplier"), "fieldname": "l1_supplier", "fieldtype": "Link", "options": "Supplier", "width": 150},
		{"label": _("L1 Rate"), "fieldname": "l1_rate", "fieldtype": "Currency", "width": 90},
		{"label": _("L2 Supplier"), "fieldname": "l2_supplier", "fieldtype": "Link", "options": "Supplier", "width": 150},
		{"label": _("L2 Rate"), "fieldname": "l2_rate", "fieldtype": "Currency", "width": 90},
		{"label": _("L3 Supplier"), "fieldname": "l3_supplier", "fieldtype": "Link", "options": "Supplier", "width": 150},
		{"label": _("L3 Rate"), "fieldname": "l3_rate", "fieldtype": "Currency", "width": 90},
		{"label": _("PO"), "fieldname": "purchase_order", "fieldtype": "Link", "options": "Purchase Order", "width": 150},
		{"label": _("PO Supplier"), "fieldname": "po_supplier", "fieldtype": "Link", "options": "Supplier", "width": 150},
		{"label": _("PO at Rank"), "fieldname": "po_rank", "fieldtype": "Data", "width": 85},
		{"label": _("PO Status"), "fieldname": "po_status", "fieldtype": "Data", "width": 110},
		{"label": _("All Quotes (supplier:rate)"), "fieldname": "sq_list", "fieldtype": "Data", "width": 220},
	]


def get_data(filters):
	mr_items = _get_mr_items(filters)
	if not mr_items:
		return []

	mr_item_names = [r.mr_item for r in mr_items]
	rfq_by_mr_item = _get_rfq_map(mr_item_names)
	quotes_by_mr_item = _get_quotes_map(mr_item_names)
	po_by_mr_item = _get_po_map(mr_item_names)

	sq_state = filters.get("sq_state")           # Draft / Submitted
	supplier_filter = filters.get("supplier")
	rfq_filter = filters.get("request_for_quotation")
	rfq_status_filter = filters.get("rfq_status")
	po_filter = filters.get("purchase_order")
	po_status_filter = filters.get("po_status")
	rank_filter = filters.get("po_rank")         # L1 / L2 / L3

	data = []
	for mr in mr_items:
		rfq_groups = rfq_by_mr_item.get(mr.mr_item) or [None]
		all_quotes = quotes_by_mr_item.get(mr.mr_item, [])
		all_pos = po_by_mr_item.get(mr.mr_item, [])

		for rfq in rfq_groups:
			rfq_name = rfq.request_for_quotation if rfq else None
			rfq_status = rfq.rfq_status if rfq else None

			# Quotes belonging to this RFQ grouping (blank RFQ on the quote = include)
			if rfq_name:
				quotes = [q for q in all_quotes if (not q.request_for_quotation or q.request_for_quotation == rfq_name)]
			else:
				quotes = list(all_quotes)

			if sq_state:
				want = 0 if sq_state == "Draft" else 1
				quotes = [q for q in quotes if q.docstatus == want]

			ranked = _rank_quotes(quotes)

			po, po_rank = _resolve_po(all_pos, quotes, ranked)

			# ---- row-level filters ----
			if supplier_filter:
				suppliers_in_row = {q.supplier for q in ranked}
				if po:
					suppliers_in_row.add(po.supplier)
				if supplier_filter not in suppliers_in_row:
					continue
			if rfq_filter and rfq_name != rfq_filter:
				continue
			if rfq_status_filter and rfq_status != rfq_status_filter:
				continue
			if po_filter and (not po or po.purchase_order != po_filter):
				continue
			if po_status_filter and (not po or po.po_status != po_status_filter):
				continue
			if rank_filter and po_rank != rank_filter:
				continue

			def at(i, attr):
				return ranked[i].get(attr) if i < len(ranked) else None

			data.append({
				"item_code": mr.item_code,
				"item_name": mr.item_name,
				"material_request": mr.material_request,
				"pr_qty": mr.pr_qty,
				"request_for_quotation": rfq_name,
				"rfq_status": rfq_status,
				"l1_supplier": at(0, "supplier"), "l1_rate": at(0, "rate"),
				"l2_supplier": at(1, "supplier"), "l2_rate": at(1, "rate"),
				"l3_supplier": at(2, "supplier"), "l3_rate": at(2, "rate"),
				"purchase_order": po.purchase_order if po else None,
				"po_supplier": po.supplier if po else None,
				"po_rank": po_rank,
				"po_status": po.po_status if po else None,
				"sq_list": ", ".join(
					"{0}:{1}".format(q.supplier_name or q.supplier, flt(q.rate)) for q in ranked
				),
			})

	return data


def _rank_quotes(quotes):
	"""One quote (lowest rate) per supplier, ranked by rate ascending. Rate must be > 0."""
	best_by_supplier = {}
	for q in quotes:
		if flt(q.rate) <= 0:
			continue
		cur = best_by_supplier.get(q.supplier)
		if cur is None or flt(q.rate) < flt(cur.rate):
			best_by_supplier[q.supplier] = q
	return sorted(best_by_supplier.values(), key=lambda x: flt(x.rate))


def _resolve_po(all_pos, quotes, ranked):
	"""Pick the PO for this grouping and the L-rank of its supplier."""
	group_sq_names = {q.supplier_quotation for q in quotes}
	po = None
	for p in all_pos:
		if p.supplier_quotation and p.supplier_quotation in group_sq_names:
			po = p
			break
	if not po and all_pos:
		po = all_pos[0]

	po_rank = None
	if po:
		for idx, q in enumerate(ranked):
			if q.supplier == po.supplier:
				po_rank = "L{0}".format(idx + 1)
				break
	return po, po_rank


def _get_mr_items(filters):
	conditions = ["mr.material_request_type = 'Purchase'", "mr.docstatus < 2"]
	values = {}
	if filters.get("from_date"):
		conditions.append("mr.transaction_date >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("mr.transaction_date <= %(to_date)s")
		values["to_date"] = filters.to_date
	if filters.get("item_code"):
		conditions.append("mri.item_code = %(item_code)s")
		values["item_code"] = filters.item_code
	if filters.get("material_request"):
		conditions.append("mr.name = %(material_request)s")
		values["material_request"] = filters.material_request

	return frappe.db.sql(
		"""
		select mri.name as mr_item, mr.name as material_request,
		       mr.transaction_date, mri.item_code, mri.item_name, mri.qty as pr_qty
		from `tabMaterial Request Item` mri
		inner join `tabMaterial Request` mr on mr.name = mri.parent
		where {conditions}
		order by mr.transaction_date desc, mr.name, mri.idx
		""".format(conditions=" and ".join(conditions)),
		values, as_dict=True,
	)


def _get_rfq_map(mr_item_names):
	rows = frappe.db.sql(
		"""
		select rfqi.material_request_item as mr_item, rfqi.parent as request_for_quotation,
		       rfq.status as rfq_status
		from `tabRequest for Quotation Item` rfqi
		inner join `tabRequest for Quotation` rfq on rfq.name = rfqi.parent
		where rfqi.material_request_item in %(mr_items)s and rfq.docstatus < 2
		""",
		{"mr_items": mr_item_names}, as_dict=True,
	)
	out = {}
	for r in rows:
		out.setdefault(r.mr_item, []).append(r)
	return out


def _get_quotes_map(mr_item_names):
	rows = frappe.db.sql(
		"""
		select sqi.material_request_item as mr_item, sqi.request_for_quotation,
		       sqi.parent as supplier_quotation, sqi.rate, sqi.qty,
		       sq.supplier, sq.supplier_name, sq.status as sq_status, sq.docstatus
		from `tabSupplier Quotation Item` sqi
		inner join `tabSupplier Quotation` sq on sq.name = sqi.parent
		where sqi.material_request_item in %(mr_items)s and sq.docstatus < 2
		""",
		{"mr_items": mr_item_names}, as_dict=True,
	)
	out = {}
	for r in rows:
		out.setdefault(r.mr_item, []).append(r)
	return out


def _get_po_map(mr_item_names):
	rows = frappe.db.sql(
		"""
		select poi.material_request_item as mr_item, poi.supplier_quotation,
		       poi.parent as purchase_order, po.supplier, po.supplier_name,
		       po.status as po_status, po.docstatus
		from `tabPurchase Order Item` poi
		inner join `tabPurchase Order` po on po.name = poi.parent
		where poi.material_request_item in %(mr_items)s and po.docstatus < 2
		""",
		{"mr_items": mr_item_names}, as_dict=True,
	)
	out = {}
	for r in rows:
		out.setdefault(r.mr_item, []).append(r)
	return out
