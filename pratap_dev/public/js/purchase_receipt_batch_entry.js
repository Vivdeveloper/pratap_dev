frappe.ui.form.on("Purchase Receipt", {
	setup(frm) {
		patch_pratap_batch_entry_handler(frm);
	},

	onload(frm) {
		patch_pratap_batch_entry_handler(frm);
	},

	refresh(frm) {
		patch_pratap_batch_entry_handler(frm);
		ensure_batch_entry_button(frm);
	},
});

frappe.ui.form.on("Purchase Receipt Item", {
	add_serial_batch_bundle(frm, cdt, cdn) {
		open_batch_entry_dialog(frm, cdt, cdn);
	},
});

const pratap_batch_entry_state = {
	frm: null,
	cdn: null,
	dialog: null,
	default_pkg_qty: null,
	required_no_of_unit: null,
};

function patch_pratap_batch_entry_handler(frm) {
	if (!frm.cscript) {
		return;
	}

	frm.cscript.add_serial_batch_bundle = function () {};
}

function ensure_batch_entry_button(frm) {
	const items_field = frm.fields_dict.items;
	const grid = items_field?.grid;
	if (!grid) {
		return;
	}

	ensure_batch_entry_styles();
	bind_items_grid_selection(frm);

	items_field.$wrapper.find(".pratap-batch-entry-btn-wrapper").remove();

	const label = __("Add Batch Nos");
	const $btn = grid.add_custom_button(label, () => {
		const row = get_selected_batch_item_row(frm);
		if (!row) {
			frappe.msgprint(__("Please select an item row in the table first."));
			return;
		}
		open_batch_entry_dialog(frm, row.doctype, row.name);
	});

	$btn.detach().insertAfter(grid.wrapper.find(".grid-add-multiple-rows"));
	$btn.prop("disabled", frm.doc.docstatus !== 0);
}

function bind_items_grid_selection(frm) {
	const grid = frm.fields_dict.items?.grid;
	if (!grid || grid._pratap_batch_selection_bound) {
		return;
	}

	grid.wrapper.on("click", ".grid-row", function () {
		pratap_batch_entry_state.frm = frm;
		pratap_batch_entry_state.cdn = $(this).attr("data-name");
	});

	grid._pratap_batch_selection_bound = true;
}

function get_selected_batch_item_row(frm) {
	const grid = frm.fields_dict.items?.grid;
	if (!grid) {
		return null;
	}

	const selected = grid.get_selected_children();
	if (selected.length === 1) {
		return selected[0];
	}

	if (pratap_batch_entry_state.frm === frm && pratap_batch_entry_state.cdn) {
		const row = (frm.doc.items || []).find((item) => item.name === pratap_batch_entry_state.cdn);
		if (row) {
			return row;
		}
	}

	const item_rows = (frm.doc.items || []).filter((item) => item.item_code);
	if (item_rows.length === 1) {
		return item_rows[0];
	}

	return null;
}

async function ensure_item_batch_tracking(item_code) {
	const { message: item_meta } = await frappe.db.get_value("Item", item_code, "has_batch_no");
	if (cint(item_meta?.has_batch_no)) {
		return true;
	}

	return new Promise((resolve) => {
		frappe.confirm(
			__(
				"Item {0} is not batch tracked. Enable batch tracking on this item and continue?",
				[item_code]
			),
			async () => {
				await frappe.call({
					method: "pratap_dev.purchase_receipt_batch_entry.enable_item_batch_tracking",
					args: { item_code },
				});
				resolve(true);
			},
			() => resolve(false)
		);
	});
}

async function open_batch_entry_dialog(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row?.item_code) {
		frappe.msgprint(__("Please select an Item Code first."));
		return;
	}

	if (frm.is_new()) {
		frappe.throw(__("Please save this GRN before adding batch numbers."));
	}

	const can_continue = await ensure_item_batch_tracking(row.item_code);
	if (!can_continue) {
		return;
	}

	pratap_batch_entry_state.frm = frm;
	pratap_batch_entry_state.cdn = row.name;

	const default_pkg_qty = flt(row.custom_packing_qty) || 1;
	const required_no_of_unit = flt(row.custom_total_qty);

	const { message: context } = await frappe.call({
		method: "pratap_dev.purchase_receipt_batch_entry.get_grn_batch_entry_context",
		args: {
			purchase_receipt: frm.doc.name,
			purchase_receipt_item: row.name,
		},
		freeze: true,
		freeze_message: __("Loading batch details..."),
	});

	const batch_rows = context?.batch_rows || [];
	const initial_rows = (batch_rows.length ? batch_rows : [{}]).map((entry) =>
		prepare_batch_entry_row(entry, default_pkg_qty)
	);

	show_batch_entry_dialog(frm, row, initial_rows, default_pkg_qty, required_no_of_unit);
}

function show_batch_entry_dialog(frm, row, initial_rows, default_pkg_qty, required_no_of_unit) {
	if (pratap_batch_entry_state.dialog) {
		pratap_batch_entry_state.dialog.hide();
		pratap_batch_entry_state.dialog = null;
	}

	const is_read_only = frm.doc.docstatus !== 0;
	const bundle_label = row.serial_and_batch_bundle || __("Not set");

	const dialog = new frappe.ui.Dialog({
		title: __("Add Batch Nos"),
		size: "extra-large",
		fields: [
			{
				fieldname: "item_info",
				fieldtype: "HTML",
				options: `<div class="pratap-batch-dialog-meta">
					<div class="pratap-batch-dialog-meta-item">
						<span class="pratap-batch-dialog-label">${__("Item")}</span>
						<strong>${frappe.utils.escape_html(row.item_code || "")}</strong>
						${
							row.item_name
								? `<span class="text-muted"> — ${frappe.utils.escape_html(row.item_name)}</span>`
								: ""
						}
					</div>
					<div class="pratap-batch-dialog-meta-bundle">
						<span class="pratap-batch-dialog-label">${__("Bundle")}</span>
						<strong>${frappe.utils.escape_html(bundle_label)}</strong>
					</div>
					<div class="pratap-batch-dialog-meta-bundle">
						<span class="pratap-batch-dialog-label">${__("Required No of Unit")}</span>
						<strong>${format_batch_qty(required_no_of_unit)}</strong>
					</div>
				</div>`,
			},
			{
				fieldname: "batches",
				fieldtype: "Table",
				label: __("Batches"),
				cannot_add_rows: is_read_only,
				cannot_delete_rows: is_read_only,
				in_place_edit: !is_read_only,
				data: initial_rows,
				fields: get_batch_entry_table_fields(default_pkg_qty, is_read_only, row.item_code),
			},
		],
		primary_action_label: is_read_only ? __("Close") : __("Save Batch Nos"),
		primary_action() {
			if (is_read_only) {
				dialog.hide();
				return;
			}
			save_batch_entry_dialog(frm, row, dialog);
		},
	});

	pratap_batch_entry_state.dialog = dialog;
	pratap_batch_entry_state.default_pkg_qty = default_pkg_qty;
	pratap_batch_entry_state.required_no_of_unit = required_no_of_unit;

	dialog.show();
	style_batch_entry_dialog(dialog);

	if (!is_read_only) {
		bind_batch_entry_grid_events(dialog, default_pkg_qty, row.item_code);
	}
}

function setup_batch_link_query(grid, item_code, default_pkg_qty = 1) {
	if (!grid || !item_code) {
		return;
	}

	const batch_query = () => ({
		filters: {
			item: item_code,
		},
	});

	const batch_route_options = () => ({
		item: item_code,
	});

	const batch_field = (grid.docfields || []).find((df) => df.fieldname === "batch_no");
	if (batch_field) {
		batch_field.get_query = batch_query;
		batch_field.get_route_options_for_new_doc = batch_route_options;
	}

	const apply_query = (grid_row) => {
		const field = grid_row?.get_field?.("batch_no");
		if (field) {
			field.get_query = batch_query;
			field.df.get_query = batch_query;
			field.df.get_route_options_for_new_doc = batch_route_options;
		}
	};

	(grid.grid_rows || []).forEach(apply_query);

	if (grid._pratap_batch_query_applied) {
		return;
	}

	const original_add_new_row = grid.add_new_row.bind(grid);
	grid.add_new_row = function (...args) {
		const result = original_add_new_row(...args);
		finalize_new_batch_entry_row(grid, default_pkg_qty, item_code);
		return result;
	};

	const original_refresh = grid.refresh.bind(grid);
	grid.refresh = function (...args) {
		const result = original_refresh(...args);
		setup_batch_link_query(grid, item_code, default_pkg_qty);
		return result;
	};

	grid._pratap_batch_query_applied = true;
}

function finalize_new_batch_entry_row(grid, default_pkg_qty, item_code) {
	if (!grid) {
		return;
	}

	const default_pkg = flt(default_pkg_qty) || flt(grid._pratap_default_pkg_qty) || 1;
	const row_doc = grid.df?.data?.[grid.df.data.length - 1];
	if (row_doc) {
		finalize_batch_entry_row_doc(row_doc, default_pkg);
	}

	const grid_row = grid.grid_rows?.[grid.grid_rows.length - 1];
	if (grid_row?.doc) {
		finalize_batch_entry_row_doc(grid_row.doc, default_pkg);
		grid_row.refresh_field("custom_packing_qty");
		grid_row.refresh_field("custom_total_qty");
		grid_row.refresh_field("qty");

		if (item_code) {
			const batch_query = () => ({ filters: { item: item_code } });
			const batch_route_options = () => ({ item: item_code });
			const field = grid_row.get_field?.("batch_no");
			if (field) {
				field.get_query = batch_query;
				field.df.get_query = batch_query;
				field.df.get_route_options_for_new_doc = batch_route_options;
			}
		}
	}
}

function finalize_batch_entry_row_doc(doc, default_pkg_qty) {
	if (!flt(doc.custom_packing_qty)) {
		doc.custom_packing_qty = default_pkg_qty;
	}
	recalculate_batch_entry_row(doc, default_pkg_qty);
	return doc;
}

function style_batch_entry_dialog(dialog) {
	const grid = dialog.fields_dict.batches?.grid;
	if (!grid) {
		return;
	}

	dialog.$wrapper.find(".modal-dialog").addClass("pratap-batch-entry-dialog");
	grid.wrapper.find(".form-grid").css("overflow-x", "visible");
	grid.wrapper.find(".grid-heading-row, .grid-body .rows").css("min-width", "100%");
	grid.refresh();
}

function get_batch_entry_table_fields(default_pkg_qty, is_read_only = false, item_code = "") {
	return [
		{
			fieldname: "batch_no",
			fieldtype: "Link",
			options: "Batch",
			label: __("Batch No"),
			in_list_view: 1,
			reqd: 1,
			read_only: is_read_only,
			columns: 4,
			get_query() {
				return {
					filters: {
						item: item_code,
					},
				};
			},
			get_route_options_for_new_doc() {
				return {
					item: item_code,
				};
			},
		},
		{
			fieldname: "custom_packing_qty",
			fieldtype: "Float",
			label: __("Standard Pkg Qty"),
			in_list_view: 1,
			default: default_pkg_qty,
			read_only: 1,
			columns: 3,
		},
		{
			fieldname: "custom_total_qty",
			fieldtype: "Float",
			label: __("No of Unit"),
			in_list_view: 1,
			read_only: is_read_only,
			columns: 2,
		},
		{
			fieldname: "qty",
			fieldtype: "Float",
			label: __("Total Qty"),
			read_only: 1,
			in_list_view: 1,
			columns: 3,
		},
	];
}

function bind_batch_entry_grid_events(dialog, default_pkg_qty, item_code) {
	const grid = dialog.fields_dict.batches?.grid;
	if (!grid) {
		return;
	}

	grid._pratap_default_pkg_qty = default_pkg_qty;
	setup_batch_link_query(grid, item_code, default_pkg_qty);

	const refresh_row_fields = (grid_row) => {
		grid_row.refresh_field("custom_packing_qty");
		grid_row.refresh_field("custom_total_qty");
		grid_row.refresh_field("qty");
	};

	const on_qty_field_change = (grid_row) => {
		recalculate_batch_entry_row(grid_row.doc, default_pkg_qty);
		refresh_row_fields(grid_row);
	};

	const handler = function () {
		const $input = $(this);
		const row_name = $input.closest(".grid-row").attr("data-name");
		const grid_row = grid.grid_rows_by_docname[row_name];
		if (!grid_row) {
			return;
		}
		// Read the value straight from the input so Total Qty (Standard Pkg Qty x No of Unit)
		// updates live as the user types, instead of only on save/model-commit.
		const fieldname = $input.attr("data-fieldname");
		if (fieldname) {
			grid_row.doc[fieldname] = flt($input.val());
		}
		on_qty_field_change(grid_row);
	};

	grid.wrapper
		.off(
			"input change blur keyup",
			'input[data-fieldname="custom_packing_qty"], input[data-fieldname="custom_total_qty"]'
		)
		.on(
			"input change blur keyup",
			'input[data-fieldname="custom_packing_qty"], input[data-fieldname="custom_total_qty"]',
			handler
		);
}

function validate_batch_entry_rows(rows, required_no_of_unit) {
	if (!rows.length) {
		frappe.throw(__("Add at least one batch row."));
	}

	if (flt(required_no_of_unit) <= 0) {
		frappe.throw(__("Set No of Unit on the item row before adding batches."));
	}

	let total_no_of_unit = 0;

	for (const entry of rows) {
		const batch_no = (entry.batch_no || "").trim();
		if (!batch_no) {
			frappe.throw(__("Batch No is required for all rows."));
		}
		if (flt(entry.custom_total_qty) <= 0) {
			frappe.throw(__("No of Unit must be greater than 0 for batch {0}.", [batch_no]));
		}
		total_no_of_unit += flt(entry.custom_total_qty);
	}

	if (Math.abs(total_no_of_unit - flt(required_no_of_unit)) > 0.0001) {
		const entered_units = format_batch_qty_plain(total_no_of_unit);
		const required_units = format_batch_qty_plain(required_no_of_unit);
		const difference = format_batch_qty_plain(Math.abs(total_no_of_unit - required_no_of_unit));

		frappe.throw({
			title: __("Batch Units Mismatch"),
			message: __(
				"The total <b>No of Unit</b> across batch rows is <b>{0}</b>, but this item row requires <b>{1}</b>. The difference is <b>{2}</b>. Please adjust batch units so both totals match.",
				[entered_units, required_units, difference]
			),
		});
	}
}

function save_batch_entry_dialog(frm, row, dialog) {
	const default_pkg_qty = pratap_batch_entry_state.default_pkg_qty || flt(row.custom_packing_qty) || 1;
	const required_no_of_unit = pratap_batch_entry_state.required_no_of_unit;

	const grid = dialog.fields_dict.batches?.grid;
	const rows = (grid?.data || []).map((entry) => {
		recalculate_batch_entry_row(entry, default_pkg_qty);
		return entry;
	});

	validate_batch_entry_rows(rows, required_no_of_unit);

	dialog.hide();

	frappe.call({
		method: "pratap_dev.purchase_receipt_batch_entry.add_batches_to_grn_item",
		args: {
			purchase_receipt: frm.doc.name,
			purchase_receipt_item: row.name,
			batches: rows.map((entry) => ({
				batch_no: (entry.batch_no || "").trim(),
				standard_pkg_qty: flt(entry.custom_packing_qty) || default_pkg_qty,
				no_of_unit: flt(entry.custom_total_qty),
				total_qty: flt(entry.qty),
			})),
		},
		freeze: true,
		freeze_message: __("Updating batch details..."),
		callback(response) {
			if (response.exc) {
				return;
			}

			const result = response.message || {};
			frappe.model.set_value(row.doctype, row.name, {
				qty: result.qty,
				received_qty: result.received_qty,
				stock_qty: result.stock_qty,
				custom_packing_qty: result.custom_packing_qty,
				serial_and_batch_bundle: result.serial_and_batch_bundle,
				use_serial_batch_fields: 0,
			});

			frm.refresh_field("items");
			frappe.show_alert({
				message: __("Batch details updated"),
				indicator: "green",
			});
		},
	});
}

function prepare_batch_entry_row(row, default_pkg_qty) {
	const prepared = {
		batch_no: row.batch_no || "",
		custom_packing_qty: flt(row.standard_pkg_qty ?? row.custom_packing_qty) || default_pkg_qty,
		custom_total_qty: flt(row.no_of_unit ?? row.custom_total_qty),
		qty: flt(row.total_qty ?? row.qty),
	};
	recalculate_batch_entry_row(prepared, default_pkg_qty);
	return prepared;
}

function recalculate_batch_entry_row(row, default_pkg_qty) {
	const packing = flt(row.custom_packing_qty) || flt(default_pkg_qty) || 1;
	row.custom_packing_qty = packing;
	row.qty = packing * flt(row.custom_total_qty);
	return row;
}

function format_batch_qty(value) {
	return format_batch_qty_plain(value);
}

function format_batch_qty_plain(value) {
	const number = flt(value);
	if (!number) {
		return "0";
	}

	const formatted = flt(number, 3).toString();
	return formatted.replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
}

function ensure_batch_entry_styles() {
	let style = document.getElementById("pratap-batch-entry-styles");
	if (style) {
		return;
	}

	style = document.createElement("style");
	style.id = "pratap-batch-entry-styles";
	style.textContent = `
		.pratap-batch-entry-dialog {
			max-width: min(1180px, 96vw) !important;
			width: 96vw;
		}
		.pratap-batch-entry-dialog .modal-body {
			max-height: 80vh;
			overflow-y: auto;
		}
		.pratap-batch-dialog-meta {
			display: flex;
			flex-wrap: wrap;
			gap: 16px 32px;
			margin-bottom: 12px;
			padding: 10px 12px;
			border: 1px solid var(--border-color, #d1d8dd);
			border-radius: var(--border-radius, 8px);
			background: var(--subtle-fg, #f7fafc);
		}
		.pratap-batch-dialog-meta-item,
		.pratap-batch-dialog-meta-bundle {
			min-width: 220px;
		}
		.pratap-batch-dialog-label {
			display: block;
			font-size: 11px;
			text-transform: uppercase;
			letter-spacing: 0.02em;
			color: var(--text-muted, #6c7680);
			margin-bottom: 2px;
		}
		.pratap-batch-entry-dialog .form-grid {
			overflow-x: visible !important;
		}
		.pratap-batch-entry-dialog .grid-heading-row,
		.pratap-batch-entry-dialog .grid-body .rows {
			min-width: 100% !important;
		}
		.pratap-batch-entry-dialog .grid-heading-row .grid-static-col,
		.pratap-batch-entry-dialog .data-row .col {
			min-width: 0;
		}
	`;
	document.head.appendChild(style);
}
