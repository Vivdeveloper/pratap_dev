// Stock Entry — Batch Packages allocation dialog.
// Real stock (batch + qty) is still set via ERPNext's standard "Add Batch Nos",
// so nothing about stock/valuation changes. This dialog captures HOW the moved qty
// splits across each batch's pack sizes, so the Batch Package Ledger can reduce the
// source-warehouse rows and add new Transfer In rows (e.g. to WIP) on submit.
//
// Behaviour mirrors the standard batch selector: it auto-lists ONLY the batches
// with package balance in the source warehouse, in FIFO order (oldest first), and
// pre-fills the "take" amounts up to the item row's qty. Batch is a column in the
// table (no separate picker). The allocation is stored (hidden) on the item row.

frappe.ui.form.on("Stock Entry", {
	refresh(frm) {
		add_batch_packages_button(frm);
		bind_se_row_selection(frm);
	},
});

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

// Total = Pack x Units. If a row has a Total but no Units (user typed Total), derive
// Units = Total / Pack (float). Reads the live dialog from module state.
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

// FIFO pre-fill: walk the (already FIFO-ordered) rows and take from each up to its
// available balance until the item row's qty is met.
function fifo_prefill(rows, target_qty) {
	let remaining = flt(target_qty);
	rows.forEach((r) => {
		const pkg = flt(r.standard_pkg_qty);
		const avail = flt(r.available);
		if (remaining <= 0.0001 || !pkg || avail <= 0) {
			r.no_of_unit = 0;
			r.total_qty = 0;
			return;
		}
		const take = Math.min(avail, remaining);
		r.total_qty = take;
		r.no_of_unit = take / pkg;
		remaining -= take;
	});
	return rows;
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

	// restore a previously-saved allocation, if any
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
					&nbsp;·&nbsp; <span class="text-muted">${__("Batches shown FIFO from this warehouse")}</span>
				</div>`,
			},
			{
				fieldname: "alloc",
				fieldtype: "Table",
				label: __("Take from these batch packages (FIFO)"),
				cannot_add_rows: true,
				cannot_delete_rows: false,
				in_place_edit: false,
				data: [],
				fields: [
					{ fieldname: "batch_no", fieldtype: "Data", label: __("Batch"), in_list_view: 1, read_only: 1, columns: 2 },
					{ fieldname: "standard_pkg_qty", fieldtype: "Float", label: __("Pack Qty"), in_list_view: 1, read_only: 1, columns: 1 },
					{ fieldname: "available_units", fieldtype: "Float", label: __("Available Units"), in_list_view: 1, read_only: 1, columns: 2 },
					{ fieldname: "available", fieldtype: "Float", label: __("Available Qty"), in_list_view: 1, read_only: 1, columns: 2 },
					{
						fieldname: "no_of_unit",
						fieldtype: "Float",
						label: __("Take No of Unit"),
						in_list_view: 1,
						columns: 2,
						onchange() {
							setTimeout(recompute_se_alloc, 0);
						},
					},
					{
						fieldname: "total_qty",
						fieldtype: "Float",
						label: __("Take Total Qty"),
						in_list_view: 1,
						columns: 2,
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

	// Load FIFO options for the item in the source warehouse.
	frappe.call({
		method: "pratap_dev.batch_package_hooks.get_item_package_options",
		args: { item_code: row.item_code, warehouse: source_wh },
		callback: (r) => {
			const opts = (r && r.message) || [];
			if (!opts.length) {
				frappe.show_alert({
					message: __("No package balance for {0} in {1}.", [row.item_code, source_wh]),
					indicator: "orange",
				});
			}
			let data = opts.map((o) => ({
				batch_no: o.batch_no,
				standard_pkg_qty: flt(o.standard_pkg_qty),
				available_units: flt(o.no_of_unit),
				available: flt(o.total_qty),
				no_of_unit: 0,
				total_qty: 0,
			}));

			// If we had a saved allocation, restore those take amounts onto matching
			// (batch, pack) rows; otherwise FIFO-prefill up to the item row qty.
			if (saved.length) {
				data.forEach((r2) => {
					const s = saved.find(
						(x) => x.batch_no === r2.batch_no && flt(x.standard_pkg_qty) === flt(r2.standard_pkg_qty)
					);
					if (s) {
						r2.no_of_unit = flt(s.no_of_unit);
						r2.total_qty = flt(s.total_qty);
					}
				});
			} else {
				data = fifo_prefill(data, flt(row.qty));
			}

			d.fields_dict.alloc.df.data = data;
			d.fields_dict.alloc.grid.refresh();
		},
	});
}

function save_se_allocation(frm, row, d) {
	recompute_se_alloc();

	const rows = (d.fields_dict.alloc.grid.data || [])
		.map((r) => {
			const pkg = flt(r.standard_pkg_qty);
			const units = flt(r.no_of_unit);
			const total = flt(r.total_qty) || pkg * units;
			return {
				batch_no: (r.batch_no || "").trim(),
				standard_pkg_qty: pkg,
				no_of_unit: units,
				total_qty: total,
				available: flt(r.available),
			};
		})
		.filter((r) => r.batch_no && (r.total_qty > 0 || r.no_of_unit > 0));

	if (!rows.length) {
		frappe.msgprint(__("Enter how many units/qty to take from at least one batch package."));
		return;
	}

	// soft check: don't take more than available on any row
	for (const r of rows) {
		if (r.available && r.total_qty > r.available + 0.0001) {
			frappe.msgprint(
				__("Batch {0} (Pack {1}): taking {2} exceeds available {3}.", [
					r.batch_no,
					r.standard_pkg_qty,
					r.total_qty,
					r.available,
				])
			);
			return;
		}
	}

	frappe.model.set_value(row.doctype, row.name, "custom_batch_packages_json", JSON.stringify(rows));
	se_pkg_state.dialog = null;
	d.hide();
	frappe.show_alert({
		message: __("Package allocation saved. It posts to the batch ledger on submit."),
		indicator: "green",
	});
}
