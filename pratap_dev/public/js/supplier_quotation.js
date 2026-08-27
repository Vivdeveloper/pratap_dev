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

let _sq_po_dialog = null;

function show_create_purchase_order_dialog(frm) {
	if (!(frm.doc.items || []).length) {
		frappe.msgprint(__("No items to create a Purchase Order from."));
		return;
	}

	// Per-item context: standard pkg qty, no-of-unit, pending qty (MR row qty - already
	// ordered), and which submitted POs already exist for the row. All computed
	// server-side so restricted Buying users (no Purchase Order read access) don't hit
	// "No permission for Purchase Order Item" from a client-side child-table query.
	new Promise((resolve) => {
		frappe.call({
			method: "pratap_dev.supplier_quotation_po.get_sq_po_context",
			args: { supplier_quotation: frm.doc.name },
			callback: (r) => resolve(r.message || {}),
		});
	}).then((ctx) => {
		const po_by_row = {};
		Object.keys(ctx || {}).forEach((sq_item) => {
			po_by_row[sq_item] = (ctx[sq_item] && ctx[sq_item].purchase_orders) || [];
		});

		const data = (frm.doc.items || []).map((d) => {
			const c = ctx[d.name] || {};
			const std_pkg = flt(c.std_pkg) || 1;
			const has_cap = c.pending !== null && c.pending !== undefined;
			const pending = has_cap ? flt(c.pending) : null;
			const max_units = has_cap ? flt(pending / std_pkg, 3) : 0;
			const already = (po_by_row[d.name] || []).length ? 1 : 0;
			// Locked when fully ordered (MR pending <= 0) or, for non-MR items, when a
			// PO already exists for this SQ row.
			const locked = (has_cap && pending <= 0.0001) || (!has_cap && already);

			let default_units;
			if (locked) default_units = 0;
			else if (has_cap) default_units = max_units;
			else default_units = flt(c.no_of_unit) || (std_pkg ? flt(flt(d.qty) / std_pkg, 3) : 0);

			return {
				docname: d.name,
				item_code: d.item_code,
				item_name: d.item_name,
				std_pkg: std_pkg,
				sq_units: flt(c.no_of_unit),
				pending: has_cap ? String(flt(pending, 3)) : "",
				units_to_order: default_units,
				qty_to_order: flt(default_units * std_pkg, 3),
				select: locked ? 0 : 1,
				_has_cap: has_cap ? 1 : 0,
				_max_units: max_units,
				_locked: locked ? 1 : 0,
				already_created: already,
				purchase_order: (po_by_row[d.name] || []).join(", "),
			};
		});

		render_create_purchase_order_dialog(frm, data);
	});
}

// Two-way recompute (like the Stock Entry dialog), directional so it never fights
// the user, values capped at 3 decimals:
//   from_field "qty"  -> user typed Qty to Order, derive Units = Qty / Pack
//   otherwise (units) -> Qty to Order = Units x Pack
// NO client-side clamp here (that was zeroing the value on type); the pending cap
// is still enforced server-side in make_partial_purchase_order.
function recompute_sq_po(from_field) {
	if (!_sq_po_dialog) return;
	const grid = _sq_po_dialog.fields_dict.selected_items.grid;
	(grid.data || []).forEach((r) => {
		const pkg = flt(r.std_pkg) || 1;
		if (from_field === "qty") {
			r.units_to_order = flt(flt(r.qty_to_order) / pkg, 3);
		} else {
			r.qty_to_order = flt(flt(r.units_to_order) * pkg, 3);
		}
	});
	grid.refresh();
}

function render_create_purchase_order_dialog(frm, data) {
	const dialog = new frappe.ui.Dialog({
		title: __("Create Purchase Order — Units to Order"),
		size: "extra-large",
		fields: [
			{
				fieldname: "selected_items",
				fieldtype: "Table",
				// Same layout pattern as the (working) Stock Entry "Batch Packages"
				// dialog: native row checkboxes + header select-all, editable cells,
				// data populated AFTER show. Column widths sum to <= 10 so header and
				// body line up (the double-checkbox + overflow was the misalignment).
				label: __("Tick rows to order, set Units to Order"),
				cannot_add_rows: true,
				cannot_delete_rows: false,
				in_place_edit: false,
				data: [],
				fields: [
					{ fieldtype: "Data", fieldname: "docname", hidden: 1 },
					{ fieldtype: "Data", fieldname: "item_name", hidden: 1 },
					{ fieldtype: "Data", fieldname: "purchase_order", hidden: 1 },
					{ fieldtype: "Check", fieldname: "already_created", hidden: 1 },
					{ fieldtype: "Check", fieldname: "_has_cap", hidden: 1 },
					{ fieldtype: "Float", fieldname: "_max_units", hidden: 1 },
					{ fieldtype: "Check", fieldname: "_locked", hidden: 1 },
					{
						fieldtype: "Data",
						fieldname: "item_code",
						label: __("Item Code"),
						in_list_view: 1,
						read_only: 1,
						columns: 2,
					},
					{
						fieldtype: "Float",
						fieldname: "std_pkg",
						label: __("Std Pkg Qty"),
						in_list_view: 1,
						read_only: 1,
						columns: 1,
					},
					{
						fieldtype: "Float",
						fieldname: "sq_units",
						label: __("No of Unit"),
						in_list_view: 1,
						read_only: 1,
						columns: 1,
					},
					{
						fieldtype: "Data",
						fieldname: "pending",
						label: __("Pending"),
						in_list_view: 1,
						read_only: 1,
						columns: 1,
					},
					{
						fieldtype: "Float",
						fieldname: "units_to_order",
						label: __("Units to Order"),
						in_list_view: 1,
						columns: 2,
						onchange() {
							setTimeout(() => recompute_sq_po("units"), 0);
						},
					},
					{
						fieldtype: "Float",
						fieldname: "qty_to_order",
						label: __("Qty to Order"),
						in_list_view: 1,
						columns: 2,
						onchange() {
							setTimeout(() => recompute_sq_po("qty"), 0);
						},
					},
				],
			},
		],
		primary_action_label: __("Create Purchase Order"),
		primary_action() {
			recompute_sq_po();
			const grid = dialog.fields_dict.selected_items.grid;
			const selected = grid.get_selected_children() || [];
			if (!selected.length) {
				frappe.msgprint(__("Tick at least one row to order."));
				return;
			}
			const locked_ticked = selected.filter((r) => r._locked);
			const rows = selected
				.filter((r) => !r._locked && flt(r.units_to_order) > 0)
				.map((r) => ({ sq_item: r.docname, units: flt(r.units_to_order) }));

			if (!rows.length) {
				if (locked_ticked.length) {
					frappe.msgprint(
						__(
							"These item(s) are already fully ordered (nothing pending), so no PO can be raised: {0}",
							[locked_ticked.map((r) => r.item_code).join(", ")]
						)
					);
				} else {
					frappe.msgprint(__("Enter Units to Order (> 0) on the ticked rows."));
				}
				return;
			}

			dialog.hide();
			frappe.call({
				method: "pratap_dev.supplier_quotation_po.make_partial_purchase_order",
				args: { source_name: frm.doc.name, rows: JSON.stringify(rows) },
				freeze: true,
				freeze_message: __("Creating Purchase Order..."),
				callback(r) {
					if (!r.exc && r.message) {
						frappe.model.sync(r.message);
						frappe.set_route("Form", r.message.doctype, r.message.name);
					}
				},
			});
		},
	});

	_sq_po_dialog = dialog;
	dialog.show();

	// Populate rows AFTER show so the grid binds data + renders editable cells and
	// native checkboxes correctly (matches the Stock Entry dialog).
	const gf = dialog.fields_dict.selected_items;
	gf.df.data = data;
	gf.grid.refresh();
}
