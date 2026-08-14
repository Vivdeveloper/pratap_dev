// Stock Entry — Batch Packages allocation dialog.
// Real stock (batch + qty) is still set via ERPNext's standard "Add Batch Nos",
// so nothing about stock/valuation changes. This dialog captures HOW the moved qty
// splits across the batch's pack sizes, so the Batch Package Ledger can reduce the
// source-warehouse rows and add a new Transfer In row (e.g. to WIP) on submit.
// The allocation is stored (hidden) on the item row.

frappe.ui.form.on("Stock Entry", {
	refresh(frm) {
		add_batch_packages_button(frm);
		bind_se_row_selection(frm);
	},
});

// Module-level state so the in-field onchange handlers (whose `this` is not the
// dialog) can reach the live dialog + source warehouse. Mirrors the pattern used
// by purchase_receipt_batch_entry.js.
const se_pkg_state = { cdn: null, dialog: null, source_wh: null };

function bind_se_row_selection(frm) {
	const grid = frm.fields_dict.items?.grid;
	if (!grid || grid._rtm_pkg_sel_bound) return;
	grid.wrapper.on("click", ".grid-row", function () {
		se_pkg_state.cdn = $(this).attr("data-name");
	});
	grid._rtm_pkg_sel_bound = true;
}

function add_batch_packages_button(frm) {
	const grid = frm.fields_dict.items?.grid;
	if (!grid) return;
	grid.wrapper.find(".rtm-batch-pkg-btn-wrapper").remove();
	const $btn = grid.add_custom_button(__("Batch Packages"), () => {
		const row = get_selected_se_row(frm);
		if (!row) {
			frappe.msgprint(__("Click an item row first, then press Batch Packages."));
			return;
		}
		open_se_package_dialog(frm, row);
	});
	$btn.prop("disabled", frm.doc.docstatus !== 0);
}

function get_selected_se_row(frm) {
	const grid = frm.fields_dict.items?.grid;
	const selected = grid?.get_selected_children?.() || [];
	if (selected.length === 1) return selected[0];
	if (se_pkg_state.cdn) {
		const row = (frm.doc.items || []).find((r) => r.name === se_pkg_state.cdn);
		if (row) return row;
	}
	const with_item = (frm.doc.items || []).filter((r) => r.item_code);
	return with_item.length === 1 ? with_item[0] : null;
}

// Recompute the allocation grid in place: Total = Pack x Units. If a row has a
// Total but no Units (user typed Total directly), derive Units = Total / Pack
// (float). Reads the live dialog from module state so it works from any onchange.
function recompute_se_alloc() {
	const d = se_pkg_state.dialog;
	if (!d || !d.fields_dict.alloc) return;
	const grid = d.fields_dict.alloc.grid;
	(grid.data || []).forEach((r) => {
		const pkg = flt(r.standard_pkg_qty);
		if (!pkg) return;
		if (flt(r.total_qty) && !flt(r.no_of_unit)) {
			r.no_of_unit = flt(r.total_qty) / pkg;
		} else {
			r.total_qty = pkg * flt(r.no_of_unit);
		}
	});
	grid.refresh();
}

// Load the batch's available pack balances (from the ledger) into the grid.
function load_se_package_options() {
	const d = se_pkg_state.dialog;
	if (!d) return;
	const batch_no = d.get_value("batch_no");
	const warehouse = se_pkg_state.source_wh;
	if (!batch_no || !warehouse) return;

	frappe.call({
		method: "pratap_dev.batch_package_hooks.get_batch_package_options",
		args: { batch_no, warehouse },
		callback: (r) => {
			const opts = (r && r.message) || [];
			if (!opts.length) {
				frappe.show_alert({
					message: __("No package balance for {0} in {1}.", [batch_no, warehouse]),
					indicator: "orange",
				});
			}
			const data = opts.map((o) => ({
				standard_pkg_qty: flt(o.standard_pkg_qty),
				available: flt(o.total_qty),
				no_of_unit: 0,
				total_qty: 0,
			}));
			d.fields_dict.alloc.df.data = data;
			d.fields_dict.alloc.grid.refresh();
		},
	});
}

function open_se_package_dialog(frm, row) {
	if (!row.item_code) {
		frappe.msgprint(__("Select an Item Code on this row first."));
		return;
	}
	const source_wh = row.s_warehouse;
	const target_wh = row.t_warehouse;
	if (!source_wh) {
		frappe.msgprint(__("This row has no Source Warehouse — package allocation applies to outgoing stock."));
		return;
	}

	// pre-load any saved allocation
	let saved = [];
	try {
		saved = JSON.parse(row.custom_batch_packages_json || "[]");
		if (!Array.isArray(saved)) saved = [];
	} catch (e) {
		saved = [];
	}

	const d = new frappe.ui.Dialog({
		title: __("Batch Packages — {0}", [row.item_code]),
		size: "extra-large",
		fields: [
			{
				fieldname: "info",
				fieldtype: "HTML",
				options: `<div class="text-muted" style="margin-bottom:8px;">
					${__("Source")}: <b>${frappe.utils.escape_html(source_wh)}</b>
					${target_wh ? ` &nbsp;→&nbsp; ${__("Target")}: <b>${frappe.utils.escape_html(target_wh)}</b>` : ` &nbsp;(${__("consumption")})`}
					&nbsp;·&nbsp; ${__("Row Qty")}: <b>${format_number(flt(row.qty))}</b>
				</div>`,
			},
			{
				fieldname: "batch_no",
				fieldtype: "Link",
				options: "Batch",
				label: __("Batch"),
				reqd: 1,
				default: saved.length ? saved[0].batch_no : row.batch_no || "",
				get_query() {
					return { filters: { item: row.item_code } };
				},
				onchange() {
					load_se_package_options();
				},
			},
			{
				fieldname: "alloc",
				fieldtype: "Table",
				label: __("Take from these packages"),
				cannot_add_rows: false,
				cannot_delete_rows: false,
				in_place_edit: false,
				data: saved.map((r) => ({
					standard_pkg_qty: flt(r.standard_pkg_qty),
					available: flt(r.available),
					no_of_unit: flt(r.no_of_unit),
					total_qty: flt(r.total_qty),
				})),
				fields: [
					{ fieldname: "standard_pkg_qty", fieldtype: "Float", label: __("Pack Qty"), in_list_view: 1, columns: 2 },
					{ fieldname: "available", fieldtype: "Float", label: __("Available Qty"), in_list_view: 1, read_only: 1, columns: 3 },
					{
						fieldname: "no_of_unit",
						fieldtype: "Float",
						label: __("Take No of Unit"),
						in_list_view: 1,
						columns: 3,
						onchange() {
							setTimeout(recompute_se_alloc, 0);
						},
					},
					{
						fieldname: "total_qty",
						fieldtype: "Float",
						label: __("Take Total Qty"),
						in_list_view: 1,
						columns: 3,
						onchange() {
							setTimeout(recompute_se_alloc, 0);
						},
					},
				],
			},
		],
		primary_action_label: __("Save Allocation"),
		primary_action() {
			save_se_allocation(frm, row, d);
		},
	});

	se_pkg_state.dialog = d;
	se_pkg_state.source_wh = source_wh;

	d.show();

	// Auto-load pack rows for the pre-filled batch (unless we restored a saved set).
	if (d.get_value("batch_no") && !saved.length) {
		load_se_package_options();
	}
}

function save_se_allocation(frm, row, d) {
	const batch_no = d.get_value("batch_no");
	if (!batch_no) {
		frappe.msgprint(__("Select a Batch."));
		return;
	}
	// make sure derived values are current before reading
	recompute_se_alloc();

	const rows = (d.fields_dict.alloc.grid.data || [])
		.map((r) => {
			const pkg = flt(r.standard_pkg_qty);
			const units = flt(r.no_of_unit);
			const total = flt(r.total_qty) || pkg * units;
			return { batch_no, standard_pkg_qty: pkg, no_of_unit: units, total_qty: total, available: flt(r.available) };
		})
		.filter((r) => r.total_qty > 0 || r.no_of_unit > 0);

	if (!rows.length) {
		frappe.msgprint(__("Enter how many units/qty to take from at least one package."));
		return;
	}

	// soft check: don't take more than available
	for (const r of rows) {
		if (r.available && r.total_qty > r.available + 0.0001) {
			frappe.msgprint(__("Pack Qty {0}: taking {1} exceeds available {2}.", [r.standard_pkg_qty, r.total_qty, r.available]));
			return;
		}
	}

	frappe.model.set_value(row.doctype, row.name, "custom_batch_packages_json", JSON.stringify(rows));
	se_pkg_state.dialog = null;
	d.hide();
	frappe.show_alert({
		message: __("Package allocation saved for {0}. It posts to the batch ledger on submit.", [batch_no]),
		indicator: "green",
	});
}
