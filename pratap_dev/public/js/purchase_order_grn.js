frappe.ui.form.on("Purchase Order", {
	refresh(frm) {
		if (!can_create_grn(frm)) {
			return;
		}

		frm.add_custom_button(__("Create GRN"), () => show_create_grn_dialog(frm), __("Create"));
	},
});

function can_create_grn(frm) {
	if (frm.doc.docstatus !== 1) {
		return false;
	}
	if (["Closed", "On Hold"].includes(frm.doc.status)) {
		return false;
	}
	return flt(frm.doc.per_received) < 100;
}

function show_create_grn_dialog(frm) {
	frappe.call({
		method: "pratap_dev.purchase_order_grn.get_po_grn_dialog_items",
		args: { purchase_order: frm.doc.name },
		freeze: true,
		freeze_message: __("Loading items..."),
		callback(r) {
			const items = r.message || [];
			if (!items.length) {
				frappe.msgprint(__("No pending balance found for GRN on this Purchase Order."));
				return;
			}
			open_create_grn_dialog(frm, items);
		},
	});
}

function open_create_grn_dialog(frm, items) {
	const dialog = new frappe.ui.Dialog({
		title: __("Create GRN from {0}", [frm.doc.name]),
		size: "extra-large",
		fields: [
			{
				fieldname: "items",
				fieldtype: "Table",
				label: __("Items"),
				cannot_add_rows: true,
				cannot_delete_rows: true,
				in_place_edit: true,
				data: items.map((row) => prepare_grn_dialog_row(row)),
				fields: get_grn_dialog_table_fields(),
			},
		],
		primary_action_label: __("Create GRN"),
		primary_action() {
			const rows = dialog.get_value("items") || [];
			const payload = [];

			for (const row of rows) {
				recalculate_grn_row(row);

				const no_of_unit = flt(row.custom_total_qty);
				const total_qty = flt(row.qty);
				const balance_units = flt(row.balance_no_of_unit);
				const balance_qty = flt(row.balance_grn_qty);

				if (no_of_unit <= 0 || total_qty <= 0) {
					continue;
				}
				if (no_of_unit > balance_units) {
					frappe.throw(
						__(
							"No of Unit for {0} cannot be greater than Balance No of Unit {1}",
							[row.item_code, balance_units]
						)
					);
				}
				if (total_qty > balance_qty) {
					frappe.throw(
						__(
							"Total Qty for {0} cannot be greater than Balance GRN Qty {1}",
							[row.item_code, balance_qty]
						)
					);
				}

				payload.push({
					po_item: row.po_item,
					grn_qty: total_qty,
					qty: total_qty,
					custom_packing_qty: row.custom_packing_qty,
					custom_total_qty: no_of_unit,
				});
			}

			if (!payload.length) {
				frappe.throw(__("Please enter No of Unit for at least one item."));
			}

			dialog.hide();

			frappe.call({
				method: "pratap_dev.purchase_order_grn.make_purchase_receipts_from_po",
				args: {
					purchase_order: frm.doc.name,
					items: payload,
				},
				freeze: true,
				freeze_message: __("Creating and saving Purchase Receipts..."),
				callback(response) {
					if (response.exc) {
						return;
					}

					const receipts = response.message || [];
					receipts.forEach((doc) => frappe.model.sync(doc));

					frm.reload_doc();

					if (!receipts.length) {
						return;
					}

					const links = receipts
						.map(
							(doc) =>
								`<a href="/app/${frappe.router.slug(doc.doctype)}/${doc.name}">${doc.name}</a> (${__(
									"Saved"
								)})`
						)
						.join("<br>");

					frappe.show_alert({
						message: __("{0} GRN(s) saved", [receipts.length]),
						indicator: "green",
					});

					if (receipts.length === 1) {
						frappe.set_route("Form", receipts[0].doctype, receipts[0].name);
						return;
					}

					frappe.msgprint({
						title: __("{0} GRNs Saved", [receipts.length]),
						message: links,
						indicator: "green",
					});

					frappe.set_route("Form", receipts[0].doctype, receipts[0].name);
				},
			});
		},
	});

	dialog.show();
	bind_grn_grid_events(dialog);
}

function get_grn_dialog_table_fields() {
	return [
		{
			fieldname: "po_item",
			fieldtype: "Data",
			hidden: 1,
		},
		{
			fieldname: "po_qty",
			fieldtype: "Float",
			hidden: 1,
		},
		{
			fieldname: "po_no_of_unit",
			fieldtype: "Float",
			hidden: 1,
		},
		{
			fieldname: "received_grn_qty",
			fieldtype: "Float",
			hidden: 1,
		},
		{
			fieldname: "draft_grn_qty",
			fieldtype: "Float",
			hidden: 1,
		},
		{
			fieldname: "grn_qty",
			fieldtype: "Float",
			hidden: 1,
		},
		{
			fieldname: "uom",
			fieldtype: "Link",
			options: "UOM",
			hidden: 1,
		},
		{
			fieldname: "item_code",
			fieldtype: "Link",
			options: "Item",
			label: __("Item Code"),
			read_only: 1,
			in_list_view: 1,
			columns: 2,
		},
		{
			fieldname: "custom_packing_qty",
			fieldtype: "Float",
			label: __("Packing Qty"),
			read_only: 1,
			in_list_view: 1,
		},
		{
			fieldname: "custom_total_qty",
			fieldtype: "Float",
			label: __("No of Unit"),
			in_list_view: 1,
		},
		{
			fieldname: "qty",
			fieldtype: "Float",
			label: __("Total Qty"),
			read_only: 1,
			in_list_view: 1,
		},
		{
			fieldname: "balance_no_of_unit",
			fieldtype: "Float",
			label: __("Balance No of Unit"),
			read_only: 1,
			in_list_view: 1,
		},
		{
			fieldname: "balance_grn_qty",
			fieldtype: "Float",
			label: __("Balance GRN Qty"),
			read_only: 1,
			in_list_view: 1,
		},
	];
}

function prepare_grn_dialog_row(row) {
	const prepared = { ...row };
	prepared.po_qty = flt(prepared.po_qty);
	prepared.po_no_of_unit = flt(prepared.po_no_of_unit);
	prepared.custom_packing_qty = flt(prepared.custom_packing_qty) || 1;
	prepared.received_grn_qty = flt(prepared.received_grn_qty);
	prepared.draft_grn_qty = flt(prepared.draft_grn_qty);
	recalculate_grn_row(prepared);
	return prepared;
}

function recalculate_grn_row(row) {
	const packing = flt(row.custom_packing_qty) || 1;
	const po_units = flt(row.po_no_of_unit);
	const received_units = row.received_grn_qty / packing;
	const draft_units = row.draft_grn_qty / packing;

	row.balance_no_of_unit = Math.max(po_units - received_units - draft_units, 0);
	row.balance_grn_qty = row.balance_no_of_unit * packing;

	// Total Qty = Packing Qty × No of Unit (for this GRN)
	row.qty = packing * flt(row.custom_total_qty);
	row.grn_qty = row.qty;
	row.pending_grn_qty = row.balance_grn_qty;

	if (flt(row.custom_total_qty) > row.balance_no_of_unit) {
		row.custom_total_qty = row.balance_no_of_unit;
		row.qty = packing * row.custom_total_qty;
		row.grn_qty = row.qty;
	}
}

function bind_grn_grid_events(dialog) {
	const grid = dialog.fields_dict.items?.grid;
	if (!grid) {
		return;
	}

	const refresh_row_fields = (grid_row) => {
		grid_row.refresh_field("qty");
		grid_row.refresh_field("balance_no_of_unit");
		grid_row.refresh_field("balance_grn_qty");
	};

	grid.wrapper.on(
		"change",
		'input[data-fieldname="custom_total_qty"]',
		function () {
			const row_name = $(this).closest(".grid-row").attr("data-name");
			const grid_row = grid.grid_rows_by_docname[row_name];
			if (!grid_row) {
				return;
			}
			recalculate_grn_row(grid_row.doc);
			refresh_row_fields(grid_row);
		}
	);
}
