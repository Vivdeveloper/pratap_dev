// Request for Quotation — live pre-fill of Standard Pkg Qty + No of Unit.
//
// As soon as you pick an item on a row (with a supplier already on the RFQ), the
// Standard Pkg Qty is pulled from that item's "Supplier Pack Sizes" table for the
// RFQ's supplier, and No of Unit = ceil(Quantity / Standard Pkg Qty) is computed.
// Picking / changing the supplier refills the item rows too.
//
// The server (pratap_dev.item_supplier_pack.apply_rfq_pack_sizes) still fills any
// remaining blanks on save as a safety net. Both only fill when the field is blank,
// so anything you type by hand is preserved — the fields stay fully editable.

frappe.ui.form.on("Request for Quotation Item", {
	item_code(frm, cdt, cdn) {
		rfq_fill_pack_size(frm, cdt, cdn);
	},
	custom_packing_qty(frm, cdt, cdn) {
		rfq_recalc_units(cdt, cdn);
	},
	qty(frm, cdt, cdn) {
		rfq_recalc_units(cdt, cdn);
	},
});

frappe.ui.form.on("Request for Quotation Supplier", {
	supplier(frm) {
		// Supplier drives the lookup — (re)fill every item row that's still blank.
		(frm.doc.items || []).forEach((row) => rfq_fill_pack_size(frm, row.doctype, row.name));
	},
});

function rfq_current_supplier(frm) {
	if (frm.doc.custom_supplier_code) {
		return frm.doc.custom_supplier_code;
	}
	const suppliers = frm.doc.suppliers || [];
	return suppliers.length ? suppliers[0].supplier : null;
}

function rfq_fill_pack_size(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row || !row.item_code) {
		return;
	}
	const supplier = rfq_current_supplier(frm);
	if (!supplier) {
		return;
	}
	frappe.call({
		method: "pratap_dev.item_supplier_pack.get_pack_size",
		args: { item_code: row.item_code, supplier: supplier },
		callback(r) {
			const pack = flt(r.message);
			// Fill Standard Pkg Qty only when blank (manual entry wins).
			if (pack > 0 && !flt(row.custom_packing_qty)) {
				frappe.model.set_value(cdt, cdn, "custom_packing_qty", String(pack));
			}
			rfq_recalc_units(cdt, cdn);
		},
	});
}

function rfq_recalc_units(cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row) {
		return;
	}
	const pack = flt(row.custom_packing_qty);
	const qty = flt(row.qty);
	if (pack > 0 && qty > 0) {
		frappe.model.set_value(cdt, cdn, "custom_total_qty", String(Math.ceil(qty / pack)));
	}
}
