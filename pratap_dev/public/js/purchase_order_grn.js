frappe.ui.form.on("Purchase Order", {
	refresh(frm) {
		remove_default_purchase_receipt_button(frm);

		if (can_create_grn(frm)) {
			frm.add_custom_button(__("Create GRN"), () => show_create_grn_dialog(frm), __("Create"));
		}

		if (pratap_dev.last_buying_rates.should_show(frm)) {
			frm.add_custom_button(
				__("Last Buying Rate"),
				() => show_last_buying_rates(frm),
				__("Tools")
			);
		}

		update_grn_created_display(frm);
		update_gate_pass_display(frm);
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

function show_last_buying_rates(frm) {
	return pratap_dev.last_buying_rates.show(frm, {
		rate_column_label: __("PO Rate"),
		current_po: frm.doc.name,
	});
}

// Read-only "GRN Created" flag: Yes if any submitted GRN references this PO, else No.
// Recomputed on view so it is always current (even for POs saved before the flag existed);
// the server keeps the stored value in sync on GRN submit/cancel.
function update_grn_created_display(frm) {
	if (frm.is_new() || !frm.doc.name || !frm.fields_dict.custom_grn_created) {
		return;
	}
	// Only recompute if this user can read Purchase Receipts. Users who can see POs but
	// not GRNs would otherwise trigger a "Not permitted" (PermissionError) from the
	// frappe.client.get_value endpoint. For them we trust the stored value, which the
	// server keeps in sync on GRN submit/cancel.
	if (!frappe.model.can_read("Purchase Receipt")) {
		return;
	}
	// NOTE: pass the parent doctype ("Purchase Receipt") as the 5th arg. frappe.client.get_value
	// raises PermissionError unconditionally when a child table is queried without a parent
	// (check_parent_permission), so querying "Purchase Receipt Item" on its own would throw
	// "Not permitted" for EVERY user. With the parent supplied, the check runs against
	// Purchase Receipt (already gated by the can_read guard above).
	frappe.db
		.get_value(
			"Purchase Receipt Item",
			{ purchase_order: frm.doc.name, docstatus: 1 },
			"name",
			null,
			"Purchase Receipt"
		)
		.then((r) => {
			const has_grn = !!(r && r.message && r.message.name);
			const val = has_grn ? "Yes" : "No";
			if (frm.doc.custom_grn_created !== val) {
				frm.doc.custom_grn_created = val;
				frm.refresh_field("custom_grn_created");
			}
		});
}

// Read-only "Gate Pass" flag: Yes if any Gate Pass references this PO, else No.
// Recomputed on view so it is always current; the server keeps the stored value in sync
// on PO validate.
function update_gate_pass_display(frm) {
	if (frm.is_new() || !frm.doc.name || !frm.fields_dict.custom_gate_pass_available) {
		return;
	}
	if (!frappe.model.can_read("Gate Pass")) {
		return;
	}
	frappe.db
		.get_value("Gate Pass", { purchase_order_po_no: frm.doc.name }, "name")
		.then((r) => {
			const has_gp = !!(r && r.message && r.message.name);
			const val = has_gp ? "Yes" : "No";
			if (frm.doc.custom_gate_pass_available !== val) {
				frm.doc.custom_gate_pass_available = val;
				frm.refresh_field("custom_gate_pass_available");
			}
		});
}

function remove_default_purchase_receipt_button(frm) {
	// ERPNext adds Purchase Receipt under Create; site translation shows it as "GRN".
	const label = __("Purchase Receipt");
	const group = __("Create");

	const remove_if_exists = () => {
		while (frm.custom_buttons?.[label]) {
			frm.remove_custom_button(label, group);
		}
	};

	if (frm._pr_remove_pr_interval) {
		clearInterval(frm._pr_remove_pr_interval);
	}

	remove_if_exists();

	let attempts = 0;
	frm._pr_remove_pr_interval = setInterval(() => {
		attempts++;
		const existed = !!frm.custom_buttons?.[label];
		remove_if_exists();

		if (existed || attempts >= 50) {
			clearInterval(frm._pr_remove_pr_interval);
			frm._pr_remove_pr_interval = null;
		}
	}, 100);
}

function can_create_grn(frm) {
	if (frm.doc.docstatus !== 1) {
		return false;
	}
	if (["Closed", "On Hold"].includes(frm.doc.status)) {
		return false;
	}
	return flt(frm.doc.per_received) < 100;
}

function show_create_grn_dialog(frm) {
	frappe.call({
		method: "pratap_dev.purchase_order_grn.get_po_grn_dialog_items",
		args: { purchase_order: frm.doc.name },
		freeze: true,
		freeze_message: __("Loading items..."),
		callback(r) {
			const items = r.message || [];
			if (!items.length) {
				// Fully received already — instead of a dead-end popup, take the user to this
				// PO's GRNs (Purchase Receipt list filtered by this Purchase Order) so they can
				// review every GRN raised against it.
				frappe.show_alert(
					{
						message: __("No pending quantity to receive — showing this PO's GRNs."),
						indicator: "blue",
					},
					5
				);
				frappe.set_route("List", "Purchase Receipt", { purchase_order: frm.doc.name });
				return;
			}
			open_create_grn_dialog(frm, items);
		},
	});
}

// Module-level handle to the open Create-GRN dialog so grid onchange handlers (where
// `this` is the window, not the control) can reach the batch grid to recompute.
const grn_dialog_state = { dialog: null };

function open_create_grn_dialog(frm, items) {
	const prepared_items = items.map((row) => prepare_grn_dialog_row(row));
	const batch_items = prepared_items.filter((it) => cint(it.has_batch_no));

	const fields = [
		{
			fieldname: "sales_invoice_number",
			fieldtype: "Data",
			label: __("Sales Invoice Number"),
			reqd: 1,
		},
		{
			fieldname: "sales_invoice_date",
			fieldtype: "Date",
			label: __("Invoice Date"),
			reqd: 1,
		},
		{
			fieldname: "gate_pass",
			fieldtype: "Link",
			options: "Gate Pass",
			label: __("Gate Pass"),
		},
		{
			fieldname: "invoice_section_break",
			fieldtype: "Section Break",
		},
		{
			fieldname: "items",
			fieldtype: "Table",
			label: __("Items"),
			cannot_add_rows: true,
			cannot_delete_rows: true,
			in_place_edit: true,
			data: prepared_items,
			fields: get_grn_dialog_table_fields(),
		},
	];

	// Batch-tracked items get a batch-detail table below (mirrors "Add Batch Nos"), so the
	// Serial-and-Batch Bundle is built automatically when the GRN is created.
	if (batch_items.length) {
		fields.push({
			fieldname: "batch_section_break",
			fieldtype: "Section Break",
			label: __("Batch Details"),
		});
		fields.push({
			fieldname: "batch_details",
			fieldtype: "Table",
			label: __("Batch Details"),
			description: __(
				"Batch-wise detail for batch-tracked items. The No of Unit across an item's rows must equal its GRN Unit. Use Add Row to split one item across multiple batches."
			),
			cannot_add_rows: false,
			cannot_delete_rows: false,
			in_place_edit: true,
			data: seed_batch_detail_rows(batch_items),
			fields: get_batch_detail_table_fields(batch_items),
		});
	}

	// History — past GRNs raised from this PO (draft + submitted). Collapsible section
	// (Tab Break is unreliable inside frappe.ui.Dialog, so we use a section instead).
	fields.push({
		fieldtype: "Section Break",
		fieldname: "history_section",
		label: __("History (previous GRNs for this PO)"),
		collapsible: 1,
		collapsible_depends_on: "eval:true",
	});
	fields.push({
		fieldtype: "HTML",
		fieldname: "history_html",
		options: `<div class="text-muted" style="padding:8px">${__("Loading history…")}</div>`,
	});

	const dialog = new frappe.ui.Dialog({
		title: __("Create GRN from {0}", [frm.doc.name]),
		size: "extra-large",
		fields: fields,
		primary_action_label: __("Create GRN"),
		primary_action() {
			submit_create_grn(frm, dialog);
		},
	});

	grn_dialog_state.dialog = dialog;
	dialog.show();
	bind_grn_grid_events(dialog);
	setup_batch_detail_grid(dialog, batch_items);
	load_grn_history(frm, dialog);

	// Auto-link the Gate Pass that references this PO, if one exists — and carry its Supplier
	// Invoice No / Date into the Sales Invoice Number / Invoice Date fields of this dialog.
	frappe.db
		.get_value(
			"Gate Pass",
			{ purchase_order_po_no: frm.doc.name },
			["name", "supplier_invoice_no", "supplier_invoice_date"]
		)
		.then((r) => {
			const gp = r && r.message;
			if (gp && gp.name) {
				dialog.set_value("gate_pass", gp.name);
				if (gp.supplier_invoice_no) {
					dialog.set_value("sales_invoice_number", gp.supplier_invoice_no);
				}
				if (gp.supplier_invoice_date) {
					dialog.set_value("sales_invoice_date", gp.supplier_invoice_date);
				}
			}
		});
}

function load_grn_history(frm, dialog) {
	frappe.call({
		method: "pratap_dev.purchase_order_grn.get_po_grn_history",
		args: { purchase_order: frm.doc.name },
		callback(r) {
			render_grn_history(dialog, r.message || []);
		},
	});
}

function render_grn_history(dialog, rows) {
	const field = dialog.fields_dict.history_html;
	if (!field) {
		return;
	}
	if (!rows.length) {
		field.$wrapper.html(
			`<div class="text-muted" style="padding:8px">${__(
				"No GRNs have been created from this PO yet."
			)}</div>`
		);
		return;
	}

	const body = rows
		.map((r) => {
			const grn_link = `<a href="/app/purchase-receipt/${encodeURIComponent(
				r.grn
			)}" target="_blank">${frappe.utils.escape_html(r.grn || "")}</a>`;
			const created = r.creation ? frappe.datetime.str_to_user(r.creation) : "";
			const inv_date = r.invoice_date ? frappe.datetime.str_to_user(r.invoice_date) : "";
			return `<tr>
				<td>${grn_link}<div class="text-muted" style="font-size:11px">${frappe.utils.escape_html(
					r.docstatus_label || ""
				)}</div></td>
				<td>${frappe.utils.escape_html(r.sales_invoice || "")}</td>
				<td>${inv_date}</td>
				<td>${frappe.utils.escape_html(r.item_code || "")}</td>
				<td style="text-align:right">${flt(r.qty)}</td>
				<td>${frappe.utils.escape_html(r.supplier_batches || "")}</td>
				<td style="text-align:right">${flt(r.sample_qty)}</td>
				<td>${created}</td>
			</tr>`;
		})
		.join("");

	field.$wrapper.html(`
		<div style="overflow-x:auto">
			<table class="table table-bordered" style="font-size:12px; margin-bottom:0">
				<thead><tr>
					<th>${__("GRN")}</th>
					<th>${__("Sales Invoice #")}</th>
					<th>${__("Invoice Date")}</th>
					<th>${__("Item")}</th>
					<th style="text-align:right">${__("GRN Qty")}</th>
					<th>${__("Supplier Batch")}</th>
					<th style="text-align:right">${__("Sample Qty")}</th>
					<th>${__("Created On")}</th>
				</tr></thead>
				<tbody>${body}</tbody>
			</table>
		</div>
	`);
}

// One pre-seeded batch row per batch-tracked item — Std Pkg Qty from the item's Packing
// Qty, No of Unit from its GRN Unit. The user fills Supplier Batch / Expiry / Sample Qty,
// and may Add Row to split an item across several batches.
function seed_batch_detail_rows(batch_items) {
	return batch_items.map((it) => {
		const packing = flt(it.custom_packing_qty) || 1;
		const units = flt(it.grn_unit);
		return {
			po_item: it.po_item,
			item_code: it.item_code,
			supplier_batch: "",
			batch_no: "",
			standard_pkg_qty: packing,
			no_of_unit: units,
			qty: packing * units,
			expiry_date: null,
			sample_qty: 0,
		};
	});
}

function get_batch_detail_table_fields(batch_items) {
	const item_options = [...new Set(batch_items.map((b) => b.item_code))];
	return [
		{ fieldname: "po_item", fieldtype: "Data", hidden: 1 },
		{
			fieldname: "item_code",
			fieldtype: "Select",
			label: __("Item Code"),
			options: item_options.join("\n"),
			in_list_view: 1,
			columns: 2,
			onchange() {
				on_batch_item_change(this.doc, batch_items);
			},
		},
		{
			fieldname: "supplier_batch",
			fieldtype: "Data",
			label: __("Supplier Batch"),
			in_list_view: 1,
			columns: 2,
			description: __("A Batch No is auto-generated from this on create"),
		},
		{
			fieldname: "batch_no",
			fieldtype: "Data",
			label: __("Batch No (auto)"),
			read_only: 1,
			in_list_view: 1,
			columns: 1,
		},
		{
			fieldname: "standard_pkg_qty",
			fieldtype: "Float",
			label: __("Standard Pkg Qty"),
			read_only: 1,
			in_list_view: 1,
			columns: 1,
		},
		{
			fieldname: "no_of_unit",
			fieldtype: "Float",
			label: __("No of Unit"),
			in_list_view: 1,
			columns: 1,
			onchange() {
				setTimeout(recompute_batch_detail_grid, 0);
			},
		},
		{
			fieldname: "qty",
			fieldtype: "Float",
			label: __("Total Qty"),
			read_only: 1,
			in_list_view: 1,
			columns: 1,
		},
		{
			fieldname: "expiry_date",
			fieldtype: "Date",
			label: __("Expiry Date"),
			in_list_view: 1,
			columns: 1,
			min_date: frappe.datetime.str_to_obj(frappe.datetime.get_today()),
		},
		{
			fieldname: "sample_qty",
			fieldtype: "Float",
			label: __("Sample Quantity"),
			in_list_view: 1,
			columns: 1,
		},
	];
}

// Auto-fill newly added batch rows. When an item's stock arrives in more than one batch,
// the user clicks "Add Row" to split it — the new row is pre-filled with the same item as
// the row above (its PO link + Standard Pkg Qty) and the REMAINING No of Unit for that item
// (GRN Unit minus what its other batch rows already consume), so only Supplier Batch /
// Expiry / Sample Qty need typing.
function setup_batch_detail_grid(dialog, batch_items) {
	const grid = dialog?.fields_dict?.batch_details?.grid;
	if (!grid || grid._pratap_prefill_bound) {
		return;
	}
	const original_add = grid.add_new_row.bind(grid);
	grid.add_new_row = function (...args) {
		const result = original_add(...args);
		const data = grid.data || [];
		const new_row = data[data.length - 1];
		if (new_row) {
			prefill_batch_row(new_row, grid, batch_items);
			grid.refresh();
		}
		return result;
	};
	grid._pratap_prefill_bound = true;
}

function prefill_batch_row(row, grid, batch_items) {
	const data = grid.data || [];
	// Default to the item of the nearest row above that has one; else the first batch item.
	let src_code = null;
	for (let i = data.length - 2; i >= 0; i--) {
		if (data[i].item_code) {
			src_code = data[i].item_code;
			break;
		}
	}
	if (!src_code && batch_items.length) {
		src_code = batch_items[0].item_code;
	}
	const match = batch_items.find((b) => b.item_code === src_code);
	if (!match) {
		return;
	}
	const packing = flt(match.custom_packing_qty) || 1;
	// Units already allocated to this item across its other batch rows.
	const allocated = data
		.filter((r) => r !== row && r.item_code === match.item_code)
		.reduce((sum, r) => sum + flt(r.no_of_unit), 0);
	const remaining = Math.max(flt(match.grn_unit) - allocated, 0);

	row.item_code = match.item_code;
	row.po_item = match.po_item;
	row.standard_pkg_qty = packing;
	row.no_of_unit = remaining;
	row.qty = packing * remaining;
	row.supplier_batch = "";
	row.batch_no = "";
	row.expiry_date = null;
	row.sample_qty = 0;
}

// When Item Code is (re)chosen on a batch row (e.g. a new split row), bind it to the
// matching item's PO line + default its Standard Pkg Qty, then recompute Total Qty.
function on_batch_item_change(doc, batch_items) {
	const match = batch_items.find((b) => b.item_code === doc.item_code);
	if (match) {
		doc.po_item = match.po_item;
		doc.standard_pkg_qty = flt(match.custom_packing_qty) || 1;
	}
	setTimeout(recompute_batch_detail_grid, 0);
}

// Recompute Total Qty (= Std Pkg Qty x No of Unit) for every batch row and re-render.
function recompute_batch_detail_grid() {
	const dialog = grn_dialog_state.dialog;
	const grid = dialog?.fields_dict?.batch_details?.grid;
	if (!grid) {
		return;
	}
	(grid.data || []).forEach((row) => {
		row.qty = (flt(row.standard_pkg_qty) || 0) * flt(row.no_of_unit);
	});
	grid.refresh();
}

// When an item has exactly ONE batch row, keep it in sync with the upper GRN Unit so the
// simple (single-batch) case needs no manual entry. Split rows (2+) are left untouched.
function sync_batch_rows_for_item(dialog, upper_row) {
	const grid = dialog?.fields_dict?.batch_details?.grid;
	if (!grid) {
		return;
	}
	const rows = (grid.data || []).filter((b) => b.po_item === upper_row.po_item);
	if (rows.length === 1) {
		const packing = flt(upper_row.custom_packing_qty) || 1;
		rows[0].standard_pkg_qty = packing;
		rows[0].no_of_unit = flt(upper_row.grn_unit);
		rows[0].qty = packing * flt(upper_row.grn_unit);
		grid.refresh();
	}
}

function submit_create_grn(frm, dialog) {
	const grid = dialog.fields_dict.items?.grid;
	const rows = grid?.get_selected_children() || [];

	if (!rows.length) {
		frappe.throw(__("Please tick at least one item checkbox to create GRN."));
	}

	const items_payload = [];
	const selected_po_items = new Set();

	for (const row of rows) {
		recalculate_grn_row(row);

		const grn_units = flt(row.grn_unit);
		const packing = flt(row.custom_packing_qty) || 1;
		const balance_units = flt(row.balance_no_of_unit);

		if (grn_units <= 0) {
			continue;
		}
		if (grn_units > balance_units) {
			frappe.throw(
				__("GRN Unit for {0} cannot be greater than Balance No of Unit {1}", [
					row.item_code,
					balance_units,
				])
			);
		}

		selected_po_items.add(row.po_item);
		items_payload.push({
			po_item: row.po_item,
			item_code: row.item_code,
			has_batch_no: cint(row.has_batch_no),
			custom_packing_qty: packing,
			custom_total_qty: grn_units,
			qty: packing * grn_units,
			grn_qty: packing * grn_units,
		});
	}

	if (!items_payload.length) {
		frappe.throw(__("Please enter GRN Unit for at least one selected item."));
	}

	// Collect batch rows for the selected items only.
	const batch_grid = dialog.fields_dict.batch_details?.grid;
	const batch_rows_all = batch_grid?.data || [];
	const batch_payload = [];
	for (const b of batch_rows_all) {
		if (!selected_po_items.has(b.po_item)) {
			continue;
		}
		const units = flt(b.no_of_unit);
		const supplier_batch = (b.supplier_batch || "").trim();
		if (units <= 0 && !supplier_batch) {
			continue; // untouched / empty row
		}
		const packing = flt(b.standard_pkg_qty) || 1;
		batch_payload.push({
			po_item: b.po_item,
			item_code: b.item_code,
			supplier_batch: supplier_batch,
			batch_no: (b.batch_no || "").trim(),
			standard_pkg_qty: packing,
			no_of_unit: units,
			total_qty: packing * units,
			expiry_date: b.expiry_date || null,
			sample_qty: flt(b.sample_qty),
		});
	}

	// Block early if a batch-tracked item's batch rows are missing/incomplete (option B).
	const today = frappe.datetime.get_today();
	for (const it of items_payload) {
		if (!cint(it.has_batch_no)) {
			continue;
		}
		const rows_for_item = batch_payload.filter((b) => b.po_item === it.po_item);
		if (!rows_for_item.length) {
			frappe.throw(__("Item {0}: add batch details before creating the GRN.", [it.item_code]));
		}
		let total_units = 0;
		for (const r of rows_for_item) {
			if (!r.supplier_batch) {
				frappe.throw(
					__("Item {0}: Supplier Batch is required for every batch row.", [it.item_code])
				);
			}
			if (r.no_of_unit <= 0) {
				frappe.throw(
					__("Item {0}: batch No of Unit must be greater than 0.", [it.item_code])
				);
			}
			if (r.expiry_date && r.expiry_date < today) {
				frappe.throw(
					__("Item {0}: Expiry Date cannot be in the past.", [it.item_code])
				);
			}
			total_units += r.no_of_unit;
		}
		if (Math.abs(total_units - flt(it.custom_total_qty)) > 0.0001) {
			frappe.throw(
				__("Item {0}: batch No of Unit total ({1}) must equal the GRN Unit ({2}).", [
					it.item_code,
					total_units,
					it.custom_total_qty,
				])
			);
		}
	}

	dialog.hide();

	frappe.call({
		method: "pratap_dev.purchase_order_grn.create_grn_with_batches_and_qc",
		args: {
			purchase_order: frm.doc.name,
			items: items_payload,
			batches: batch_payload,
			sales_invoice_number: dialog.get_value("sales_invoice_number"),
			sales_invoice_date: dialog.get_value("sales_invoice_date"),
			gate_pass: dialog.get_value("gate_pass"),
		},
		freeze: true,
		freeze_message: __("Creating GRN, building batches and sending for QC..."),
		callback(response) {
			if (response.exc) {
				return;
			}
			const res = response.message || {};
			const grns = res.grns || [];
			const qcs = res.qcs || [];

			frappe.show_alert(
				{
					message: __("{0} GRN(s) created · {1} QC(s) sent", [grns.length, qcs.length]),
					indicator: "green",
				},
				6
			);

			if (qcs.length === 1) {
				frappe.set_route("Form", "Pratap Quality Inspection", qcs[0]);
			} else if (qcs.length > 1) {
				frappe.set_route("List", "Pratap Quality Inspection");
			} else if (grns.length === 1) {
				frappe.set_route("Form", "Purchase Receipt", grns[0]);
			} else {
				frm.reload_doc();
			}
		},
	});
}

function get_grn_dialog_table_fields() {
	return [
		{
			fieldname: "po_item",
			fieldtype: "Data",
			hidden: 1,
		},
		{
			fieldname: "po_qty",
			fieldtype: "Float",
			hidden: 1,
		},
		{
			fieldname: "po_no_of_unit",
			fieldtype: "Float",
			hidden: 1,
		},
		{
			fieldname: "received_grn_qty",
			fieldtype: "Float",
			hidden: 1,
		},
		{
			fieldname: "draft_grn_qty",
			fieldtype: "Float",
			hidden: 1,
		},
		{
			fieldname: "grn_qty",
			fieldtype: "Float",
			hidden: 1,
		},
		{
			fieldname: "uom",
			fieldtype: "Link",
			options: "UOM",
			hidden: 1,
		},
		{
			fieldname: "has_batch_no",
			fieldtype: "Int",
			hidden: 1,
		},
		{
			fieldname: "item_code",
			fieldtype: "Link",
			options: "Item",
			label: __("Item Code"),
			read_only: 1,
			in_list_view: 1,
			columns: 2,
		},
		{
			fieldname: "custom_packing_qty",
			fieldtype: "Float",
			label: __("Packing Qty"),
			read_only: 1,
			in_list_view: 1,
		},
		{
			fieldname: "custom_total_qty",
			fieldtype: "Float",
			label: __("No of Unit"),
			read_only: 1,
			in_list_view: 1,
			description: __("Balance available to receive (frozen)"),
		},
		{
			fieldname: "grn_unit",
			fieldtype: "Float",
			label: __("GRN Unit"),
			in_list_view: 1,
			columns: 2,
			description: __("No of units to receive in this GRN"),
		},
		{
			fieldname: "qty",
			fieldtype: "Float",
			label: __("Total Qty"),
			read_only: 1,
			in_list_view: 1,
		},
		{
			fieldname: "balance_no_of_unit",
			fieldtype: "Float",
			hidden: 1,
		},
		{
			fieldname: "balance_grn_qty",
			fieldtype: "Float",
			hidden: 1,
		},
	];
}

function prepare_grn_dialog_row(row) {
	const prepared = { ...row };
	prepared.po_qty = flt(prepared.po_qty);
	prepared.po_no_of_unit = flt(prepared.po_no_of_unit);
	prepared.custom_packing_qty = flt(prepared.custom_packing_qty) || 1;
	prepared.received_grn_qty = flt(prepared.received_grn_qty);
	prepared.draft_grn_qty = flt(prepared.draft_grn_qty);
	prepared.has_batch_no = cint(prepared.has_batch_no);

	// Compute the PO balance (frozen "No of Unit") once.
	const received_units = prepared.received_grn_qty / prepared.custom_packing_qty;
	const draft_units = prepared.draft_grn_qty / prepared.custom_packing_qty;
	prepared.balance_no_of_unit = Math.max(
		prepared.po_no_of_unit - received_units - draft_units,
		0
	);
	prepared.balance_grn_qty = prepared.balance_no_of_unit * prepared.custom_packing_qty;
	prepared.pending_grn_qty = prepared.balance_grn_qty;

	// Frozen "No of Unit" = PO balance; editable "GRN Unit" defaults to the full balance.
	prepared.custom_total_qty = prepared.balance_no_of_unit;
	prepared.grn_unit = prepared.balance_no_of_unit;
	recalculate_grn_row(prepared);
	return prepared;
}

// "No of Unit" is now the frozen PO balance; the editable driver is "GRN Unit".
// Total Qty = Packing Qty × GRN Unit (capped to the PO balance).
function recalculate_grn_row(row, options = {}) {
	const packing = flt(row.custom_packing_qty) || 1;
	const balance_units = flt(row.balance_no_of_unit);

	let grn_units = flt(row.grn_unit);
	const was_over = grn_units > balance_units;
	if (was_over) {
		grn_units = balance_units;
		row.grn_unit = grn_units;
		if (options.show_cap_message) {
			frappe.show_alert({
				message: __(
					"{0}: GRN Unit cannot exceed {1} (balance on PO)",
					[row.item_code || "", balance_units]
				),
				indicator: "orange",
			});
		}
	}

	row.qty = packing * grn_units;
	row.grn_qty = row.qty;
	return was_over;
}

function bind_grn_grid_events(dialog) {
	const grid = dialog.fields_dict.items?.grid;
	if (!grid) {
		return;
	}

	const on_grn_unit_change = (grid_row) => {
		recalculate_grn_row(grid_row.doc, { show_cap_message: true });
		grid_row.refresh_field("grn_unit");
		grid_row.refresh_field("qty");
		// Keep a single-batch item's row in step with its GRN Unit.
		sync_batch_rows_for_item(dialog, grid_row.doc);
	};

	const handle = function () {
		const row_name = $(this).closest(".grid-row").attr("data-name");
		const grid_row = grid.grid_rows_by_docname[row_name];
		if (grid_row) {
			on_grn_unit_change(grid_row);
		}
	};

	grid.wrapper.on("change", 'input[data-fieldname="grn_unit"]', handle);
	grid.wrapper.on("blur", 'input[data-fieldname="grn_unit"]', handle);
}
