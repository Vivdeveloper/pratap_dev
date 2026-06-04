const PRATAP_QC_BUTTON_GROUP = __("Quality");

frappe.ui.form.on("Purchase Receipt", {
	refresh(frm) {
		setup_pratap_qc_buttons(frm);
		if (frm.doc.items) {
			is_qc_checked = frm?.doc?.items[0].qc_required;
			if (is_qc_checked && frm.doc.docstatus === 0) {
				frm.page.clear_primary_action();
			}
		}
	},
});

frappe.ui.form.on("Purchase Receipt Item", {
	// item_code(frm, cdt, cdn) {
	// 	const row = locals[cdt][cdn];
	// 	if (row.qc_required){
	// 		frm.page.clear_primary_action();
	// 	}
	// },
	custom_pratap_quality_inspection(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.custom_pratap_quality_inspection) {
			return;
		}

		frappe.db.get_value(
			"Pratap Quality Inspection",
			row.custom_pratap_quality_inspection,
			"custom_density",
			(r) => {
				if (r?.custom_density != null && r.custom_density !== "") {
					frappe.model.set_value(cdt, cdn, "custom_density", flt(r.custom_density));
				}
			}
		);
	},
});

frappe.ui.form.on("Purchase Invoice", {
	refresh(frm) {
		setup_pratap_qc_buttons(frm);
	},
});

frappe.ui.form.on("Delivery Note", {
	refresh(frm) {
		setup_pratap_qc_buttons(frm);
	},
});

frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		setup_pratap_qc_buttons(frm);
	},
});

function clear_pratap_qc_buttons(frm) {
	(frm._pratap_qc_button_labels || []).forEach(({ label, group }) => {
		frm.remove_custom_button(label, group);
	});
	frm._pratap_qc_button_labels = [];
}

function add_pratap_qc_button(frm, label, action) {
	frm._pratap_qc_button_labels = frm._pratap_qc_button_labels || [];
	frm.add_custom_button(label, action, PRATAP_QC_BUTTON_GROUP);
	frm._pratap_qc_button_labels.push({ label, group: PRATAP_QC_BUTTON_GROUP });
}

async function setup_pratap_qc_buttons(frm) {
	clear_pratap_qc_buttons(frm);

	if (frm.is_new() || ![0, 1].includes(frm.doc.docstatus)) {
		return;
	}

	if (!frappe.model.can_create("Pratap Quality Inspection")) {
		return;
	}

	if (frm.doctype === "Purchase Receipt") {
		await setup_grn_pratap_qc_buttons(frm);
		return;
	}

	if (frm.doctype === "Purchase Invoice" && !frm.doc.update_stock) {
		return;
	}

	add_pratap_qc_button(frm, __("Create Pratap QC"), () => create_pratap_qc_from_reference(frm));
}

async function setup_grn_pratap_qc_buttons(frm) {
	const { message: data } = await frappe.call({
		method: "pratap_dev.purchase_receipt.get_pratap_qc_status_for_grn",
		args: { purchase_receipt: frm.doc.name },
	});

	if (!data || data.skip) {
		return;
	}

	(data.open_qcs || []).forEach((qc) => {
		const label =
			data.open_qcs.length === 1 && !data.can_create
				? __("Open Pratap QC")
				: __("Open {0} ({1})", [qc.name, __(qc.status || "Pending")]);

		add_pratap_qc_button(frm, label, () =>
			frappe.set_route("Form", "Pratap Quality Inspection", qc.name)
		);
	});

	(data.view_qcs || []).forEach((qc) => {
		add_pratap_qc_button(frm, __("View {0}", [qc.name]), () =>
			frappe.set_route("Form", "Pratap Quality Inspection", qc.name)
		);
	});

	if (data.can_create) {
		add_pratap_qc_button(frm, __("Create Pratap QC"), () =>
			create_pratap_qc_from_grn(frm, data.items_need_create || [])
		);
	}
}

async function create_pratap_qc_from_grn(frm, items_need_create) {
	if (!items_need_create.length) {
		frappe.msgprint(__("All GRN items already have a Pratap Quality Inspection."));
		return;
	}

	const selected_item = await pick_grn_item_for_qc(items_need_create);
	if (!selected_item) {
		return;
	}

	await open_new_pratap_qc(frm, selected_item);
}

async function create_pratap_qc_from_reference(frm) {
	const items = frm.doc.items || [];
	if (!items.length) {
		frappe.msgprint(__("No items found in this document."));
		return;
	}

	let selected_item = items[0];
	if (frm.doctype === "Purchase Receipt") {
		selected_item = await pick_grn_item_for_qc(
			items.map((row) => ({
				name: row.name,
				item_code: row.item_code,
				item_name: row.item_name,
				qty: row.qty,
				uom: row.uom,
				stock_uom: row.stock_uom,
				work_order: row.work_order,
			}))
		);
		if (!selected_item) {
			return;
		}
	}

	await open_new_pratap_qc(frm, selected_item);
}

async function open_new_pratap_qc(frm, selected_item) {
	const qc_defaults = {
		inspection_type: get_inspection_type(frm.doctype),
		reference_type: get_reference_type(frm.doctype),
		reference_doctype: frm.doctype,
		reference_name: frm.doc.name,
		work_order: selected_item.work_order || "",
		company: frm.doc.company,
		production_item: selected_item.item_code || "",
		item_name: selected_item.item_name || "",
		reference_qty: flt(selected_item.qty),
		sales_uom: selected_item.uom || selected_item.stock_uom || "",
		status: "Pending",
	};

	if (selected_item.item_code) {
		const item_fields = await frappe.db.get_value("Item", selected_item.item_code, ["purchase_uom"]);
		qc_defaults.purchase_uom = item_fields?.message?.purchase_uom || "";
		if (
			qc_defaults.purchase_uom &&
			qc_defaults.sales_uom &&
			qc_defaults.purchase_uom.toLowerCase() === qc_defaults.sales_uom.toLowerCase()
		) {
			qc_defaults.custom_density = 1;
		}
	}

	frappe.new_doc("Pratap Quality Inspection", qc_defaults);
}

function get_reference_type(doctype) {
	if (doctype === "Purchase Receipt") {
		return "GRN";
	}
	return doctype;
}

function get_inspection_type(doctype) {
	if (doctype === "Purchase Receipt" || doctype === "Purchase Invoice") {
		return "Incoming";
	}
	return "Outgoing";
}

function pick_grn_item_for_qc(items) {
	if (!items.length) {
		frappe.msgprint(__("No items are pending Pratap Quality Inspection."));
		return Promise.resolve(null);
	}

	if (items.length === 1) {
		return Promise.resolve(items[0]);
	}

	const option_map = new Map();
	const option_labels = items.map((row, index) => {
		const label = `${index + 1}. ${row.item_code || ""} - ${row.item_name || ""} (${flt(row.qty)} ${row.uom || ""})`;
		option_map.set(label, row);
		return label;
	});

	return new Promise((resolve) => {
		const dialog = new frappe.ui.Dialog({
			title: __("Select GRN Item"),
			fields: [
				{
					fieldname: "item_label",
					fieldtype: "Select",
					label: __("Item"),
					reqd: 1,
					options: option_labels.join("\n"),
				},
			],
			primary_action_label: __("Continue"),
			primary_action(values) {
				const selected = option_map.get(values.item_label);
				dialog.hide();
				resolve(selected || null);
			},
		});
		dialog.set_value("item_label", option_labels[0]);
		dialog.show();
	});
}
