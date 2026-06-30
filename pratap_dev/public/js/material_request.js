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

		if (frm.doc.docstatus === 0) {
			const sf_btn = frm.add_custom_button(__("Sales Forecast"), () => {
				open_sales_forecast_dialog(frm);
			});
			$(sf_btn).css({ "background-color": "black", color: "white" });
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

// ---------------------------------------------------------------------------
// Sales Forecast (Forecast Club) picker — mirrors the Work Order button dialog.
// Lists Forecast Clubs with their material request items; selected items are
// inserted into the Material Request (qty set, not added).
// ---------------------------------------------------------------------------

function open_sales_forecast_dialog(frm) {
	frappe.call({
		method: "pratap_dev.material_request_forecast.get_forecast_clubs_for_material_request",
		freeze: true,
		freeze_message: __("Loading Sales Forecast..."),
		callback(r) {
			const data = r.message || [];
			if (!data.length) {
				frappe.msgprint(__("No Sales Forecast items found."));
				return;
			}
			show_sales_forecast_dialog(frm, data);
		},
	});
}

function show_sales_forecast_dialog(frm, data) {
	const existing_fcs = [];
	(frm.doc.items || []).forEach((row) => {
		if (row.custom_forecast_club && !existing_fcs.includes(row.custom_forecast_club)) {
			existing_fcs.push(row.custom_forecast_club);
		}
	});

	let html = `
<style>
.sf-card { border: 1px solid #e0e0e0; border-radius: 10px; padding: 12px; margin-bottom: 12px; background: #fff; transition: all 0.2s ease; }
.sf-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
.sf-header { display: flex; align-items: center; gap: 10px; padding: 8px; border-radius: 6px; font-weight: 600; }
.sf-selected { background: #e6f4ea; border: 1px solid #28a745; }
.sf-title { font-size: 14px; }
.sf-plant { font-size: 11px; font-weight: 600; color: #1d6fc0; background: #e8f1fc; padding: 3px 10px; border-radius: 10px; margin-left: auto; }
.sf-status { font-size: 11px; font-weight: 600; color: #6c757d; margin-left: 10px; }
.sf-table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 13px; }
.sf-table th { background: #f7f7f7; padding: 8px; text-align: left; border-bottom: 1px solid #ddd; }
.sf-table td { padding: 8px; border-bottom: 1px solid #eee; }
.sf-qty-badge { background: #f1f3f5; padding: 3px 8px; border-radius: 6px; font-weight: 500; }
</style>
`;

	data.forEach((d) => {
		const isSelected = existing_fcs.includes(d.forecast_club);
		html += `
		<div class="sf-card">
			<div class="sf-header ${isSelected ? "sf-selected" : ""}">
				<input type="checkbox" class="sf-checkbox" data-fc="${frappe.utils.escape_html(
					d.forecast_club
				)}" ${isSelected ? "checked disabled" : ""}>
				<span class="sf-title">${frappe.utils.escape_html(d.forecast_club)}</span>
				${d.plant ? `<span class="sf-plant">${frappe.utils.escape_html(d.plant)}</span>` : `<span class="sf-plant" style="background:#f1f3f5;color:#6c757d;">${__("No Plant")}</span>`}
				${d.status ? `<span class="sf-status">${frappe.utils.escape_html(d.status)}</span>` : ""}
			</div>
			<table class="sf-table">
				<thead>
					<tr>
						<th style="width:20%">${__("Item Code")}</th>
						<th style="width:60%">${__("Item Name")}</th>
						<th style="width:20%">${__("MR Qty")}</th>
					</tr>
				</thead>
				<tbody>`;

		if (d.items && d.items.length) {
			d.items.forEach((i) => {
				html += `
					<tr>
						<td>${frappe.utils.escape_html(i.item_code)}</td>
						<td>${frappe.utils.escape_html(i.item_name || "")}</td>
						<td><span class="sf-qty-badge">${i.qty}</span></td>
					</tr>`;
			});
		} else {
			html += `<tr><td colspan="3" style="text-align:center; color:#999;">${__(
				"No Items"
			)}</td></tr>`;
		}

		html += `</tbody></table></div>`;
	});

	const dialog = new frappe.ui.Dialog({
		title: __("Select Items from Sales Forecast"),
		size: "large",
		fields: [{ fieldtype: "HTML", fieldname: "html" }],
		primary_action_label: __("Insert into MR"),
		primary_action() {
			const selected_fcs = [];
			dialog.$wrapper.find(".sf-checkbox:checked").each(function () {
				selected_fcs.push($(this).data("fc"));
			});

			if (!selected_fcs.length) {
				frappe.msgprint(__("Select at least one Sales Forecast"));
				return;
			}

			const item_qty_map = {};
			const item_fc_map = {};

			data.forEach((d) => {
				if (!selected_fcs.includes(d.forecast_club)) {
					return;
				}
				(d.items || []).forEach((i) => {
					item_qty_map[i.item_code] = (item_qty_map[i.item_code] || 0) + (i.qty || 0);
					if (!item_fc_map[i.item_code]) {
						item_fc_map[i.item_code] = d.forecast_club;
					}
				});
			});

			Object.keys(item_qty_map).forEach((item_code) => {
				const total_qty = item_qty_map[item_code];
				const forecast_club = item_fc_map[item_code];
				const existing = frm.doc.items.find((row) => row.item_code === item_code);

				if (existing) {
					frappe.model.set_value(existing.doctype, existing.name, "qty", total_qty);
					if (!existing.custom_forecast_club) {
						frappe.model.set_value(
							existing.doctype,
							existing.name,
							"custom_forecast_club",
							forecast_club
						);
					}
					return;
				}

				const empty_row = frm.doc.items.find((row) => !row.item_code);
				const row = empty_row || frm.add_child("items");

				frappe.model.set_value(row.doctype, row.name, "item_code", item_code);
				frappe.model.set_value(row.doctype, row.name, "qty", total_qty);
				frappe.model.set_value(row.doctype, row.name, "custom_forecast_club", forecast_club);

				if (frm.doc.set_warehouse) {
					frappe.model.set_value(row.doctype, row.name, "warehouse", frm.doc.set_warehouse);
				}
				if (frm.doc.schedule_date) {
					frappe.model.set_value(row.doctype, row.name, "schedule_date", frm.doc.schedule_date);
				}
			});

			frm.refresh_field("items");
			frappe.msgprint(__("Items inserted Successfully"));
			dialog.hide();
		},
	});

	dialog.fields_dict.html.$wrapper.html(html);
	dialog.show();
}
