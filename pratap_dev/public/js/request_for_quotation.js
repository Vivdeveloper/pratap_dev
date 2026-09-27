// Request for Quotation — PR-Quantity-driven pack maths.
//
// PR Quantity (custom_pr_quantity) is the Material Request qty carried into the RFQ.
// It is captured once and then STATIC (read-only) — it never changes. From it:
//   No of Unit = ceil(PR Quantity / Standard Pkg Qty)
//   Quantity   = Standard Pkg Qty * No of Unit   (rounded up to whole packs)
//
// Standard Pkg Qty is pulled from the item's "Supplier Pack Sizes" table for the
// RFQ's supplier when blank; editing it (or No of Unit) recomputes downstream.
// The server (pratap_dev.item_supplier_pack.apply_rfq_pack_sizes) is the authoritative
// safety net on save.

frappe.ui.form.on("Request for Quotation Item", {
	item_code(frm, cdt, cdn) {
		rfq_fill_pack_size(frm, cdt, cdn);
	},
	custom_packing_qty(frm, cdt, cdn) {
		rfq_recalc_units(cdt, cdn);
	},
	custom_total_qty(frm, cdt, cdn) {
		// Manual No of Unit override -> Quantity = Std Pkg Qty * No of Unit.
		rfq_apply_units(cdt, cdn);
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
		rfq_recalc_units(cdt, cdn);
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

// First fill only: PR Quantity (static) + Std Pkg Qty -> No of Unit (ceil). Quantity is
// then kept in sync by rfq_apply_units. A manually edited No of Unit is preserved.
function rfq_recalc_units(cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row) {
		return;
	}
	// Capture PR Quantity once from the MR qty carried into the RFQ, then keep it static.
	let pr = flt(row.custom_pr_quantity);
	if (!pr && flt(row.qty) > 0) {
		pr = flt(row.qty);
		frappe.model.set_value(cdt, cdn, "custom_pr_quantity", pr);
	}
	const pack = flt(row.custom_packing_qty);
	// Seed No of Unit only when it's blank (first fill). Editing Std Pkg Qty later does
	// NOT re-derive units -- it just flows into Quantity via rfq_apply_units below.
	if (pack > 0 && pr > 0 && !flt(row.custom_total_qty)) {
		frappe.model.set_value(cdt, cdn, "custom_total_qty", String(Math.ceil(pr / pack)));
	}
	rfq_apply_units(cdt, cdn);
}

// Quantity = Standard Pkg Qty * No of Unit (used when No of Unit is edited by hand).
function rfq_apply_units(cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row) {
		return;
	}
	const pack = flt(row.custom_packing_qty);
	const units = flt(row.custom_total_qty);
	if (pack > 0 && units > 0) {
		frappe.model.set_value(cdt, cdn, "qty", pack * units);
	}
}
