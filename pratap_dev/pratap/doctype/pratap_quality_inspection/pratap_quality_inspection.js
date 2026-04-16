// Copyright (c) 2026, saurabh@exacuer.com and contributors
// For license information, please see license.txt

frappe.ui.form.on("Pratap Quality Inspection", {
	reference_qty(frm) {
		set_density_qty(frm);
		set_raw_material_required_qty(frm);
		validate_total_raw_material_percentage(frm);
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

frappe.ui.form.on("Pratap Quality Inspection Raw Material", {
	mat_req_in_pecentage(frm) {
		set_raw_material_required_qty(frm);
		validate_total_raw_material_percentage(frm);
	},

	item_code(frm, cdt, cdn) {
		set_row_actual_qty(cdt, cdn);
	},

	source_warehouse(frm, cdt, cdn) {
		set_row_actual_qty(cdt, cdn);
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

function set_raw_material_required_qty(frm) {
	const reference_qty = flt(frm.doc.reference_qty);
	(frm.doc.raw_materials || []).forEach((row) => {
		const percentage = flt(row.mat_req_in_pecentage);
		const total_req_qty = reference_qty * (percentage / 100);
		frappe.model.set_value(row.doctype, row.name, "total_req_qty", total_req_qty);
	});
}

function validate_total_raw_material_percentage(frm) {
	const total_percentage = (frm.doc.raw_materials || []).reduce(
		(total, row) => total + flt(row.mat_req_in_pecentage),
		0
	);

	if (total_percentage > 100) {
		frappe.msgprint(
			__(
				"Total Raw Material % cannot be greater than 100. Current total is {0}.",
				[total_percentage]
			)
		);
	}
}

function set_row_actual_qty(cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row || !row.item_code || !row.source_warehouse) {
		frappe.model.set_value(cdt, cdn, "actual_qty", 0);
		return;
	}

	frappe.db
		.get_value(
			"Bin",
			{ item_code: row.item_code, warehouse: row.source_warehouse },
			"actual_qty"
		)
		.then((r) => {
			const actualQty = flt(r.message?.actual_qty);
			frappe.model.set_value(cdt, cdn, "actual_qty", actualQty);
		});
}
