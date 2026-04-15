// Copyright (c) 2026, saurabh@exacuer.com and contributors
// For license information, please see license.txt

frappe.ui.form.on("Pratap Quality Inspection", {
	reference_qty(frm) {
		set_density_qty(frm);
	},

	custom_density(frm) {
		set_density_qty(frm);
	},

	process_loss(frm) {
		set_density_qty(frm);
	},

	production_item(frm) {
		if (!frm.doc.quality_inspection_template) {
			frm.call("get_item_specification_details").then(() => {
				frm.refresh_field("readings");
			});
		}
	},

	quality_inspection_template(frm) {
		frm.call("get_item_specification_details").then(() => {
			frm.refresh_field("readings");
		});
	},
});

function set_density_qty(frm) {
	const reference_qty = flt(frm.doc.reference_qty);
	const custom_density = flt(frm.doc.custom_density);
	const process_loss = flt(frm.doc.process_loss);
	const density_qty = custom_density > 0 ? reference_qty / custom_density : 0;
	const multiplier = 1 - process_loss / 100;
	const finished_qty = multiplier > 0 ? density_qty * multiplier : 0;
	frm.set_value("density_qty", density_qty);
	frm.set_value("finished_qty", finished_qty);
}
