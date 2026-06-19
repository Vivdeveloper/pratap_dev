// Copyright (c) 2026, saurabh@exacuer.com and contributors
// For license information, please see license.txt

frappe.ui.form.on("Pratap Quality Inspection", {
	setup(frm) {
		set_reference_doctype(frm);
		set_reference_name_query(frm);
	},

	refresh(frm) {
		set_reference_doctype(frm);
		set_reference_name_query(frm);
		set_cancel_all_ignore_doctypes(frm);
		handle_status_values(frm);
		toggle_supplier_coa(frm);
		setup_qc_submit_button(frm);
		if (frm.doc.reference_type === "GRN" && frm.doc.reference_name) {
			load_grn_batch_details(frm);
		} else {
			render_grn_batch_html(frm);
		}
		// on amending removing fields that is not relevent
		if (frm.doc.amended_from && frm.doc.__islocal){
			frm.set_value("stock_entry", "");
        }

		// Debuge later and fix it
		// frm.$wrapper.on("keyup", (frm) => {
		// 	console.log("keyup event triggered");
		// 	handel_submitted_buttons();
		// });
		// handel_submitted_buttons();


	},
	reference_type(frm) {
		const previous_doctype = frm.doc.reference_doctype;
		set_reference_doctype(frm);
		if (previous_doctype !== frm.doc.reference_doctype) {
			frm.set_value("reference_name", "");
		}
		handle_status_values(frm);
		toggle_supplier_coa(frm);
		if (frm.doc.reference_type !== "GRN") {
			frm.set_value("batch_qc_json", "");
			clear_grn_batch_html(frm);
		}
	},

	reference_name(frm) {
		fetch_reference_item_details(frm);
	},

	reference_qty(frm) {
		set_density_qty(frm);
		set_raw_material_required_qty(frm);
		validate_total_raw_material_percentage(frm);
	},

	custom_density(frm) {
		set_density_qty(frm);
	},

	purchase_uom(frm) {
		apply_density_for_same_uom(frm);
	},

	sales_uom(frm) {
		apply_density_for_same_uom(frm);
	},

	process_loss(frm) {
		set_density_qty(frm);
	},

	production_item(frm) {
		if (frm.doc.reference_type === "GRN") {
			load_grn_batch_details(frm);
		}
		if (!frm.doc.quality_inspection_template) {
			frm.call("get_item_specification_details").then(() => {
				frm.refresh_field("readings");
			});
		}
	},

	quality_inspection_template(frm) {
		frm.call("get_item_specification_details").then(() => {
			frm.refresh_field("readings");
		});
	},

	before_submit(frm) {
		if ((frm.doc.status || "").trim() !== "Accepted") {
			frappe.throw({
				title: __("Cannot Submit"),
				message: __(
					"Status must be Accepted before submit. Complete readings and set Status to Accepted."
				),
			});
		}
	},
});

frappe.ui.form.on("Pratap Quality Inspection Raw Material", {
	mat_req_in_pecentage(frm) {
		set_raw_material_required_qty(frm);
		validate_total_raw_material_percentage(frm);
	},

	item_code(frm, cdt, cdn) {
		set_row_actual_qty(cdt, cdn);
	},

	source_warehouse(frm, cdt, cdn) {
		set_row_actual_qty(cdt, cdn);
	},
});

function set_density_qty(frm) {
	const reference_qty = flt(frm.doc.reference_qty);
	const custom_density = flt(frm.doc.custom_density);
	const process_loss = flt(frm.doc.process_loss);
	const density_qty = custom_density > 0 ? reference_qty / custom_density : 0;
	const multiplier = 1 - process_loss / 100;
	const finished_qty = multiplier > 0 ? density_qty * multiplier : 0;
	frm.set_value("density_qty", density_qty);
	frm.set_value("finished_qty", finished_qty);
}

function set_raw_material_required_qty(frm) {
	const reference_qty = flt(frm.doc.reference_qty);
	(frm.doc.raw_materials || []).forEach((row) => {
		const percentage = flt(row.mat_req_in_pecentage);
		const total_req_qty = reference_qty * (percentage / 100);
		frappe.model.set_value(row.doctype, row.name, "total_req_qty", total_req_qty);
	});
}

function validate_total_raw_material_percentage(frm) {
	const total_percentage = (frm.doc.raw_materials || []).reduce(
		(total, row) => total + flt(row.mat_req_in_pecentage),
		0
	);

	if (total_percentage > 100) {
		frappe.msgprint(
			__(
				"Total Raw Material % cannot be greater than 100. Current total is {0}.",
				[total_percentage]
			)
		);
	}
}

function set_row_actual_qty(cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row || !row.item_code || !row.source_warehouse) {
		frappe.model.set_value(cdt, cdn, "actual_qty", 0);
		return;
	}

	frappe.db
		.get_value(
			"Bin",
			{ item_code: row.item_code, warehouse: row.source_warehouse },
			"actual_qty"
		)
		.then((r) => {
			const actualQty = flt(r.message?.actual_qty);
			frappe.model.set_value(cdt, cdn, "actual_qty", actualQty);
		});
}

function set_cancel_all_ignore_doctypes(frm) {
	// Same as ERPNext Quality Inspection: do not auto-cancel reference GRN / SABB via Cancel All.
	const ignore = ["Serial and Batch Bundle"];
	if (frm.doc.reference_doctype) {
		ignore.push(frm.doc.reference_doctype);
	}
	frm.ignore_doctypes_on_cancel_all = ignore;
}

function set_reference_doctype(frm) {
	const doctype_map = {
		GRN: "Purchase Receipt",
		"Purchase Invoice": "Purchase Invoice",
		"Delivery Note": "Delivery Note",
		"Sales Invoice": "Sales Invoice",
		"Work Order": "Work Order",
		"Job Card": "Job Card",
		"Stock Entry": "Stock Entry",
	};
	const mapped_doctype = doctype_map[frm.doc.reference_type] || "";
	if (frm.doc.reference_doctype !== mapped_doctype) {
		frm.set_value("reference_doctype", mapped_doctype);
	}
}

function set_reference_name_query(frm) {
	frm.set_query("reference_name", () => {
		if (frm.doc.reference_type === "GRN") {
			return {
				filters: {
					docstatus: ["<", 2],
				},
			};
		}
		return {};
	});
}

function apply_density_for_same_uom(frm) {
	const purchase_uom = (frm.doc.purchase_uom || "").trim().toLowerCase();
	const sales_uom = (frm.doc.sales_uom || "").trim().toLowerCase();

	if (purchase_uom && sales_uom && purchase_uom === sales_uom) {
		frm.set_value("custom_density", 1);
		set_density_qty(frm);
	}
}

function fetch_reference_item_details(frm) {
	if (!frm.doc.reference_type || !frm.doc.reference_name) {
		return Promise.resolve();
	}

	if (frm.doc.reference_type === "Work Order") {
		frm.set_value("work_order", frm.doc.reference_name);
		return Promise.resolve();
	}

	const reference_doctype = frm.doc.reference_doctype;
	if (!reference_doctype) {
		return Promise.resolve();
	}

	return frappe.db.get_doc(reference_doctype, frm.doc.reference_name).then((doc) => {
		const items = doc.items || [];
		if (!items.length) {
			if (frm.doc.reference_type === "GRN") {
				load_grn_batch_details(frm);
			}
			return;
		}
		let selected_item = items[0];
		if (frm.doc.purchase_receipt_item) {
			selected_item =
				items.find((row) => row.name === frm.doc.purchase_receipt_item) || selected_item;
		} else if (frm.doc.production_item) {
			selected_item =
				items.find((row) => row.item_code === frm.doc.production_item) || selected_item;
		}
		if (frm.doc.work_order) {
			selected_item =
				items.find((row) => row.work_order && row.work_order === frm.doc.work_order) ||
				selected_item;
		}

		frm.set_value("company", doc.company || "");
		frm.set_value("purchase_receipt_item", selected_item.name || "");
		frm.set_value("production_item", selected_item.item_code || "");
		frm.set_value("item_name", selected_item.item_name || "");
		frm.set_value("sales_uom", selected_item.uom || selected_item.stock_uom || "");
		frm.set_value("reference_qty", flt(selected_item.received_qty) || flt(selected_item.qty));

		if (selected_item.work_order) {
			frm.set_value("work_order", selected_item.work_order);
		}

		if (frm.doc.reference_type === "GRN" && selected_item.item_code) {
			frappe.db
				.get_value("Item", selected_item.item_code, ["purchase_uom"], (r) => {
					frm.set_value("purchase_uom", r.message?.purchase_uom || "");
					apply_density_for_same_uom(frm);
				})
				.then(() => load_grn_batch_details(frm));
			return;
		}

		if (frm.doc.reference_type === "GRN") {
			load_grn_batch_details(frm);
		}
	});
}

function handle_status_values(frm){
	if (frm.doc.reference_type == "GRN") {
		frm.set_df_property("status", "options", ["Pending", "Accepted", "Rejected"]);

	}
}

function setup_qc_submit_button(frm) {
	if (frm.doc.docstatus !== 0) {
		return;
	}

	const status = (frm.doc.status || "").trim();
	const can_submit = status === "Accepted";

	if (can_submit) {
		if ($(frm.page.btn_primary).attr("data-label") === "Submit") {
			$(frm.page.btn_primary).show();
		}
		return;
	}

	frm.page.clear_primary_action();
	frm.page.set_primary_action(__("Submit"), () => {
		frappe.throw({
			title: __("Cannot Submit"),
			message: __(
				"Status must be Accepted before submit. For GRN QC, complete all readings as Accepted."
			),
		});
	});
}

function handel_submitted_buttons(){
	if (cur_frm.doc.status === "Accepted" && !cur_frm.is_dirty()) {
		if ($(cur_frm.page.btn_primary).attr("data-label") === "Submit") {
			$(cur_frm.page.btn_primary).show();
		}
		
	} else {
		if(cur_frm.is_dirty()){
			$(cur_frm.page.btn_primary).show();
		}else{
			$(cur_frm.page.btn_primary).hide();
		}
	}
}
function toggle_supplier_coa(frm) {
	const show_supplier_coa = frm.doc.reference_type === "GRN";
	const grid = frm.fields_dict.readings?.grid;
	if (!grid) {
		return;
	}

	grid.visible_columns = [];
	grid.set_column_disp("supplier_coa", show_supplier_coa);
}

function clear_grn_batch_html(frm) {
	frm._grn_batch_rows = [];
	const $wrapper = frm.fields_dict.batch_html?.$wrapper;
	if ($wrapper) {
		$wrapper.empty();
	}
}

function parse_batch_qc_json(value) {
	if (!value) {
		return {};
	}
	try {
		const parsed = JSON.parse(value);
		return Array.isArray(parsed) ? Object.fromEntries(parsed.map((row) => [row.batch_no, row])) : {};
	} catch {
		return {};
	}
}

function serialize_batch_qc_rows(rows) {
	return JSON.stringify(
		(rows || []).map((row) => {
			const batch_qty = flt(row.batch_qty);
			const accepted_qty = flt(row.accepted_qty);
			return {
				batch_no: row.batch_no,
				batch_qty,
				accepted_qty,
				rejected_qty: Math.max(batch_qty - accepted_qty, 0),
			};
		})
	);
}

function load_grn_batch_details(frm) {
	if (frm.doc.reference_type !== "GRN" || !frm.doc.reference_name) {
		clear_grn_batch_html(frm);
		return;
	}

	frappe
		.call({
			method: "pratap_dev.pratap.doctype.pratap_quality_inspection.pratap_quality_inspection.get_grn_batch_list",
			args: {
				purchase_receipt: frm.doc.reference_name,
				item_code: frm.doc.production_item || null,
				purchase_receipt_item: frm.doc.purchase_receipt_item || null,
			},
			freeze: false,
		})
		.then((response) => {
			const saved_rows = parse_batch_qc_json(frm.doc.batch_qc_json);
			const batches = response.message || [];

			frm._grn_batch_rows = batches.map((row) => {
				const saved = saved_rows[row.batch_no] || {};
				const batch_qty = flt(row.batch_qty);
				const accepted_qty = Math.min(Math.max(flt(saved.accepted_qty), 0), batch_qty);
				return {
					batch_no: row.batch_no,
					batch_qty,
					accepted_qty,
					rejected_qty: batch_qty - accepted_qty,
				};
			});

			render_grn_batch_html(frm);
		});
}

function render_grn_batch_html(frm) {
	const $wrapper = frm.fields_dict.batch_html?.$wrapper;
	if (!$wrapper) {
		return;
	}

	if (frm.doc.reference_type !== "GRN") {
		clear_grn_batch_html(frm);
		return;
	}

	const rows = frm._grn_batch_rows || [];
	if (!rows.length) {
		const message = frm.doc.reference_name
			? __("No batch details found for this GRN item.")
			: __("Select a GRN reference to load batch details.");
		$wrapper.html(`<div class="grn-batch-empty text-muted">${message}</div>`);
		ensure_grn_batch_styles();
		return;
	}

	const is_read_only = frm.doc.docstatus === 1;
	const table_rows = rows
		.map((row, index) => {
			const accepted = format_batch_input(row.accepted_qty);
			const rejected = format_batch_display(calc_rejected_qty(row));
			const batch_qty = format_batch_display(row.batch_qty);

			if (is_read_only) {
				return `<tr data-batch-index="${index}">
					<td class="grn-batch-col-index">${index + 1}</td>
					<td class="grn-batch-col-batch">
						<span class="grn-batch-badge">${frappe.utils.escape_html(row.batch_no || "")}</span>
					</td>
					<td class="grn-batch-col-qty">${batch_qty}</td>
					<td class="grn-batch-col-qty grn-batch-col-accepted">${format_batch_display(row.accepted_qty)}</td>
					<td class="grn-batch-col-qty grn-batch-col-rejected">${rejected}</td>
				</tr>`;
			}

			return `<tr data-batch-index="${index}">
				<td class="grn-batch-col-index">${index + 1}</td>
				<td class="grn-batch-col-batch">
					<span class="grn-batch-badge">${frappe.utils.escape_html(row.batch_no || "")}</span>
				</td>
				<td class="grn-batch-col-qty">${batch_qty}</td>
				<td class="grn-batch-col-input grn-batch-col-accepted">
					<input type="number" class="grn-batch-input grn-batch-accepted-qty"
						data-batch-index="${index}" min="0" max="${flt(row.batch_qty)}"
						step="any" value="${accepted}" placeholder="0">
				</td>
				<td class="grn-batch-col-qty grn-batch-col-rejected">
					<span class="grn-batch-rejected-display" data-batch-index="${index}">${rejected}</span>
				</td>
			</tr>`;
		})
		.join("");

	const totals = get_grn_batch_totals(rows);

	const item_label = frm.doc.production_item
		? frappe.utils.escape_html(frm.doc.production_item)
		: "";
	const subtitle = item_label
		? `${item_label} · ${rows.length} ${__("batch(es)")}`
		: `${rows.length} ${__("batch(es)")}`;

	$wrapper.html(`
		<div class="grn-batch-qc-wrapper">
			<div class="grn-batch-qc-header">
				<span class="grn-batch-qc-title">${__("Batch QC Details")}</span>
				<span class="grn-batch-qc-subtitle">${subtitle}</span>
			</div>
			<div class="table-responsive">
				<table class="grn-batch-table">
					<thead>
						<tr>
							<th class="grn-batch-col-index">#</th>
							<th class="grn-batch-col-batch">${__("Batch No")}</th>
							<th class="grn-batch-col-qty">${__("Batch Qty")}</th>
							<th class="grn-batch-col-input grn-batch-col-accepted">${__("Accepted Qty")}</th>
							<th class="grn-batch-col-input grn-batch-col-rejected">${__("Rejected Qty")}</th>
						</tr>
					</thead>
					<tbody>${table_rows}</tbody>
					<tfoot>
						<tr>
							<td colspan="2" class="grn-batch-total-label">${__("Total")}</td>
							<td class="grn-batch-col-qty grn-batch-total-batch-qty">${format_batch_display(totals.batch_qty)}</td>
							<td class="grn-batch-col-qty grn-batch-col-accepted grn-batch-total-accepted-qty">${format_batch_display(totals.accepted_qty)}</td>
							<td class="grn-batch-col-qty grn-batch-col-rejected grn-batch-total-rejected-qty">${format_batch_display(totals.rejected_qty)}</td>
						</tr>
					</tfoot>
				</table>
			</div>
		</div>
	`);

	if (!is_read_only) {
		bind_grn_batch_html_events(frm, $wrapper);
	}

	ensure_grn_batch_styles();
}

function bind_grn_batch_html_events(frm, $wrapper) {
	$wrapper
		.off("input blur", ".grn-batch-accepted-qty")
		.on("input blur", ".grn-batch-accepted-qty", function () {
			sync_grn_batch_row_inputs(frm, $wrapper, $(this));
		});
}

function calc_rejected_qty(row) {
	return Math.max(flt(row.batch_qty) - flt(row.accepted_qty), 0);
}

function cap_accepted_qty(batch_qty, accepted) {
	const batch_qty_flt = flt(batch_qty);
	let accepted_qty = Math.max(flt(accepted), 0);
	let capped = false;

	if (accepted_qty > batch_qty_flt) {
		accepted_qty = batch_qty_flt;
		capped = true;
	}

	return {
		accepted_qty,
		rejected_qty: batch_qty_flt - accepted_qty,
		capped,
	};
}

function sync_grn_batch_row_inputs(frm, $wrapper, $changed_input) {
	const index = parseInt($changed_input.attr("data-batch-index"), 10);
	const row = frm._grn_batch_rows?.[index];
	if (!row) {
		return;
	}

	const $accepted_input = $wrapper.find(`.grn-batch-accepted-qty[data-batch-index="${index}"]`);
	const capped_values = cap_accepted_qty(row.batch_qty, $accepted_input.val());

	const accepted = capped_values.accepted_qty;
	const rejected = capped_values.rejected_qty;

	$accepted_input.val(format_batch_input(accepted));
	$wrapper
		.find(`.grn-batch-rejected-display[data-batch-index="${index}"]`)
		.text(format_batch_display(rejected));

	if (capped_values.capped) {
		$changed_input.addClass("grn-batch-input-capped");
		setTimeout(() => $changed_input.removeClass("grn-batch-input-capped"), 600);
	}

	row.accepted_qty = accepted;
	row.rejected_qty = rejected;

	const totals = get_grn_batch_totals(frm._grn_batch_rows);
	$wrapper.find(".grn-batch-total-accepted-qty").text(format_batch_display(totals.accepted_qty));
	$wrapper.find(".grn-batch-total-rejected-qty").text(format_batch_display(totals.rejected_qty));

	frm.set_value("batch_qc_json", serialize_batch_qc_rows(frm._grn_batch_rows));
}

function get_grn_batch_totals(rows) {
	return (rows || []).reduce(
		(totals, row) => {
			const accepted = flt(row.accepted_qty);
			totals.batch_qty += flt(row.batch_qty);
			totals.accepted_qty += accepted;
			totals.rejected_qty += calc_rejected_qty(row);
			return totals;
		},
		{ batch_qty: 0, accepted_qty: 0, rejected_qty: 0 }
	);
}

function get_grn_batch_precision() {
	return cint(frappe.defaults.get_default("float_precision")) || 3;
}

function format_batch_display(value) {
	if (value === null || value === undefined || value === "") {
		return "0";
	}
	return String(flt(value, get_grn_batch_precision()));
}

function format_batch_input(value) {
	if (value === null || value === undefined || value === "" || flt(value) === 0) {
		return "";
	}
	return String(flt(value, get_grn_batch_precision()));
}

function ensure_grn_batch_styles() {
	let style = document.getElementById("grn-batch-qc-styles");
	if (!style) {
		style = document.createElement("style");
		style.id = "grn-batch-qc-styles";
		document.head.appendChild(style);
	}

	style.textContent = `
		.grn-batch-qc-wrapper {
			border: 1px solid var(--border-color, #d1d8dd);
			border-radius: var(--border-radius, 8px);
			background: var(--card-bg, #fff);
			overflow: hidden;
			margin: 4px 0 12px;
		}
		.grn-batch-qc-header {
			display: flex;
			align-items: center;
			justify-content: space-between;
			padding: 10px 14px;
			background: var(--subtle-fg, #f7fafc);
			border-bottom: 1px solid var(--border-color, #d1d8dd);
		}
		.grn-batch-qc-title {
			font-size: 13px;
			font-weight: 600;
			color: var(--text-color, #1f272e);
		}
		.grn-batch-qc-subtitle {
			font-size: 12px;
			color: var(--text-muted, #6c7680);
		}
		.grn-batch-table {
			width: 100%;
			margin: 0;
			border-collapse: collapse;
			font-size: 13px;
		}
		.grn-batch-table thead th {
			padding: 8px 12px;
			background: var(--subtle-fg, #f7fafc);
			border-bottom: 1px solid var(--border-color, #d1d8dd);
			font-weight: 600;
			color: var(--text-muted, #6c7680);
			text-transform: uppercase;
			font-size: 11px;
			letter-spacing: 0.03em;
		}
		.grn-batch-table tbody td,
		.grn-batch-table tfoot td {
			padding: 6px 12px;
			border-bottom: 1px solid var(--border-color, #e2e8f0);
			vertical-align: middle;
		}
		.grn-batch-table tbody tr:last-child td {
			border-bottom: none;
		}
		.grn-batch-table tbody tr:hover td {
			background: var(--subtle-fg, #f9fafb);
		}
		.grn-batch-table tfoot td {
			background: var(--subtle-fg, #f7fafc);
			border-top: 2px solid var(--border-color, #d1d8dd);
			border-bottom: none;
			font-weight: 600;
			color: var(--text-color, #1f272e);
		}
		.grn-batch-col-index {
			width: 40px;
			text-align: center;
			color: var(--text-muted, #6c7680);
		}
		.grn-batch-col-batch {
			min-width: 140px;
		}
		.grn-batch-col-qty {
			width: 110px;
			text-align: right;
			font-variant-numeric: tabular-nums;
		}
		.grn-batch-col-input {
			width: 130px;
		}
		.grn-batch-col-accepted {
			background: rgba(34, 197, 94, 0.06);
		}
		.grn-batch-col-rejected {
			background: rgba(239, 68, 68, 0.06);
		}
		.grn-batch-table thead th.grn-batch-col-accepted {
			color: #15803d;
			background: rgba(34, 197, 94, 0.12);
		}
		.grn-batch-table thead th.grn-batch-col-rejected {
			color: #b91c1c;
			background: rgba(239, 68, 68, 0.12);
		}
		.grn-batch-table tfoot td.grn-batch-col-accepted {
			color: #15803d;
		}
		.grn-batch-table tfoot td.grn-batch-col-rejected {
			color: #b91c1c;
		}
		.grn-batch-table tbody td.grn-batch-col-accepted {
			color: #15803d;
			font-weight: 600;
		}
		.grn-batch-table tbody td.grn-batch-col-rejected {
			color: #b91c1c;
			font-weight: 600;
		}
		.grn-batch-rejected-display {
			display: block;
			text-align: right;
			padding: 4px 8px;
			font-variant-numeric: tabular-nums;
		}
		.grn-batch-badge {
			display: inline-block;
			padding: 2px 8px;
			border-radius: 4px;
			background: var(--subtle-accent, #edf2ff);
			color: var(--text-color, #1f272e);
			font-size: 12px;
			font-weight: 500;
		}
		.grn-batch-input {
			width: 100%;
			max-width: 120px;
			margin-left: auto;
			display: block;
			height: 28px;
			padding: 4px 8px;
			border: 1px solid var(--border-color, #d1d8dd);
			border-radius: var(--border-radius-sm, 5px);
			background: var(--control-bg, #fff);
			color: var(--text-color, #1f272e);
			font-size: 13px;
			text-align: right;
			font-variant-numeric: tabular-nums;
			transition: border-color 0.15s, box-shadow 0.15s;
		}
		.grn-batch-input:focus {
			outline: none;
			border-color: var(--primary, #2490ef);
			box-shadow: 0 0 0 2px rgba(36, 144, 239, 0.15);
		}
		.grn-batch-input.grn-batch-input-capped {
			border-color: var(--orange-500, #f59e0b);
			box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.2);
		}
		.grn-batch-input::placeholder {
			color: var(--text-muted, #b8c2cc);
		}
		.grn-batch-accepted-qty {
			border-color: rgba(34, 197, 94, 0.45);
			background: rgba(34, 197, 94, 0.06);
			color: #15803d;
			font-weight: 600;
		}
		.grn-batch-accepted-qty:focus {
			border-color: #22c55e;
			box-shadow: 0 0 0 2px rgba(34, 197, 94, 0.2);
		}
		.grn-batch-rejected-qty:focus {
			border-color: #ef4444;
			box-shadow: 0 0 0 2px rgba(239, 68, 68, 0.2);
		}
		.grn-batch-total-label {
			font-weight: 600;
			color: var(--text-color, #1f272e);
		}
		.grn-batch-empty {
			padding: 16px;
			font-size: 13px;
			text-align: center;
			border: 1px dashed var(--border-color, #d1d8dd);
			border-radius: var(--border-radius, 8px);
			background: var(--subtle-fg, #f7fafc);
		}
	`;
}