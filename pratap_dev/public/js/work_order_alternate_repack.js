// Alternate-item Repack picker on the Work Order form.
//
// Flow:
//   1. Tick one or more required item rows -> a "Pick Alternate Batches" button
//      appears next to the Custom Source Warehouse field.
//   2. Click it -> a modal opens. Pick a Warehouse (defaults to Custom Source
//      Warehouse). The modal then lists EVERY alternate-item batch that has stock
//      in that warehouse, with Available Qty shown (all computed server-side).
//   3. Enter Pick Qty on the rows you want.
//   4. Insert -> server creates an auto-submitted Repack Stock Entry that consumes
//      the picked alternate batches and produces the total into a batch of the main
//      item (grouped per main item), linked to the Work Order.

frappe.provide("pratap_dev");

const REPACK_METHOD = "pratap_dev.work_order_alternate_repack";

// Show/hide the "Pick Alternate Batches" button based on row selection.
pratap_dev.toggle_pick_alt_button = function (frm) {
	const grid = frm.fields_dict.required_items && frm.fields_dict.required_items.grid;
	const selected = grid ? grid.get_selected() : [];
	const field = frm.fields_dict.custom_custom_source_warehouse;
	if (!field) return;

	field.$wrapper.find(".pratap-pick-alt-btn").remove();
	if (selected.length && frm.doc.docstatus === 0) {
		$(
			`<button class="btn btn-xs btn-primary pratap-pick-alt-btn" style="margin-top:6px;">
				${__("Pick Alternate Batches")} (${selected.length})
			</button>`
		)
			.appendTo(field.$wrapper)
			.on("click", () => pratap_dev.open_pick_alt_dialog(frm, selected));
	}
};

pratap_dev.open_pick_alt_dialog = function (frm, selected_rows) {
	const main_items = selected_rows.map((name) => locals["Work Order Item"][name].item_code);
	const default_wh = frm.doc.custom_custom_source_warehouse;

	// backing array for the table; reloaded whenever the warehouse changes
	let rows = [];

	const dialog = new frappe.ui.Dialog({
		title: __("Pick Alternate Batches"),
		size: "extra-large",
		fields: [
			{
				fieldtype: "Link",
				fieldname: "warehouse",
				label: __("Warehouse"),
				options: "Warehouse",
				default: default_wh,
				reqd: 1,
				onchange: function () {
					pratap_dev.load_alternate_rows(dialog, main_items);
				},
			},
			{ fieldtype: "Column Break" },
			{ fieldtype: "Section Break" },
			{
				fieldname: "rows",
				fieldtype: "Table",
				cannot_add_rows: true,
				in_place_edit: true,
				data: rows,
				get_data: () => rows,
				fields: [
					{
						fieldtype: "Link",
						fieldname: "main_item",
						options: "Item",
						label: __("Main Item"),
						in_list_view: 1,
						read_only: 1,
						columns: 2,
					},
					{
						fieldtype: "Link",
						fieldname: "alternate_item",
						options: "Item",
						label: __("Alternate Item"),
						in_list_view: 1,
						read_only: 1,
						columns: 2,
					},
					{
						fieldtype: "Link",
						fieldname: "batch_no",
						options: "Batch",
						label: __("Batch"),
						in_list_view: 1,
						read_only: 1,
						columns: 3,
					},
					{
						fieldtype: "Float",
						fieldname: "available_qty",
						label: __("Available Qty"),
						in_list_view: 1,
						read_only: 1,
						columns: 2,
					},
					{
						fieldtype: "Float",
						fieldname: "pick_qty",
						label: __("Pick Qty"),
						in_list_view: 1,
						columns: 2,
					},
				],
			},
		],
		primary_action_label: __("Insert"),
		primary_action: () => {
			const picks = (dialog.get_value("rows") || []).filter((r) => flt(r.pick_qty) > 0);
			if (!picks.length) {
				frappe.msgprint(__("Enter a Pick Qty for at least one row."));
				return;
			}
			const over = picks.find((r) => flt(r.pick_qty) > flt(r.available_qty));
			if (over) {
				frappe.msgprint(
					__("Pick Qty {0} exceeds Available {1} for batch {2}.", [
						flt(over.pick_qty),
						flt(over.available_qty),
						over.batch_no,
					])
				);
				return;
			}

			// Confirm before creating the Repack Stock Entry (no silent auto-create).
			const total = picks.reduce((s, r) => s + flt(r.pick_qty), 0);
			frappe.confirm(
				__(
					"Create a Repack Stock Entry consuming {0} picked batch(es) (total {1})?",
					[picks.length, total]
				),
				() => {
					frappe.call({
						method: `${REPACK_METHOD}.create_alternate_repack`,
						args: { work_order: frm.doc.name, picks: JSON.stringify(picks) },
						freeze: true,
						freeze_message: __("Creating Repack Stock Entry..."),
						callback: (r) => {
							if (!r.message) return;
							dialog.hide();
							// server returns a single name (one main item) or a list
							const names = Array.isArray(r.message) ? r.message : [r.message];
							frappe.show_alert({
								message: __("Created {0} Repack Stock Entry(s): {1}", [
									names.length,
									names.join(", "),
								]),
								indicator: "green",
							});
							frappe.set_route("Form", "Stock Entry", names[0]);
						},
					});
				}
			);
		},
	});

	// expose the backing array so load_alternate_rows can refresh it
	dialog.__rows = rows;
	dialog.__set_rows = (newRows) => {
		rows.length = 0;
		newRows.forEach((x) => rows.push(x));
		dialog.fields_dict.rows.grid.refresh();
	};

	dialog.show();

	// auto-load for the default warehouse
	if (default_wh) {
		pratap_dev.load_alternate_rows(dialog, main_items);
	}
};

// Load all alternate-item batches (with available qty) for the chosen warehouse.
pratap_dev.load_alternate_rows = function (dialog, main_items) {
	const warehouse = dialog.get_value("warehouse");
	if (!warehouse) return;
	frappe.call({
		method: `${REPACK_METHOD}.get_alternate_batch_options`,
		args: { main_items: JSON.stringify(main_items), warehouse: warehouse },
		freeze: true,
		freeze_message: __("Loading available alternate batches..."),
		callback: (r) => {
			const list = (r.message || []).map((d) => Object.assign({ pick_qty: 0 }, d));
			// Prime the link-title cache so the Item cells show "code: name".
			list.forEach((d) => {
				if (d.main_item_name) {
					frappe.utils.add_link_title("Item", d.main_item, d.main_item + ": " + d.main_item_name);
				}
				if (d.alternate_item_name) {
					frappe.utils.add_link_title(
						"Item",
						d.alternate_item,
						d.alternate_item + ": " + d.alternate_item_name
					);
				}
			});
			dialog.__set_rows(list);
			if (!list.length) {
				frappe.show_alert({
					message: __("No alternate-item batches with stock in {0}.", [warehouse]),
					indicator: "orange",
				});
			}
		},
	});
};

frappe.ui.form.on("Work Order", {
	refresh(frm) {
		pratap_dev.toggle_pick_alt_button(frm);
	},
	onload_post_render(frm) {
		const grid = frm.fields_dict.required_items && frm.fields_dict.required_items.grid;
		if (grid && !grid.__pratap_alt_bound) {
			grid.__pratap_alt_bound = true;
			grid.wrapper.on("change", ".grid-row-check", () =>
				pratap_dev.toggle_pick_alt_button(frm)
			);
		}
	},
});
