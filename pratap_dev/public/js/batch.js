// Batch — Package Ledger two-way auto-calc + running available-units column.
// Total Qty = Pack Qty x No of Unit.  Edit No of Unit (or Pack Qty) -> Total updates;
// edit Total directly -> No of Unit is derived (Total / Pack), fractional allowed.
// "Available Units After" = running cumulative No of Unit per warehouse, in row order.

let _rtm_pkg_lock = false;

frappe.ui.form.on("Batch", {
	refresh(frm) {
		render_available_units_after(frm);
	},
});

frappe.ui.form.on("Batch Package Ledger", {
	no_of_unit(frm, cdt, cdn) {
		recalc_total_from_units(cdt, cdn);
		render_available_units_after(frm);
	},
	standard_pkg_qty(frm, cdt, cdn) {
		recalc_total_from_units(cdt, cdn);
		render_available_units_after(frm);
	},
	total_qty(frm, cdt, cdn) {
		recalc_units_from_total(cdt, cdn);
		render_available_units_after(frm);
	},
	custom_package_ledger_add(frm) {
		render_available_units_after(frm);
	},
	custom_package_ledger_remove(frm) {
		render_available_units_after(frm);
	},
	warehouse(frm) {
		render_available_units_after(frm);
	},
});

// Display-only running balance: cumulative No of Unit per warehouse, in idx order.
// Set directly on the rows (not via set_value) so it shows without dirtying the form.
function render_available_units_after(frm) {
	const rows = (frm.doc.custom_package_ledger || [])
		.slice()
		.sort((a, b) => (a.idx || 0) - (b.idx || 0));
	const running = {};
	rows.forEach((r) => {
		const wh = r.warehouse || "";
		running[wh] = (running[wh] || 0) + flt(r.no_of_unit);
		r.available_units_after = running[wh];
	});
	frm.refresh_field("custom_package_ledger");
}

function recalc_total_from_units(cdt, cdn) {
	if (_rtm_pkg_lock) return;
	const row = locals[cdt][cdn];
	const pkg = flt(row.standard_pkg_qty);
	const units = flt(row.no_of_unit);
	if (!pkg) return;
	_rtm_pkg_lock = true;
	frappe.model.set_value(cdt, cdn, "total_qty", pkg * units).always(() => {
		_rtm_pkg_lock = false;
	});
}

function recalc_units_from_total(cdt, cdn) {
	if (_rtm_pkg_lock) return;
	const row = locals[cdt][cdn];
	const pkg = flt(row.standard_pkg_qty);
	const total = flt(row.total_qty);
	if (!pkg) return;
	_rtm_pkg_lock = true;
	frappe.model.set_value(cdt, cdn, "no_of_unit", total / pkg).always(() => {
		_rtm_pkg_lock = false;
	});
}
