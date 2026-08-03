frappe.ui.form.on("Supplier Quotation", {
	refresh(frm) {
		if (pratap_dev.last_buying_rates.should_show(frm)) {
			frm.add_custom_button(
				__("Last Buying Rate"),
				() => show_last_buying_rates(frm),
				__("Tools")
			);
		}

		if (frm.doc.docstatus === 1) {
			// Replace the stock "Purchase Order" create button so users pick which
			// items go into the PO instead of it always mapping every row.
			frm.remove_custom_button(__("Purchase Order"), __("Create"));
			frm.add_custom_button(
				__("Purchase Order"),
				() => show_create_purchase_order_dialog(frm),
				__("Create")
			);
			frm.page.set_inner_btn_group_as_primary(__("Create"));
		}
	},

	async before_save(frm) {
		if (pratap_dev.last_buying_rates.should_show(frm)) {
			await show_last_buying_rates(frm);
		}
	},

	async after_workflow_action(frm) {
		if (pratap_dev.last_buying_rates.should_show(frm)) {
			await show_last_buying_rates(frm);
		}
	},
});

frappe.ui.form.on("Supplier Quotation Item", {
	item_code(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		frm.model.set_value(cdt, cdn, "rate", "");
	},
});
function show_last_buying_rates(frm) {
	return pratap_dev.last_buying_rates.show(frm, {
		rate_column_label: __("Rate"),
		current_po: "",
	});
}

function show_create_purchase_order_dialog(frm) {
	if (!(frm.doc.items || []).length) {
		frappe.msgprint(__("No items to create a Purchase Order from."));
		return;
	}

	// Rows already covered by a submitted Purchase Order can't be selected again --
	// look these up by the child row name (supplier_quotation_item) before building the dialog.
	frappe.db
		.get_list("Purchase Order Item", {
			filters: { supplier_quotation: frm.doc.name, docstatus: 1 },
			fields: ["supplier_quotation_item", "parent"],
			limit: 0,
		})
		.then((rows) => {
			const po_by_row = {};
			(rows || []).forEach((row) => {
				po_by_row[row.supplier_quotation_item] = po_by_row[row.supplier_quotation_item] || [];
				if (!po_by_row[row.supplier_quotation_item].includes(row.parent)) {
					po_by_row[row.supplier_quotation_item].push(row.parent);
				}
			});

			const data = (frm.doc.items || []).map((d) => ({
				docname: d.name,
				item_code: d.item_code,
				item_name: d.item_name,
				qty: d.qty,
				uom: d.uom,
				select: 0,
				already_created: po_by_row[d.name] ? 1 : 0,
				purchase_order: (po_by_row[d.name] || []).join(", "),
			}));

			render_create_purchase_order_dialog(frm, data);
		});
}

function render_create_purchase_order_dialog(frm, data) {
	const dialog = new frappe.ui.Dialog({
		title: __("Select Items for Purchase Order"),
		size: "large",
		fields: [
			{
				fieldname: "selected_items",
				fieldtype: "Table",
				label: __("Items"),
				cannot_add_rows: true,
				in_place_edit: false,
				data: data,
				get_data: () => data,
				fields: [
					{ fieldtype: "Data", fieldname: "docname", hidden: 1 },
					{ fieldtype: "Check", fieldname: "already_created", hidden: 1 },
					{
						fieldtype: "Check",
						fieldname: "select",
						label: __("Select"),
						in_list_view: 1,
						columns: 1,
						read_only_depends_on: "eval:doc.already_created",
					},
					{
						fieldtype: "Data",
						fieldname: "item_code",
						label: __("Item Code"),
						in_list_view: 1,
						read_only: 1,
						columns: 3,
					},
					{
						fieldtype: "Data",
						fieldname: "item_name",
						label: __("Item Name"),
						in_list_view: 1,
						read_only: 1,
						columns: 3,
					},
					{
						fieldtype: "Float",
						fieldname: "qty",
						label: __("Qty"),
						in_list_view: 1,
						read_only: 1,
						columns: 2,
					},
					{
						fieldtype: "Data",
						fieldname: "uom",
						label: __("UOM"),
						in_list_view: 1,
						read_only: 1,
						columns: 2,
					},
					{
						fieldtype: "Data",
						fieldname: "purchase_order",
						label: __("Already Created"),
						in_list_view: 1,
						read_only: 1,
						columns: 2,
					},
				],
			},
		],
		primary_action_label: __("Create Purchase Order"),
		primary_action() {
			const values = dialog.get_values();
			const selected_names = (values.selected_items || [])
				.filter((row) => row.select)
				.map((row) => row.docname);

			if (!selected_names.length) {
				frappe.msgprint(__("Please select at least one item."));
				return;
			}

			dialog.hide();
			frappe.call({
				type: "POST",
				method: "frappe.model.mapper.make_mapped_doc",
				args: {
					method: "erpnext.buying.doctype.supplier_quotation.supplier_quotation.make_purchase_order",
					source_name: frm.doc.name,
					// Frappe's native row-selection filter: {parent_table_fieldname: [row names]}.
					// The mapper's own `args`/`filtered_children` support is never actually
					// forwarded by make_mapped_doc, so this is the only mechanism that works,
					// and it's driven from our own "select" checkbox column (read via
					// dialog.get_values()) rather than the grid's native row-check column --
					// that native checkbox's docname lookup was unreliable for this ad-hoc table.
					selected_children: { items: selected_names },
				},
				freeze: true,
				freeze_message: __("Creating Purchase Order..."),
				callback(r) {
					if (!r.exc) {
						frappe.model.sync(r.message);
						frappe.set_route("Form", r.message.doctype, r.message.name);
					}
				},
			});
		},
	});

	dialog.show();

	// Hide the grid's native row-select checkbox column -- we already have our own
	// explicit "Select" field, so showing both would be confusing and redundant.
	dialog.$wrapper.find(".row-check").hide();
}
