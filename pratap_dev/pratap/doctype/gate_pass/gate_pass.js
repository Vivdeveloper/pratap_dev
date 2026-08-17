// Copyright (c) 2026, saurabh@exacuer.com and contributors
// For license information, please see license.txt

// Gate Pass — pull the PO's item lines into the Items table, let the user record
// how many units were physically received per item, and derive quantities:
//   Total to be Received = No of Unit (PO)      x Standard Pkg Qty   (PO Qty)
//   Actual Received Qty  = No of Unit Received  x Standard Pkg Qty
// Header PO Qty / Actual Received Qty = sums of those columns.

frappe.ui.form.on("Gate Pass", {
	purchase_order_po_no(frm) {
		load_po_items(frm);
	},
	refresh(frm) {
		recompute_totals(frm);
	},
});

frappe.ui.form.on("Gate Pass Item", {
	no_of_unit_received(frm, cdt, cdn) {
		recompute_row(frm, cdt, cdn);
		recompute_totals(frm);
	},
	items_remove(frm) {
		recompute_totals(frm);
	},
});

function load_po_items(frm) {
	const po = frm.doc.purchase_order_po_no;
	if (!po) {
		frm.clear_table("items");
		frm.refresh_field("items");
		recompute_totals(frm);
		return;
	}

	frappe.db.get_doc("Purchase Order", po).then((po_doc) => {
		frm.clear_table("items");
		(po_doc.items || []).forEach((r) => {
			const pkg = flt(r.custom_packing_qty);
			const units = flt(r.custom_total_qty);
			frm.add_child("items", {
				item_code: r.item_code,
				item_name: r.item_name,
				uom: r.uom,
				standard_pkg_qty: pkg,
				no_of_unit: units,
				no_of_unit_received: 0,
				// PO Qty = total qty ordered on the PO line (units x pkg).
				total_to_be_received: flt(r.qty) || pkg * units,
				actual_received_qty: 0,
				po_item: r.name,
			});
		});
		frm.refresh_field("items");
		recompute_totals(frm);
	});
}

function recompute_row(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(
		cdt,
		cdn,
		"actual_received_qty",
		flt(row.no_of_unit_received) * flt(row.standard_pkg_qty)
	);
}

function recompute_totals(frm) {
	let po_qty = 0;
	let actual = 0;
	(frm.doc.items || []).forEach((r) => {
		po_qty += flt(r.total_to_be_received);
		actual += flt(r.actual_received_qty);
	});
	// Header PO Qty / Actual Received Qty are Data fields — store the summed values.
	frm.set_value("received_qty", format_number(po_qty));
	frm.set_value("actual_received_qty", format_number(actual));
}
