frappe.ui.form.on("Purchase Receipt", {
	refresh(frm) {
		add_create_pratap_qc_button(frm);
	},
});

frappe.ui.form.on("Purchase Invoice", {
	refresh(frm) {
		add_create_pratap_qc_button(frm);
	},
});

frappe.ui.form.on("Delivery Note", {
	refresh(frm) {
		add_create_pratap_qc_button(frm);
	},
});

frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		add_create_pratap_qc_button(frm);
	},
});

function add_create_pratap_qc_button(frm) {
	if (frm.doc.docstatus !== 1) {
		return;
	}

	frm.add_custom_button(__("Create Pratap QC"), async () => {
		const reference_type = get_reference_type(frm.doctype);
		const inspection_type = get_inspection_type(frm.doctype);
		const selected_item = await get_item_for_qc(frm);
		if (!selected_item) {
			return;
		}

		frappe.new_doc("Pratap Quality Inspection", {
			inspection_type,
			reference_type,
			reference_doctype: frm.doctype,
			reference_name: frm.doc.name,
			work_order: selected_item.work_order || "",
			company: frm.doc.company,
			production_item: selected_item.item_code || "",
			item_name: selected_item.item_name || "",
			reference_qty: flt(selected_item.qty),
			sales_uom: selected_item.uom || selected_item.stock_uom || "",
		});
	});
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

function get_work_order_from_items(items) {
	if (!items || !items.length) {
		return "";
	}

	const row_with_work_order = items.find((row) => row.work_order);
	return row_with_work_order ? row_with_work_order.work_order : "";
}

function get_item_for_qc(frm) {
	const items = frm.doc.items || [];
	if (!items.length) {
		frappe.msgprint(__("No items found in this document."));
		return Promise.resolve(null);
	}

	if (frm.doctype !== "Purchase Receipt") {
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
			primary_action_label: __("Create"),
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
