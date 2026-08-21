// Stock Entry — Batch Packages allocation dialog (multi-row).
// Real stock (batch + qty) is still set via ERPNext's standard "Add Batch Nos".
// This dialog captures HOW the moved qty splits across each batch's pack sizes, and
// makes the allocation authoritative: on save it sets each row's Qty and rewrites
// its Serial and Batch Bundle to match (so ERPNext's bundle-vs-qty check passes),
// and the Batch Package Ledger posts the movement on submit.
//
// Select one OR MANY item rows, click "Batch Packages" -> one dialog with a section
// per row (FIFO-prefilled) -> one "Save Allocation" applies them all at once.

frappe.ui.form.on("Stock Entry", {
	refresh(frm) {
		add_batch_packages_button(frm);
		bind_se_row_selection(frm);
	},
});

const se_pkg_state = { cdn: null, dialog: null };

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
		if (frm.is_new() || frm.is_dirty()) {
			frappe.msgprint(__("Please save the Stock Entry before allocating batch packages."));
			return;
		}
		const rows = get_selected_se_rows(frm);
		if (!rows.length) {
			frappe.msgprint(
				__("Select item row(s) with a Source Warehouse first, then press Batch Packages.")
			);
			return;
		}
		open_se_multi_package_dialog(frm, rows);
	});
	$btn.prop("disabled", frm.doc.docstatus !== 0);
}

// Rows to allocate: ticked rows (multi) -> last-clicked -> all batch-tracked rows.
// Only rows with an item AND a source warehouse (allocation is for outgoing stock).
function get_selected_se_rows(frm) {
	const grid = frm.fields_dict.items?.grid;
	let rows = grid?.get_selected_children?.() || [];
	if (!rows.length && se_pkg_state.cdn) {
		const r = (frm.doc.items || []).find((x) => x.name === se_pkg_state.cdn);
		if (r) rows = [r];
	}
	if (!rows.length) rows = frm.doc.items || [];
	return rows.filter((r) => r.item_code && r.s_warehouse);
}

// Two-way calc across every section, directional so it never fights the user:
//   from_field "total_qty" -> user typed Total, derive Units = Total / Pack
//   otherwise (units edited) -> Total = Pack x Units
function recompute_all_se_alloc(from_field) {
	const d = se_pkg_state.dialog;
	if (!d) return;
	Object.keys(d.fields_dict).forEach((fn) => {
		if (!fn.startsWith("alloc_")) return;
		const grid = d.fields_dict[fn].grid;
		if (!grid) return;
		(grid.data || []).forEach((r) => {
			const pkg = flt(r.standard_pkg_qty);
			if (!pkg) return;
			if (from_field === "total_qty") {
				r.no_of_unit = flt(flt(r.total_qty) / pkg, 3);
			} else {
				r.total_qty = flt(pkg * flt(r.no_of_unit), 3);
			}
		});
		grid.refresh();
	});
}

// FIFO pre-fill: take from each (FIFO-ordered) row up to its available balance
// until the item row's qty is met.
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
		r.no_of_unit = flt(take / pkg, 3);
		remaining -= take;
	});
	return rows;
}

function alloc_table_fields() {
	return [
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
				setTimeout(() => recompute_all_se_alloc("no_of_unit"), 0);
			},
		},
		{
			fieldname: "total_qty",
			fieldtype: "Float",
			label: __("Take Total Qty"),
			in_list_view: 1,
			columns: 2,
			onchange() {
				setTimeout(() => recompute_all_se_alloc("total_qty"), 0);
			},
		},
	];
}

function open_se_multi_package_dialog(frm, item_rows) {
	// Build one section (header + table) per selected item row.
	const sections = item_rows.map((row, i) => {
		let saved = [];
		try {
			saved = JSON.parse(row.custom_batch_packages_json || "[]");
			if (!Array.isArray(saved)) saved = [];
		} catch (e) {
			saved = [];
		}
		return {
			row,
			source_wh: row.s_warehouse,
			target_wh: row.t_warehouse,
			fieldname: `alloc_${i}`,
			header_fieldname: `header_${i}`,
			saved,
		};
	});

	const fields = [];
	sections.forEach((s, i) => {
		fields.push({
			fieldtype: "HTML",
			fieldname: s.header_fieldname,
			options: `<div style="margin:${i ? "14px" : "0"} 0 6px;font-weight:600;">
				${frappe.utils.escape_html(s.row.item_code)}
				<span class="text-muted" style="font-weight:400;">
					· ${__("Source")}: ${frappe.utils.escape_html(s.source_wh)}
					${s.target_wh ? `→ ${frappe.utils.escape_html(s.target_wh)}` : `(${__("consumption")})`}
					· ${__("Row Qty")}: ${format_number(flt(s.row.qty))}
				</span>
			</div>`,
		});
		fields.push({
			fieldname: s.fieldname,
			fieldtype: "Table",
			label: "",
			cannot_add_rows: true,
			cannot_delete_rows: false,
			in_place_edit: false,
			data: [],
			fields: alloc_table_fields(),
		});
		if (i < sections.length - 1) {
			fields.push({ fieldtype: "Section Break" });
		}
	});

	const d = new frappe.ui.Dialog({
		title: __("Batch Packages — {0} item(s)", [sections.length]),
		size: "extra-large",
		fields: fields,
		primary_action_label: __("Save Allocation"),
		primary_action() {
			save_se_multi_allocation(frm, sections, d);
		},
	});

	se_pkg_state.dialog = d;
	d.show();

	// Load FIFO options for each section's item in its source warehouse.
	sections.forEach((s) => {
		frappe.call({
			method: "pratap_dev.batch_package_hooks.get_item_package_options",
			args: { item_code: s.row.item_code, warehouse: s.source_wh },
			callback: (r) => {
				const opts = (r && r.message) || [];
				if (!opts.length) {
					frappe.show_alert({
						message: __("No package balance for {0} in {1}.", [s.row.item_code, s.source_wh]),
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

				if (s.saved.length) {
					data.forEach((r2) => {
						const hit = s.saved.find(
							(x) => x.batch_no === r2.batch_no && flt(x.standard_pkg_qty) === flt(r2.standard_pkg_qty)
						);
						if (hit) {
							r2.no_of_unit = flt(hit.no_of_unit);
							r2.total_qty = flt(hit.total_qty);
						}
					});
				} else {
					data = fifo_prefill(data, flt(s.row.qty));
				}

				const field = d.fields_dict[s.fieldname];
				if (field) {
					field.df.data = data;
					field.grid.refresh();
				}
			},
		});
	});
}

async function save_se_multi_allocation(frm, sections, d) {
	recompute_all_se_alloc("no_of_unit");

	// Validate every section first; collect payloads. Nothing is applied until all
	// sections pass, so a bad row never leaves a half-applied Stock Entry.
	const payloads = [];
	for (const s of sections) {
		const grid = d.fields_dict[s.fieldname]?.grid;
		const rows = (grid?.data || [])
			.map((r) => {
				const pkg = flt(r.standard_pkg_qty);
				const units = flt(r.no_of_unit);
				const total = flt(r.total_qty) || flt(pkg * units, 3);
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
			continue; // section left empty -> skip that item
		}

		for (const r of rows) {
			if (r.available && r.total_qty > r.available + 0.0001) {
				frappe.msgprint(
					__("{0} — Batch {1} (Pack {2}): taking {3} exceeds available {4}.", [
						s.row.item_code,
						r.batch_no,
						r.standard_pkg_qty,
						r.total_qty,
						r.available,
					])
				);
				return;
			}
		}

		const total = rows.reduce((sum, r) => sum + flt(r.total_qty), 0);
		const batch_qty_map = {};
		rows.forEach((r) => {
			batch_qty_map[r.batch_no] = (batch_qty_map[r.batch_no] || 0) + flt(r.total_qty);
		});
		payloads.push({ row: s.row, rows, total, batch_qty_map });
	}

	if (!payloads.length) {
		frappe.msgprint(__("Enter allocation for at least one item."));
		return;
	}

	frappe.dom.freeze(__("Applying allocations..."));
	try {
		// Create OR update each row's Serial and Batch Bundle + qty + pack breakdown
		// the standard way (server-side), so this modal fully replaces ERPNext's
		// "Add Batch Nos" for the selected rows.
		for (const p of payloads) {
			await new Promise((resolve, reject) => {
				frappe.call({
					method: "pratap_dev.batch_package_hooks.apply_stock_entry_batches",
					args: {
						stock_entry: frm.doc.name,
						se_item: p.row.name,
						allocation: JSON.stringify(p.rows),
					},
					callback: () => resolve(),
					error: () => reject(),
				});
			});
		}
	} finally {
		frappe.dom.unfreeze();
	}

	se_pkg_state.dialog = null;
	d.hide();
	// Bundles were created/linked server-side (db). Reload so the row shows the
	// linked bundle and qty, and Save sees a consistent state.
	await frm.reload_doc();
	frappe.show_alert({
		message: __("Allocations saved for {0} item(s).", [payloads.length]),
		indicator: "green",
	});
}
