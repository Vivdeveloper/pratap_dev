const MR_DEFAULT_SOURCE_WAREHOUSE = "Plant 1 WIP FG - PTPL";

frappe.ui.form.on("Material Request", {
	onload(frm) {
		// Default the Set Source Warehouse to Plant 1 WIP FG on new Material Requests.
		// if (frm.is_new() && !frm.doc.set_from_warehouse) {
		// 	frm.set_value("set_from_warehouse", MR_DEFAULT_SOURCE_WAREHOUSE);
		// }
	},

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
			frm.add_custom_button(__("Request for Quotation"), () => {
				open_rfq_dialog(frm);
			});
		}

		if (frm.doc.docstatus === 0) {
			const sf_btn = frm.add_custom_button(__("Sales Forecast"), () => {
				open_sales_forecast_dialog(frm);
			});
			$(sf_btn).css({ "background-color": "black", color: "white" });
		}

		// ERPNext adds its own Create > Work Order; ours is the picker below.
		setTimeout(() => frm.remove_custom_button(__("Work Order"), __("Create")), 200);

		const wo_btn = frm.add_custom_button(__("Work Order"), () => {
			open_work_order_dialog(frm);
		});
		$(wo_btn).css({ "background-color": "black", color: "white" });

		// Keep the warehouse stock columns filled on drafts too, so they are
		// visible before the Material Request is ever saved.
		populate_rm_stock_all(frm);

		setup_reject_button(frm);
	},

	company(frm) {
		populate_rm_stock_all(frm);
	},
});

function populate_rm_stock_all(frm) {
	if (frm.doc.docstatus !== 0) {
		return;
	}
	(frm.doc.items || []).forEach((row) => set_rm_warehouse_qty(frm, row.doctype, row.name));
}

// "Reject" lets the current approver peel selected items off this Material
// Request into a brand-new one. It appears both at the top (form toolbar) and at
// the bottom (next to the grid's Delete button) — but ONLY when this user is at
// the workflow decision point where Approve/Reject is available to them.
// "Reject" lets the current approver peel selected item rows off this Material
// Request into a brand-new one. It shows both at the top (form toolbar) and at
// the bottom (next to the grid's Delete button) — but ONLY when this user is at
// the workflow decision point where Approve/Reject is available to them.
function setup_reject_button(frm) {
	const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
	if (!grid) {
		return;
	}

	// Reset on every refresh: the bottom grid button persists on the grid object,
	// so hide it and drop the top button until we re-confirm this user may reject.
	frm._mr_can_reject = false;
	frm.remove_custom_button(__("Reject"));
	const hide_bottom = () => {
		const $btn = grid.custom_buttons[__("Reject")];
		if ($btn) {
			$btn.addClass("hidden");
		}
	};
	hide_bottom();

	// Bottom button tracks row selection, but only when rejecting is allowed.
	const toggle_bottom = () => {
		const $btn = grid.custom_buttons[__("Reject")];
		if (!$btn) {
			return;
		}
		const any = grid.wrapper.find(".grid-body .grid-row-check:checked:first").length > 0;
		$btn.toggleClass("hidden", !(frm._mr_can_reject && any));
	};
	grid.wrapper.off("click.mrreject").on("click.mrreject", ".grid-row-check", () => {
		setTimeout(toggle_bottom, 50);
	});

	if (frm.is_new() || frm.doc.docstatus !== 0) {
		return;
	}

	// Only wire up the buttons if a workflow "Reject" action is available to this
	// user on this document right now (i.e. the Approve/Reject decision point).
	frappe
		.xcall("frappe.model.workflow.get_transitions", { doc: frm.doc })
		.then((transitions) => {
			const can_reject = (transitions || []).some((t) =>
				(t.action || "").toLowerCase().includes("reject")
			);
			frm._mr_can_reject = can_reject;
			if (!can_reject) {
				hide_bottom();
				return;
			}

			// Bottom button (next to Delete).
			grid
				.add_custom_button(__("Reject"), () => reject_selected_items(frm, grid))
				.removeClass("btn-secondary")
				.addClass("btn-danger");
			toggle_bottom();

			// Top button (form toolbar).
			frm.add_custom_button(__("Reject"), () => reject_selected_items(frm, grid));
		})
		.catch(() => {});
}

function reject_selected_items(frm, grid) {
	const selected = grid.get_selected_children();
	if (!selected.length) {
		frappe.msgprint(__("Select at least one item to reject"));
		return;
	}
	if (frm.is_dirty()) {
		frappe.msgprint(__("Please save the document before rejecting items."));
		return;
	}
	if (selected.length >= (frm.doc.items || []).length) {
		frappe.msgprint(__("Cannot reject all items — at least one item must remain here."));
		return;
	}

	frappe.confirm(
		__("Move {0} selected item(s) to a new Material Request and remove them from here?", [
			selected.length,
		]),
		() => {
			frappe.call({
				method: "pratap_dev.material_request_reject.reject_items_to_new_mr",
				args: {
					source_name: frm.doc.name,
					item_rows: JSON.stringify(selected.map((d) => d.name)),
				},
				freeze: true,
				freeze_message: __("Rejecting items..."),
				callback(r) {
					if (!r.message) {
						return;
					}
					frm.reload_doc();
					const link = `<a href="/app/material-request/${r.message}">${frappe.utils.escape_html(
						r.message
					)}</a>`;
					frappe.msgprint({
						title: __("Items Rejected"),
						indicator: "green",
						message: __("New Material Request {0} created with the rejected items.", [link]),
					});
				},
			});
		}
	);
}

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
	custom_expected_qty(frm, cdt, cdn) {
		recompute_required_qty_for_pr(cdt, cdn);
	},
});

function calculate_quantity(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row) {
		return;
	}

	// Quantity = Standard Pkg Qty x No of Unit
	const quantity = flt(row.custom_packing_qty) * flt(row.custom_total_qty);
	frappe.model.set_value(cdt, cdn, "qty", quantity);

	// Nothing to split until a real quantity is entered (both pkg qty & no of unit).
	if (quantity <= 0) {
		return;
	}

	// Split against the Expected Quantity (from the Sales Forecast dialog).
	const expected = flt(row.custom_expected_qty);
	if (expected <= 0) {
		return;
	}

	if (quantity > expected) {
		// Over-filled: warn, but don't touch any remainder rows the user may be editing.
		frappe.show_alert(
			{
				message: __("Row {0} ({1}): Quantity {2} is more than Expected Quantity {3}.", [
					row.idx,
					row.item_code || "",
					format_number(quantity),
					format_number(expected),
				]),
				indicator: "orange",
			},
			7
		);
		return;
	}

	if (quantity < expected) {
		// Push the remaining quantity into a linked next row for the same item.
		ensure_expected_remainder_row(frm, row, expected - quantity);
	} else {
		// Exactly filled — no remainder row needed.
		remove_expected_child_chain(frm, row.name);
	}
}

// Copy everything the user filled on the parent row onto the freshly created
// remainder row, so it comes pre-filled (supplier, warehouse, dates, etc.). Only
// the split-quantity fields and system/identity fields are left out — the split
// quantities are re-entered on the new row, and identity fields must stay unique.
const MR_ITEM_NO_COPY_FIELDS = new Set([
	// Identity / system fields — never copy.
	"name",
	"idx",
	"docstatus",
	"parent",
	"parentfield",
	"parenttype",
	"doctype",
	"owner",
	"creation",
	"modified",
	"modified_by",
	// Split-quantity fields — entered fresh on the remainder row.
	"custom_packing_qty",
	"custom_total_qty",
	"qty",
	"stock_qty",
	"amount",
	"custom_expected_qty",
]);

function copy_mr_item_fields(src, dest) {
	Object.keys(src).forEach((f) => {
		if (f.startsWith("__") || MR_ITEM_NO_COPY_FIELDS.has(f)) {
			return;
		}
		const value = src[f];
		if (value === undefined || value === null || value === "") {
			return;
		}
		dest[f] = value;
	});
}

// Create or update the single "remainder" row linked to a parent row.
function ensure_expected_remainder_row(frm, parentRow, remaining) {
	frm._mr_expected_child = frm._mr_expected_child || {};
	const childName = frm._mr_expected_child[parentRow.name];
	let child = childName ? (frm.doc.items || []).find((r) => r.name === childName) : null;

	if (!child) {
		child = frm.add_child("items");
		copy_mr_item_fields(parentRow, child);
		frm._mr_expected_child[parentRow.name] = child.name;
		// New remainder row should sit right after its parent row, not at the
		// end of the table (frm.add_child appends at the end).
		insert_row_after_parent(frm, parentRow.name, child.name);
	}

	// The remainder becomes the new row's Expected Quantity (and its default qty);
	// the user can split it further via Standard Pkg Qty / No of Unit.
	frappe.model.set_value(child.doctype, child.name, "custom_expected_qty", remaining);
	frappe.model.set_value(child.doctype, child.name, "qty", remaining);
	frm.refresh_field("items");
}

// Move a freshly added child row so it sits immediately after its parent row,
// then renumber idx so the grid renders in the new order.
function insert_row_after_parent(frm, parentName, childName) {
	const items = frm.doc.items || [];
	const childIdx = items.findIndex((r) => r.name === childName);
	if (childIdx === -1) {
		return;
	}

	const [child] = items.splice(childIdx, 1);
	const parentIdx = items.findIndex((r) => r.name === parentName);
	if (parentIdx === -1) {
		items.push(child);
	} else {
		items.splice(parentIdx + 1, 0, child);
	}

	items.forEach((r, i) => (r.idx = i + 1));
	frm.refresh_field("items");
}

// Remove a parent's remainder row (and its own remainder chain).
function remove_expected_child_chain(frm, parentName) {
	frm._mr_expected_child = frm._mr_expected_child || {};
	const childName = frm._mr_expected_child[parentName];
	if (!childName) {
		return;
	}
	remove_expected_child_chain(frm, childName);

	if ((frm.doc.items || []).some((r) => r.name === childName)) {
		frm.doc.items = frm.doc.items.filter((r) => r.name !== childName);
		frm.doc.items.forEach((r, i) => (r.idx = i + 1));
		frm.refresh_field("items");
	}
	delete frm._mr_expected_child[parentName];
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

// Warehouses to show per item row: [warehouse_name prefix, target field].
const MR_STOCK_WAREHOUSES = [
	["Main Store RM", "custom_main_store_rm_qty"],
	["Plant 1 WIP RM", "custom_plant_1_wip_rm"],
	["Plant 2 WIP RM", "custom_plant_2_wip_rm"],
];

function set_rm_warehouse_qty(frm, cdt, cdn) {
	if (frm.doc.docstatus !== 0) {
		return;
	}

	const row = locals[cdt][cdn];
	if (!row || !row.item_code || !frm.doc.company) {
		MR_STOCK_WAREHOUSES.forEach(([, fieldname]) => set_rm_qty_field(cdt, cdn, fieldname, 0));
		set_rm_qty_field(cdt, cdn, "custom_total_stock_qty", 0);
		set_rm_qty_field(cdt, cdn, "custom_pending_pr_for_grn", 0);
		set_rm_qty_field(cdt, cdn, "custom_pending_grn_qc", 0);
		recompute_required_qty_for_pr(cdt, cdn);
		return;
	}

	Promise.all(
		MR_STOCK_WAREHOUSES.map(([warehouse_name, fieldname]) =>
			get_rm_warehouse_stock(row.item_code, warehouse_name, frm.doc.company).then((qty) => {
				set_rm_qty_field(cdt, cdn, fieldname, qty);
				return qty;
			})
		)
	).then((quantities) => {
		const total_stock_qty = quantities.reduce((sum, qty) => sum + flt(qty), 0);
		set_rm_qty_field(cdt, cdn, "custom_total_stock_qty", total_stock_qty);
		recompute_required_qty_for_pr(cdt, cdn);
	});

	set_material_pipeline_status(frm, cdt, cdn);
}

// "Pending PR for GRN" / "Pending for GRN Approved (QC Pending)" come from open
// Purchase Orders company-wide for this item, not from this Material Request
// alone — see pratap_dev.material_request_stock.get_item_pipeline_status.
function set_material_pipeline_status(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row || !row.item_code || !frm.doc.company) {
		return;
	}

	frappe
		.xcall("pratap_dev.material_request_stock.get_item_pipeline_status", {
			item_code: row.item_code,
			company: frm.doc.company,
		})
		.then((data) => {
			set_rm_qty_field(cdt, cdn, "custom_pending_pr_for_grn", data?.pending_pr_for_grn || 0);
			set_rm_qty_field(cdt, cdn, "custom_pending_grn_qc", data?.pending_grn_qc || 0);
			recompute_required_qty_for_pr(cdt, cdn);
		})
		.catch(() => {});
}

// Required Qty for PR = Forecast Qty - Total Qty - Pending PR for GRN - Pending GRN QC.
function recompute_required_qty_for_pr(cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row) {
		return;
	}

	const required = Math.max(
		flt(row.custom_expected_qty) -
			flt(row.custom_total_stock_qty) -
			flt(row.custom_pending_pr_for_grn) -
			flt(row.custom_pending_grn_qc),
		0
	);
	set_rm_qty_field(cdt, cdn, "custom_required_qty_for_pr", required);
}

// Warehouse names may carry a trailing space (e.g. "Plant 1 WIP RM "), so match by prefix.
function get_rm_warehouse_stock(item_code, warehouse_name, company) {
	return frappe.db
		.get_list("Warehouse", {
			filters: { warehouse_name: ["like", `${warehouse_name}%`], company: company },
			fields: ["name"],
			limit: 1,
		})
		.then((rows) => {
			const warehouse = rows && rows.length ? rows[0].name : null;
			if (!warehouse) {
				return 0;
			}
			return frappe
				.xcall("erpnext.stock.utils.get_latest_stock_qty", { item_code, warehouse })
				.then((qty) => flt(qty));
		})
		.catch(() => 0);
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
					material_request_item: row.name,
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
				material_request_item: row.material_request_item,
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
			fetch_forecast_stock_map(frm, data).then((stock_map) => {
				show_sales_forecast_dialog(frm, data, stock_map);
			});
		},
	});
}

// Stock columns are only meaningful when we are buying, so skip the lookup for
// other purposes and render the dialog without them.
function fetch_forecast_stock_map(frm, data) {
	if (frm.doc.material_request_type !== "Purchase" || !frm.doc.company) {
		return Promise.resolve(null);
	}

	const item_codes = [];
	data.forEach((d) => {
		(d.items || []).forEach((i) => {
			if (i.item_code && !item_codes.includes(i.item_code)) {
				item_codes.push(i.item_code);
			}
		});
	});

	if (!item_codes.length) {
		return Promise.resolve(null);
	}

	// Warehouse names may carry a trailing space, so resolve each one by prefix.
	return Promise.all(
		MR_STOCK_WAREHOUSES.map(([warehouse_name]) =>
			frappe.db
				.get_list("Warehouse", {
					filters: {
						warehouse_name: ["like", `${warehouse_name}%`],
						company: frm.doc.company,
					},
					fields: ["name"],
					limit: 1,
				})
				.then((rows) => (rows && rows.length ? rows[0].name : null))
		)
	)
		.then((warehouses) => {
			const known = warehouses.filter(Boolean);
			if (!known.length) {
				return null;
			}
			return frappe.db
				.get_list("Bin", {
					filters: { item_code: ["in", item_codes], warehouse: ["in", known] },
					fields: ["item_code", "warehouse", "actual_qty"],
					limit: 0,
				})
				.then((bins) => {
					const by_warehouse = {};
					(bins || []).forEach((bin) => {
						by_warehouse[bin.warehouse] = by_warehouse[bin.warehouse] || {};
						by_warehouse[bin.warehouse][bin.item_code] = flt(bin.actual_qty);
					});
					// Column order mirrors MR_STOCK_WAREHOUSES; null warehouse => blank column.
					return MR_STOCK_WAREHOUSES.map(([label], idx) => ({
						label,
						qty_by_item: by_warehouse[warehouses[idx]] || {},
					}));
				});
		})
		.catch(() => null);
}

function show_sales_forecast_dialog(frm, data, stock_map) {
	const existing_fcs = [];
	(frm.doc.items || []).forEach((row) => {
		if (row.custom_forecast_club && !existing_fcs.includes(row.custom_forecast_club)) {
			existing_fcs.push(row.custom_forecast_club);
		}
	});

	const stock_cols = stock_map || [];

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
.sf-stock-badge { background: #e8f1fc; color: #1d6fc0; padding: 3px 8px; border-radius: 6px; font-weight: 500; }
.sf-select-all { display: flex; align-items: center; gap: 8px; padding: 8px 4px; margin-bottom: 8px; font-weight: 600; font-size: 13px; }
</style>
<label class="sf-select-all"><input type="checkbox" class="sf-select-all-box"> ${__("Select All")}</label>
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
						<th style="width:${stock_cols.length ? "16%" : "20%"}">${__("Item Code")}</th>
						<th style="width:${stock_cols.length ? "32%" : "60%"}">${__("Item Name")}</th>
						<th style="width:${stock_cols.length ? "13%" : "20%"}">${__("Expected Qty")}</th>
						${stock_cols
							.map((col) => `<th style="width:13%">${__(col.label)}</th>`)
							.join("")}
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
						${stock_cols
							.map(
								(col) =>
									`<td><span class="sf-stock-badge">${format_number(
										flt(col.qty_by_item[i.item_code])
									)}</span></td>`
							)
							.join("")}
					</tr>`;
			});
		} else {
			html += `<tr><td colspan="${3 + stock_cols.length}" style="text-align:center; color:#999;">${__(
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
					// Expected Quantity = what came from the Sales Forecast dialog.
					frappe.model.set_value(existing.doctype, existing.name, "custom_expected_qty", total_qty);
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
				frappe.model.set_value(row.doctype, row.name, "custom_expected_qty", total_qty);
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

	// "Select All" drives only the enabled boxes — already-inserted forecasts stay
	// checked-and-disabled either way.
	const $wrapper = dialog.fields_dict.html.$wrapper;
	const $all = $wrapper.find(".sf-select-all-box");
	$all.on("change", function () {
		$wrapper.find(".sf-checkbox:not(:disabled)").prop("checked", this.checked);
	});
	$wrapper.on("change", ".sf-checkbox", () => {
		const $boxes = $wrapper.find(".sf-checkbox:not(:disabled)");
		$all.prop("checked", $boxes.length > 0 && $boxes.length === $boxes.filter(":checked").length);
	});

	dialog.show();
}

// ---------------------------------------------------------------------------
// Work Order picker — ported from the "Work Order Button" Client Script so it
// lives with the rest of the Material Request code. Lists Work Orders with
// their required items; selected items are inserted into the Material Request
// (qty set, not added) and the source Work Orders are recorded on the row.
// ---------------------------------------------------------------------------

function open_work_order_dialog(frm) {
	frappe.call({
		method: "create_work_order",
		freeze: true,
		freeze_message: __("Loading Work Orders..."),
		callback(r) {
			const data = r.message || [];
			if (!data.length) {
				frappe.msgprint(__("No Work Orders found"));
				return;
			}
			show_work_order_dialog(frm, data);
		},
	});
}

function show_work_order_dialog(frm, data) {
	const existing_wos = [];
	(frm.doc.items || []).forEach((row) => {
		(row.custom_work_order_connection || "").split(", ").forEach((wo) => {
			if (wo && !existing_wos.includes(wo)) {
				existing_wos.push(wo);
			}
		});
	});

	let html = `
<style>
.wo-card { border: 1px solid #e0e0e0; border-radius: 10px; padding: 12px; margin-bottom: 12px; background: #fff; transition: all 0.2s ease; }
.wo-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
.wo-header { display: flex; align-items: center; gap: 10px; padding: 8px; border-radius: 6px; font-weight: 600; }
.wo-selected { background: #e6f4ea; border: 1px solid #28a745; }
.wo-title { font-size: 14px; }
.wo-table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 13px; }
.wo-table th { background: #f7f7f7; padding: 8px; text-align: left; border-bottom: 1px solid #ddd; }
.wo-table td { padding: 8px; border-bottom: 1px solid #eee; }
.wo-qty-badge { background: #f1f3f5; padding: 3px 8px; border-radius: 6px; font-weight: 500; }
.wo-select-all { display: flex; align-items: center; gap: 8px; padding: 8px 4px; margin-bottom: 8px; font-weight: 600; font-size: 13px; }
</style>
<label class="wo-select-all"><input type="checkbox" class="wo-select-all-box"> ${__("Select All")}</label>
`;

	data.forEach((d) => {
		const isSelected = existing_wos.includes(d.work_order);
		html += `
		<div class="wo-card">
			<div class="wo-header ${isSelected ? "wo-selected" : ""}">
				<input type="checkbox" class="wo-checkbox" data-wo="${frappe.utils.escape_html(
					d.work_order
				)}" ${isSelected ? "checked disabled" : ""}>
				<span class="wo-title">${frappe.utils.escape_html(d.work_order)}</span>
			</div>
			<table class="wo-table">
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
						<td><span class="wo-qty-badge">${i.qty}</span></td>
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
		title: __("Select Items from Work Orders"),
		size: "large",
		fields: [{ fieldtype: "HTML", fieldname: "html" }],
		primary_action_label: __("Insert into MR"),
		primary_action() {
			const selected_wos = [];
			dialog.$wrapper.find(".wo-checkbox:checked").each(function () {
				selected_wos.push($(this).data("wo"));
			});

			if (!selected_wos.length) {
				frappe.msgprint(__("Select at least one Work Order"));
				return;
			}

			const item_qty_map = {};
			const item_wo_map = {};

			data.forEach((d) => {
				if (!selected_wos.includes(d.work_order)) {
					return;
				}
				(d.items || []).forEach((i) => {
					item_qty_map[i.item_code] = (item_qty_map[i.item_code] || 0) + (i.qty || 0);
					item_wo_map[i.item_code] = item_wo_map[i.item_code] || [];
					if (!item_wo_map[i.item_code].includes(d.work_order)) {
						item_wo_map[i.item_code].push(d.work_order);
					}
				});
			});

			Object.keys(item_qty_map).forEach((item_code) => {
				const total_qty = item_qty_map[item_code];
				const wo_list = item_wo_map[item_code] || [];
				const existing = frm.doc.items.find((row) => row.item_code === item_code);

				if (existing) {
					frappe.model.set_value(existing.doctype, existing.name, "qty", total_qty);

					const existing_list = (existing.custom_work_order_connection || "")
						.split(", ")
						.filter(Boolean);
					wo_list.forEach((wo) => {
						if (!existing_list.includes(wo)) {
							existing_list.push(wo);
						}
					});
					frappe.model.set_value(
						existing.doctype,
						existing.name,
						"custom_work_order_connection",
						existing_list.join(", ")
					);
					return;
				}

				const empty_row = frm.doc.items.find((row) => !row.item_code);
				const row = empty_row || frm.add_child("items");

				frappe.model.set_value(row.doctype, row.name, "item_code", item_code);
				frappe.model.set_value(row.doctype, row.name, "qty", total_qty);
				frappe.model.set_value(
					row.doctype,
					row.name,
					"custom_work_order_connection",
					wo_list.join(", ")
				);

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

	// "Select All" drives only the enabled boxes — Work Orders already linked to
	// this Material Request stay checked-and-disabled either way.
	const $wrapper = dialog.fields_dict.html.$wrapper;
	const $all = $wrapper.find(".wo-select-all-box");
	$all.on("change", function () {
		$wrapper.find(".wo-checkbox:not(:disabled)").prop("checked", this.checked);
	});
	$wrapper.on("change", ".wo-checkbox", () => {
		const $boxes = $wrapper.find(".wo-checkbox:not(:disabled)");
		$all.prop("checked", $boxes.length > 0 && $boxes.length === $boxes.filter(":checked").length);
	});

	dialog.show();
}

// ---------------------------------------------------------------------------
// Request for Quotation picker — Supplier (rows) x Item (columns) matrix.
// Suppliers per item come from Party Specific Item (party_type=Supplier,
// restrict_based_on=Item). Checking a row's own checkbox selects every item
// that supplier is mapped to; cells already covered by a live RFQ for this
// Material Request are shown disabled and marked "Already Created". Submitting
// creates ONE Request for Quotation with the union of selected items/suppliers.
// ---------------------------------------------------------------------------

function open_rfq_dialog(frm) {
	frappe.call({
		method: "pratap_dev.material_request_rfq.get_rfq_matrix_data",
		args: { material_request: frm.doc.name },
		freeze: true,
		freeze_message: __("Loading Suppliers..."),
		callback(r) {
			const data = r.message || {};
			if (!data.items || !data.items.length) {
				frappe.msgprint(__("No items found on this Material Request."));
				return;
			}
			if (!data.suppliers || !data.suppliers.length) {
				frappe.msgprint(
					__(
						"No suppliers are mapped to these items. Add them via Party Specific Item (Party Type = Supplier)."
					)
				);
				return;
			}
			show_rfq_matrix_dialog(frm, data);
		},
	});
}

function show_rfq_matrix_dialog(frm, data) {
	const items = data.items;
	const suppliers = data.suppliers;
	const supplier_item_map = data.supplier_item_map || {};
	const already_created = new Set(
		(data.already_created || []).map(([item_code, supplier]) => `${item_code}::${supplier}`)
	);

	let html = `
<style>
.rfq-matrix-wrapper { overflow-x: auto; max-height: 60vh; overflow-y: auto; }
.rfq-matrix { border-collapse: collapse; width: 100%; font-size: 12px; }
.rfq-matrix th, .rfq-matrix td { border: 1px solid #e0e0e0; padding: 6px 8px; text-align: center; white-space: nowrap; }
.rfq-matrix th { background: #f7f7f7; position: sticky; top: 0; z-index: 1; }
.rfq-matrix td:first-child, .rfq-matrix th:first-child { text-align: left; position: sticky; left: 0; background: #fff; z-index: 2; }
.rfq-matrix th:first-child { background: #f7f7f7; z-index: 3; }
.rfq-already { color: #6c757d; font-size: 10px; display: block; margin-top: 2px; }
.rfq-select-all { display: flex; align-items: center; gap: 8px; padding: 8px 4px; margin-bottom: 8px; font-weight: 600; font-size: 13px; }
</style>
<label class="rfq-select-all"><input type="checkbox" class="rfq-select-all-box"> ${__("Select All")}</label>
<div class="rfq-matrix-wrapper">
<table class="rfq-matrix">
<thead><tr><th>${__("Supplier")}</th>`;

	items.forEach((i) => {
		html += `<th title="${frappe.utils.escape_html(i.item_code)}">${frappe.utils.escape_html(
			i.item_name || i.item_code
		)}</th>`;
	});
	html += `</tr></thead><tbody>`;

	suppliers.forEach((s) => {
		html += `<tr>
			<td><label><input type="checkbox" class="rfq-row-checkbox" data-supplier="${frappe.utils.escape_html(
				s.supplier
			)}"> ${frappe.utils.escape_html(s.supplier_name || s.supplier)}</label></td>`;

		items.forEach((i) => {
			const mapped = (supplier_item_map[i.item_code] || []).includes(s.supplier);
			if (!mapped) {
				html += `<td>&mdash;</td>`;
				return;
			}

			const done = already_created.has(`${i.item_code}::${s.supplier}`);
			if (done) {
				html += `<td>
					<input type="checkbox" class="rfq-cell-checkbox" disabled checked
						data-item="${frappe.utils.escape_html(i.item_code)}"
						data-supplier="${frappe.utils.escape_html(s.supplier)}">
					<span class="rfq-already">${__("Already Created")}</span>
				</td>`;
			} else {
				html += `<td>
					<input type="checkbox" class="rfq-cell-checkbox"
						data-item="${frappe.utils.escape_html(i.item_code)}"
						data-supplier="${frappe.utils.escape_html(s.supplier)}">
				</td>`;
			}
		});

		html += `</tr>`;
	});

	html += `</tbody></table></div>`;

	const dialog = new frappe.ui.Dialog({
		title: __("Request for Quotation — Select Items per Supplier"),
		size: "extra-large",
		fields: [{ fieldtype: "HTML", fieldname: "html" }],
		primary_action_label: __("Create Request for Quotation"),
		primary_action() {
			const $wrapper = dialog.$wrapper;
			const selected_items = new Set();
			const selected_suppliers = new Set();

			$wrapper.find(".rfq-cell-checkbox:checked:not(:disabled)").each(function () {
				selected_items.add($(this).data("item"));
				selected_suppliers.add($(this).data("supplier"));
			});

			if (!selected_items.size || !selected_suppliers.size) {
				frappe.msgprint(__("Please select at least one item/supplier combination."));
				return;
			}

			frappe.call({
				method: "pratap_dev.material_request_rfq.create_request_for_quotation",
				args: {
					material_request: frm.doc.name,
					item_codes: JSON.stringify(Array.from(selected_items)),
					suppliers: JSON.stringify(Array.from(selected_suppliers)),
				},
				freeze: true,
				freeze_message: __("Creating Request for Quotation..."),
				callback(res) {
					if (!res.message) {
						return;
					}
					dialog.hide();
					const link = `<a href="/app/request-for-quotation/${res.message}">${frappe.utils.escape_html(
						res.message
					)}</a>`;
					frappe.msgprint({
						title: __("Request for Quotation Created"),
						indicator: "green",
						message: __("{0} created.", [link]),
					});
				},
			});
		},
	});

	dialog.fields_dict.html.$wrapper.html(html);
	const $wrapper = dialog.fields_dict.html.$wrapper;

	// Row checkbox -> check every enabled item-cell for that supplier.
	$wrapper.on("change", ".rfq-row-checkbox", function () {
		const supplier = $(this).data("supplier");
		const checked = this.checked;
		$wrapper.find(".rfq-cell-checkbox:not(:disabled)").each(function () {
			if ($(this).data("supplier") === supplier) {
				this.checked = checked;
			}
		});
	});

	// Item-cell checkbox -> keep that supplier's row-checkbox in sync (checked
	// only once every enabled cell in the row is checked).
	$wrapper.on("change", ".rfq-cell-checkbox:not(:disabled)", function () {
		const supplier = $(this).data("supplier");
		const $cells = $wrapper.find(".rfq-cell-checkbox:not(:disabled)").filter(function () {
			return $(this).data("supplier") === supplier;
		});
		const all_checked = $cells.length > 0 && $cells.length === $cells.filter(":checked").length;
		$wrapper.find(".rfq-row-checkbox").each(function () {
			if ($(this).data("supplier") === supplier) {
				this.checked = all_checked;
			}
		});
	});

	$wrapper.on("change", ".rfq-select-all-box", function () {
		const checked = this.checked;
		$wrapper.find(".rfq-cell-checkbox:not(:disabled)").prop("checked", checked);
		$wrapper.find(".rfq-row-checkbox").prop("checked", checked);
	});

	dialog.show();
}
