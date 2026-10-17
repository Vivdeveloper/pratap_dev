// Copyright (c) 2026, pratap_dev contributors
// For license information, please see license.txt

// Pratap Downtime Entry — Downtime (minutes) from From/To Time, Asset filtered by company.
// Consumed items + Stock Entry button: pratap_maintenance/client/consumed_items.js (hooks).

frappe.ui.form.on("Pratap Downtime Entry", {
	setup(frm) {
		frm.set_query("asset", () => ({ filters: { company: frm.doc.company, docstatus: 1 } }));
		frm.set_query("purchase_order", () => ({ filters: { company: frm.doc.company, docstatus: 1 } }));
	},

	from_time(frm) {
		set_downtime(frm);
	},

	to_time(frm) {
		set_downtime(frm);
	},
});

function set_downtime(frm) {
	if (!frm.doc.from_time || !frm.doc.to_time) {
		return;
	}
	const minutes = moment(frm.doc.to_time).diff(moment(frm.doc.from_time), "seconds") / 60;
	frm.set_value("downtime", minutes > 0 ? minutes : 0);
}
