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
		// NOTE: do NOT mutate fields (set_value) here — doing so on refresh dirties
		// the form on open and can leave the Save button unresponsive. Totals are
		// recomputed only on real edits (PO load + item-row changes) below.
		restrict_invoice_date_to_today(frm);
	},
	onload(frm) {
		restrict_invoice_date_to_today(frm);
	},
});

// Grey out future dates in the Supplier Invoice Date picker (max = today).
// air-datepicker's maxDate needs a REAL Date object (a string throws and breaks the
// whole form render), so we pass `new Date()`. Wrapped in try/catch so a picker quirk
// can never blank the form. Backed by the server-side "no future date" validation.
function restrict_invoice_date_to_today(frm) {
	const field = frm.fields_dict.supplier_invoice_date;
	if (!field) return;
	try {
		const today = new Date();
		field.df.max_date = today;
		if (field.datepicker && typeof field.datepicker.update === "function") {
			field.datepicker.update({ maxDate: today });
		}
	} catch (e) {
		console.warn("Gate Pass: could not restrict invoice date", e);
	}
}

frappe.ui.form.on("Gate Pass Item", {
	no_of_unit_received(frm, cdt, cdn) {
		recompute_row(frm, cdt, cdn);
		recompute_totals(frm);
	},
	// Pack Qty / No of Unit are now editable: recompute the derived columns.
	standard_pkg_qty(frm, cdt, cdn) {
		recompute_row(frm, cdt, cdn);
		recompute_totals(frm);
	},
	no_of_unit(frm, cdt, cdn) {
		recompute_row(frm, cdt, cdn);
		recompute_totals(frm);
	},
	// Actual Received Qty can be overridden directly — just roll up the totals.
	actual_received_qty(frm) {
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
	const pkg = flt(row.standard_pkg_qty);
	// Total to be Received = No of Unit x Pack Qty; Actual = Units Received x Pack Qty.
	frappe.model.set_value(cdt, cdn, "total_to_be_received", flt(row.no_of_unit) * pkg);
	frappe.model.set_value(cdt, cdn, "actual_received_qty", flt(row.no_of_unit_received) * pkg);
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
