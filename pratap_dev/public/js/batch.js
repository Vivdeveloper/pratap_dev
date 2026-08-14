// Batch — Package Ledger two-way auto-calc.
// Total Qty = Pack Qty x No of Unit.  Edit No of Unit (or Pack Qty) -> Total updates;
// edit Total directly -> No of Unit is derived (Total / Pack), fractional allowed.

let _rtm_pkg_lock = false;

frappe.ui.form.on("Batch Package Ledger", {
	no_of_unit(frm, cdt, cdn) {
		recalc_total_from_units(cdt, cdn);
	},
	standard_pkg_qty(frm, cdt, cdn) {
		recalc_total_from_units(cdt, cdn);
	},
	total_qty(frm, cdt, cdn) {
		recalc_units_from_total(cdt, cdn);
	},
});

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
