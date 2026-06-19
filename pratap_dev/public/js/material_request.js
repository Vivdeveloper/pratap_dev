frappe.ui.form.on("Material Request", {
	refresh(frm) {
		frm.remove_custom_button(__("Purchase Order"), __("Create"));

		frm.add_fetch(
			"custom_supplier_",
			"supplier_name",
			"custom_supplier_name",
			"Material Request Item"
		);

		frm.set_query("custom_supplier_", "items", function (doc, cdt, cdn) {
			const row = locals[cdt][cdn];
			return {
				query: "auto_po_creation.api.supplier_link_query",
				filters: { item_code: row.item_code || "" },
			};
		});

		if (!frm.doc.__islocal && frm.doc.docstatus === 1 && frm.doc.material_request_type === "Purchase") {
			frm.add_custom_button(__("Supplier Quotation"), () => {
				open_supplier_quotation_dialog(frm);
			});
		}
	},
});

frappe.ui.form.on("Material Request Item", {
	item_code(frm, cdt, cdn) {
		set_rm_warehouse_qty(frm, cdt, cdn);
		set_supplier_if_single_vendor(frm, cdt, cdn);
	},
	custom_packing_qty(frm, cdt, cdn) {
		calculate_quantity(frm, cdt, cdn);
	},
	custom_total_qty(frm, cdt, cdn) {
		calculate_quantity(frm, cdt, cdn);
	},
	custom_supplier_(frm, cdt, cdn) {
		set_supplier_name(frm, cdt, cdn);
	},
});

function calculate_quantity(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const quantity = (row.custom_packing_qty || 0) * (row.custom_total_qty || 0);
	frappe.model.set_value(cdt, cdn, "qty", quantity);
}

function set_supplier_if_single_vendor(frm, cdt, cdn) {
	if (frm.doc.docstatus !== 0 || frm.doc.material_request_type !== "Purchase") {
		return;
	}

	const row = locals[cdt][cdn];
	if (!row?.item_code) {
		return;
	}

	frappe.call({
		method: "auto_po_creation.api.get_item_suppliers",
		args: { item_code: row.item_code },
		callback(r) {
			const suppliers = r.message || [];
			if (suppliers.length !== 1) {
				return;
			}

			const supplier = suppliers[0].supplier;
			const supplier_name = suppliers[0].supplier_name;

			if (row.custom_supplier_ === supplier && row.custom_supplier_name) {
				return;
			}

			if (supplier_name) {
				frappe.model.set_value(cdt, cdn, {
					custom_supplier_: supplier,
					custom_supplier_name: supplier_name,
				});
				return;
			}

			frappe.model.set_value(cdt, cdn, "custom_supplier_", supplier);
		},
	});
}

function set_supplier_name(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row?.custom_supplier_) {
		if (row.custom_supplier_name) {
			frappe.model.set_value(cdt, cdn, "custom_supplier_name", "");
		}
		return;
	}

	frappe.db.get_value("Supplier", row.custom_supplier_, "supplier_name", (values) => {
		const supplier_name = values?.supplier_name;
		if (!supplier_name || row.custom_supplier_name === supplier_name) {
			return;
		}
		frappe.model.set_value(cdt, cdn, "custom_supplier_name", supplier_name);
	});
}

function set_rm_qty_field(cdt, cdn, fieldname, value) {
	const row = locals[cdt][cdn];
	const next_value = flt(value);

	if (flt(row[fieldname]) === next_value) {
		return;
	}

	frappe.model.set_value(cdt, cdn, fieldname, next_value, null, true);
}

function set_rm_warehouse_qty(frm, cdt, cdn) {
	if (frm.doc.docstatus !== 0) {
		return;
	}

	const row = locals[cdt][cdn];
	if (!row.item_code || !frm.doc.company) {
		set_rm_qty_field(cdt, cdn, "custom_wip_rm_qty", 0);
		set_rm_qty_field(cdt, cdn, "custom_main_store_rm_qty", 0);
		return;
	}

	Promise.all([
		frappe.db.get_value("Warehouse", { warehouse_name: "WIP RM", company: frm.doc.company }, "name"),
		frappe.db.get_value(
			"Warehouse",
			{ warehouse_name: "Main Store RM", company: frm.doc.company },
			"name"
		),
	])
		.then(([wip_warehouse, main_store_warehouse]) => {
			const wip_wh = wip_warehouse?.message?.name;
			const main_wh = main_store_warehouse?.message?.name;

			return Promise.all([
				wip_wh
					? frappe
							.xcall("erpnext.stock.utils.get_latest_stock_qty", {
								item_code: row.item_code,
								warehouse: wip_wh,
							})
							.then((qty) => flt(qty))
					: Promise.resolve(0),
				main_wh
					? frappe
							.xcall("erpnext.stock.utils.get_latest_stock_qty", {
								item_code: row.item_code,
								warehouse: main_wh,
							})
							.then((qty) => flt(qty))
					: Promise.resolve(0),
			]);
		})
		.then(([wip_qty, main_qty]) => {
			set_rm_qty_field(cdt, cdn, "custom_wip_rm_qty", wip_qty);
			set_rm_qty_field(cdt, cdn, "custom_main_store_rm_qty", main_qty);
		})
		.catch(() => {
			set_rm_qty_field(cdt, cdn, "custom_wip_rm_qty", 0);
			set_rm_qty_field(cdt, cdn, "custom_main_store_rm_qty", 0);
		});
}

function fetch_supplier_name_map(suppliers) {
	if (!suppliers.length) {
		return Promise.resolve({});
	}

	return frappe
		.call({
			method: "auto_po_creation.api.get_supplier_name_map",
			args: { suppliers },
		})
		.then((r) => r.message || {});
}

function set_dialog_supplier_name(row, grid) {
	if (!row) {
		return Promise.resolve();
	}

	if (!row.supplier) {
		row.supplier_name = "";
		grid?.set_value("supplier_name", "", row);
		return Promise.resolve();
	}

	return frappe.db.get_value("Supplier", row.supplier, "supplier_name").then((r) => {
		const supplier_name = r?.message?.supplier_name || "";
		row.supplier_name = supplier_name;
		grid?.set_value("supplier_name", supplier_name, row);
	});
}

function apply_supplier_names_to_table_data(table_data, name_map) {
	table_data.forEach((row) => {
		if (!row.supplier_name && row.supplier) {
			row.supplier_name = name_map[row.supplier] || "";
		}
	});
}

function open_supplier_quotation_dialog(frm) {
	frappe.call({
		method: "auto_po_creation.api.get_sq_status",
		args: { material_request: frm.doc.name },
		callback(r) {
			const sq_items = r.message || [];
			const table_data = [];

			(frm.doc.items || []).forEach((row) => {
				const supplier =
					row.custom_supplier_ ||
					row.supplier ||
					row.supplier_code ||
					row.default_supplier;
				const sq_created = sq_items.includes(row.item_code);

				table_data.push({
					sq_created: sq_created ? 1 : 0,
					_sq_created: sq_created,
					item_code: row.item_code,
					item_name: row.item_name,
					qty: row.qty,
					supplier: supplier || "",
					supplier_name: row.custom_supplier_name || "",
				});
			});

			if (!table_data.length) {
				frappe.msgprint(__("No items found on this Material Request."));
				return;
			}

			const suppliers = [...new Set(table_data.map((row) => row.supplier).filter(Boolean))];

			fetch_supplier_name_map(suppliers).then((name_map) => {
				apply_supplier_names_to_table_data(table_data, name_map);
				show_sq_selection_dialog(frm, table_data);
			});
		},
	});
}

function show_sq_selection_dialog(frm, table_data) {
	const dialog = new frappe.ui.Dialog({
		title: __("Select Items for Supplier Quotation"),
		size: "extra-large",
		fields: [
			{
				fieldname: "items",
				fieldtype: "Table",
				label: __("Items"),
				cannot_add_rows: true,
				cannot_delete_rows: true,
				in_place_edit: true,
				fields: [
					{
						fieldname: "sq_created",
						fieldtype: "Check",
						label: __("SQ Created"),
						in_list_view: 1,
						read_only: 1,
					},
					{
						fieldname: "item_code",
						fieldtype: "Data",
						label: __("Item Code"),
						in_list_view: 1,
						read_only: 1,
					},
					{
						fieldname: "item_name",
						fieldtype: "Data",
						label: __("Item Name"),
						in_list_view: 1,
						read_only: 1,
					},
					{
						fieldname: "qty",
						fieldtype: "Float",
						label: __("Qty"),
						in_list_view: 1,
					},
					{
						fieldname: "supplier",
						fieldtype: "Link",
						options: "Supplier",
						label: __("Supplier Code"),
						in_list_view: 1,
					},
					{
						fieldname: "supplier_name",
						fieldtype: "Data",
						label: __("Supplier Name"),
						fetch_from: "supplier.supplier_name",
						in_list_view: 1,
						read_only: 1,
					},
				],
			},
		],
		primary_action_label: __("Create Supplier Quotation"),
		primary_action() {
			const selected_items = dialog.fields_dict.items.grid
				.get_selected_children()
				.filter((row) => !row._sq_created);

			if (!selected_items.length) {
				frappe.msgprint(__("Please select items without existing Supplier Quotation."));
				return;
			}

			const missing_supplier = selected_items.filter((row) => !row.supplier);
			if (missing_supplier.length) {
				frappe.msgprint({
					title: __("Supplier Missing"),
					indicator: "red",
					message: `
						Supplier not selected for:<br>
						<b>${missing_supplier.map((row) => row.item_code).join(", ")}</b>
					`,
				});
				return;
			}

			const payload = selected_items.map((row) => ({
				item_code: row.item_code,
				qty: row.qty,
				supplier: row.supplier,
			}));

			frappe.call({
				method: "auto_po_creation.api.create_supplier_quotations",
				args: {
					material_request: frm.doc.name,
					items: JSON.stringify(payload),
				},
				freeze: true,
				freeze_message: __("Creating Supplier Quotations..."),
				callback(res) {
					if (!res.message) {
						return;
					}

					let msg = "";

					if (res.message.created?.length) {
						msg += `<b>${__("Supplier Quotations Created")}:</b><br><br>`;
						res.message.created.forEach((sq) => {
							msg += `
								<b>${__("Supplier Quotation")}:</b>
								<a href="/app/supplier-quotation/${sq.name}" target="_blank">
									${sq.name}
								</a>
								(${sq.supplier})<br>
								<b>${__("Items")}:</b> ${sq.items.join(", ")}<br><br>
							`;
						});
					}

					if (res.message.existing?.length) {
						msg += `<b>${__("Already Created")}:</b><br><br>`;
						res.message.existing.forEach((sq) => {
							msg += `
								<b>${__("Supplier Quotation")}:</b>
								<a href="/app/supplier-quotation/${sq.sq_name}" target="_blank">
									${sq.sq_name}
								</a>
								(${sq.supplier})<br><br>
							`;
						});
					}

					if (!msg) {
						msg = __("No Supplier Quotations were created.");
					}

					frappe.msgprint({
						title: __("Supplier Quotation Creation Summary"),
						indicator: res.message.created?.length ? "green" : "orange",
						message: msg,
					});

					dialog.hide();
					frm.reload_doc();
				},
			});
		},
		on_page_show() {
			const grid = dialog.fields_dict.items.grid;
			grid.df.data = table_data;
			grid.refresh();

			const supplier_field = grid.get_field("supplier");
			if (supplier_field) {
				supplier_field.get_query = (doc) => ({
					query: "auto_po_creation.api.supplier_link_query",
					filters: { item_code: doc.item_code || "" },
				});
			}

			setTimeout(() => {
				grid.grid_rows.forEach((grid_row) => {
					const supplier_name = grid_row.doc.supplier_name;
					if (supplier_name) {
						grid.set_value("supplier_name", supplier_name, grid_row.doc);
					}
				});

				grid.grid_rows.forEach((row) => {
					if (row.doc._sq_created && row.$checkbox) {
						row.$checkbox.prop("disabled", true);
						row.$row.addClass("text-muted");
					}
				});
			}, 100);
		},
	});

	dialog.$wrapper.on("change", 'input[data-fieldname="supplier"]', function () {
		const $row = $(this).closest(".grid-row");
		if (!$row.length) {
			return;
		}

		const docname = $row.attr("data-name");
		const grid = dialog.fields_dict.items.grid;
		const row = grid.grid_rows_by_docname[docname]?.doc;
		if (!row) {
			return;
		}

		set_dialog_supplier_name(row, grid);
	});

	dialog.show();
}
