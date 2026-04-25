// Copyright (c) 2026, saurabh@exacuer.com and contributors
// For license information, please see license.txt

frappe.ui.form.on("Pratap Quality Inspection", {
	setup(frm) {
		set_reference_doctype(frm);
	},

	refresh(frm) {
		set_reference_doctype(frm);
	},

	reference_type(frm) {
		const previous_doctype = frm.doc.reference_doctype;
		set_reference_doctype(frm);
		if (previous_doctype !== frm.doc.reference_doctype) {
			frm.set_value("reference_name", "");
		}
	},

	reference_name(frm) {
		fetch_reference_item_details(frm);
	},

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

function set_reference_doctype(frm) {
	const doctype_map = {
		GRN: "Purchase Receipt",
		"Purchase Invoice": "Purchase Invoice",
		"Delivery Note": "Delivery Note",
		"Sales Invoice": "Sales Invoice",
		"Work Order": "Work Order",
		"Job Card": "Job Card",
		"Stock Entry": "Stock Entry",
	};
	const mapped_doctype = doctype_map[frm.doc.reference_type] || "";
	if (frm.doc.reference_doctype !== mapped_doctype) {
		frm.set_value("reference_doctype", mapped_doctype);
	}
}

function fetch_reference_item_details(frm) {
	if (!frm.doc.reference_type || !frm.doc.reference_name) {
		return;
	}

	if (frm.doc.reference_type === "Work Order") {
		frm.set_value("work_order", frm.doc.reference_name);
		return;
	}

	const reference_doctype = frm.doc.reference_doctype;
	if (!reference_doctype) {
		return;
	}

	frappe.db.get_doc(reference_doctype, frm.doc.reference_name).then((doc) => {
		const items = doc.items || [];
		if (!items.length) {
			return;
		}
		let selected_item = items[0];
		if (frm.doc.production_item) {
			selected_item =
				items.find((row) => row.item_code === frm.doc.production_item) || selected_item;
		}
		if (frm.doc.work_order) {
			selected_item =
				items.find((row) => row.work_order && row.work_order === frm.doc.work_order) ||
				selected_item;
		}

		frm.set_value("company", doc.company || "");
		frm.set_value("production_item", selected_item.item_code || "");
		frm.set_value("item_name", selected_item.item_name || "");
		frm.set_value("sales_uom", selected_item.uom || selected_item.stock_uom || "");
		frm.set_value("reference_qty", flt(selected_item.qty));

		if (selected_item.work_order) {
			frm.set_value("work_order", selected_item.work_order);
		}
	});
}
