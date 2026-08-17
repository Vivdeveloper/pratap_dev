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

	// Two lookups: (1) which SQ rows already have a submitted PO, and (2) per-item
	// standard pkg qty, no-of-unit and pending qty (MR row qty - already ordered).
	Promise.all([
		frappe.db.get_list("Purchase Order Item", {
			filters: { supplier_quotation: frm.doc.name, docstatus: 1 },
			fields: ["supplier_quotation_item", "parent"],
			limit: 0,
		}),
		new Promise((resolve) => {
			frappe.call({
				method: "pratap_dev.supplier_quotation_po.get_sq_po_context",
				args: { supplier_quotation: frm.doc.name },
				callback: (r) => resolve(r.message || {}),
			});
		}),
	]).then(([po_rows, ctx]) => {
		const po_by_row = {};
		(po_rows || []).forEach((row) => {
			po_by_row[row.supplier_quotation_item] = po_by_row[row.supplier_quotation_item] || [];
			if (!po_by_row[row.supplier_quotation_item].includes(row.parent)) {
				po_by_row[row.supplier_quotation_item].push(row.parent);
			}
		});

		const data = (frm.doc.items || []).map((d) => {
			const c = ctx[d.name] || {};
			const std_pkg = flt(c.std_pkg) || 1;
			const has_cap = c.pending !== null && c.pending !== undefined;
			const pending = has_cap ? flt(c.pending) : null;
			const max_units = has_cap ? pending / std_pkg : 0;
			const already = po_by_row[d.name] ? 1 : 0;
			// Locked when fully ordered (MR pending <= 0) or, for non-MR items, when a
			// PO already exists for this SQ row.
			const locked = (has_cap && pending <= 0.0001) || (!has_cap && already);

			let default_units;
			if (locked) default_units = 0;
			else if (has_cap) default_units = max_units;
			else default_units = flt(c.no_of_unit) || (std_pkg ? flt(d.qty) / std_pkg : 0);

			return {
				docname: d.name,
				item_code: d.item_code,
				item_name: d.item_name,
				std_pkg: std_pkg,
				sq_units: flt(c.no_of_unit),
				pending: has_cap ? pending : "",
				units_to_order: default_units,
				qty_to_order: default_units * std_pkg,
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

// Live recompute: Qty to Order = Units x Std Pkg, clamped to the pending cap.
function recompute_sq_po() {
	if (!_sq_po_dialog) return;
	const grid = _sq_po_dialog.fields_dict.selected_items.grid;
	(grid.data || []).forEach((r) => {
		const pkg = flt(r.std_pkg) || 1;
		let units = flt(r.units_to_order);
		if (r._has_cap && units > flt(r._max_units)) {
			units = flt(r._max_units);
			r.units_to_order = units;
		}
		r.qty_to_order = units * pkg;
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
				label: __("Items"),
				cannot_add_rows: true,
				in_place_edit: false,
				data: data,
				get_data: () => data,
				fields: [
					{ fieldtype: "Data", fieldname: "docname", hidden: 1 },
					{ fieldtype: "Data", fieldname: "item_name", hidden: 1 },
					{ fieldtype: "Data", fieldname: "purchase_order", hidden: 1 },
					{ fieldtype: "Check", fieldname: "already_created", hidden: 1 },
					{ fieldtype: "Check", fieldname: "_has_cap", hidden: 1 },
					{ fieldtype: "Float", fieldname: "_max_units", hidden: 1 },
					{ fieldtype: "Check", fieldname: "_locked", hidden: 1 },
					{
						fieldtype: "Check",
						fieldname: "select",
						label: __("Select"),
						in_list_view: 1,
						columns: 1,
						read_only_depends_on: "eval:doc._locked",
					},
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
						read_only_depends_on: "eval:doc._locked",
						onchange() {
							setTimeout(recompute_sq_po, 0);
						},
					},
					{
						fieldtype: "Float",
						fieldname: "qty_to_order",
						label: __("Qty to Order"),
						in_list_view: 1,
						read_only: 1,
						columns: 2,
					},
				],
			},
		],
		primary_action_label: __("Create Purchase Order"),
		primary_action() {
			recompute_sq_po();
			const grid = dialog.fields_dict.selected_items.grid;
			const rows = (grid.data || [])
				.filter((r) => r.select && !r._locked && flt(r.units_to_order) > 0)
				.map((r) => ({ sq_item: r.docname, units: flt(r.units_to_order) }));

			if (!rows.length) {
				frappe.msgprint(__("Select at least one item and enter Units to Order."));
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

	// Hide the grid's native row-select checkbox column -- we already have our own
	// explicit "Select" field, so showing both would be confusing and redundant.
	dialog.$wrapper.find(".row-check").hide();
}
