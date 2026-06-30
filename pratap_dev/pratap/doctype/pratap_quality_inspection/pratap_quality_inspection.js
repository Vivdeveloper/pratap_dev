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
		if (frm.doc.reference_type === "GRN" && frm.doc.reference_name) {
			load_grn_batch_details(frm);
		} else {
			render_grn_batch_html(frm);
		}
		expand_batch_html_full_width(frm);
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
				render_batch_readings_matrix(frm);
			});
		}
	},

	quality_inspection_template(frm) {
		frm.call("get_item_specification_details").then(() => {
			frm.refresh_field("readings");
			render_batch_readings_matrix(frm);
		});
	},

	readings_add(frm) {
		render_batch_readings_matrix(frm);
	},

	readings_remove(frm) {
		render_batch_readings_matrix(frm);
	},

	validate(frm) {
		warn_incomplete_batch_readings(frm);
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
		if (flt(frm.doc.inspected_qty) <= 0) {
			frappe.throw({
				title: __("Validation Error"),
				message: __("Inspected Qty must be greater than 0."),
			});
		}
		if (frm.doc.reference_type === "GRN" && frm._grn_batch_rows?.length) {
			frm.doc.batch_qc_json = serialize_batch_qc_rows(frm._grn_batch_rows);
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

frappe.ui.form.on("Pratap Quality Inspection Reading", {
	observe_value(frm, cdt, cdn) {
		update_reading_row_status(frm, cdt, cdn);
	},

	min_value(frm, cdt, cdn) {
		update_reading_row_status(frm, cdt, cdn);
	},

	max_value(frm, cdt, cdn) {
		update_reading_row_status(frm, cdt, cdn);
	},

	manual_inspection(frm, cdt, cdn) {
		update_reading_row_status(frm, cdt, cdn);
	},

	numeric(frm, cdt, cdn) {
		update_reading_row_status(frm, cdt, cdn);
	},

	reading_value(frm, cdt, cdn) {
		update_reading_row_status(frm, cdt, cdn);
	},

	status(frm, cdt, cdn) {
		update_document_status_from_readings(frm);
	},
});

function update_reading_row_status(frm, cdt, cdn) {
	if (frm.doc.docstatus >= 1) {
		return;
	}

	const row = locals[cdt][cdn];
	if (!row) {
		return;
	}

	if (cint(row.manual_inspection)) {
		update_document_status_from_readings(frm);
		return;
	}

	if (cint(row.formula_based_criteria)) {
		return;
	}

	let status = "";

	if (cint(row.numeric)) {
		const observe_value = (row.observe_value || "").trim();
		if (observe_value) {
			const parsed_value = flt(observe_value);
			const min_value = flt(row.min_value);
			const max_value = flt(row.max_value);
			status =
				parsed_value >= min_value && parsed_value <= max_value
					? "Accepted"
					: "Rejected";
		}
	} else {
		const observe_value = (row.observe_value || "").trim();
		const reading_value = observe_value || (row.reading_value || "").trim();
		const accepted_value = (row.value || "").trim();
		if (reading_value && accepted_value) {
			status =
				reading_value.toLowerCase() === accepted_value.toLowerCase()
					? "Accepted"
					: "Rejected";
		}
	}

	if (row.status !== status) {
		frappe.model.set_value(cdt, cdn, "status", status);
	}

	update_document_status_from_readings(frm);
}

function update_document_status_from_readings(frm) {
	if (frm.doc.docstatus >= 1 || frm.doc.status === "Rework") {
		return;
	}

	const readings = frm.doc.readings || [];
	if (!readings.length) {
		return;
	}

	const statuses = readings.map((row) => (row.status || "").trim());
	let parent_status = "Pending";

	if (statuses.some((status) => status === "Rejected")) {
		parent_status = "Rejected";
	} else if (statuses.every((status) => status === "Accepted")) {
		parent_status = "Accepted";
	}

	if ((frm.doc.status || "").trim() !== parent_status) {
		frm.set_value("status", parent_status);
	}
}

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

function toggle_supplier_coa(frm) {
	const show_supplier_coa = frm.doc.reference_type === "GRN";
	const grid = frm.fields_dict.readings?.grid;
	if (!grid) {
		return;
	}

	grid.visible_columns = [];
	grid.set_column_disp("supplier_coa", show_supplier_coa);
}

function expand_batch_html_full_width(frm) {
	const field = frm.fields_dict.batch_html;
	if (!field?.$wrapper || frm.doc.reference_type !== "GRN") {
		return;
	}

	const $section = field.$wrapper.closest(".form-section");
	if (!$section.length) {
		return;
	}

	$section.find("> .section-body > .form-column").addClass("col-sm-12").removeClass("col-sm-6");
	$section.find(".column-break").hide();
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

function parse_batch_qc_json_rows(value) {
	if (!value) {
		return [];
	}
	try {
		const parsed = JSON.parse(value);
		return Array.isArray(parsed) ? parsed : [];
	} catch {
		return [];
	}
}

function serialize_batch_qc_rows(rows) {
	return JSON.stringify(
		(rows || []).map((row) => {
			const normalized = normalize_grn_batch_row(row);
			return {
				batch_no: normalized.batch_no,
				batch_qty: normalized.batch_qty,
				standard_pkg_qty: normalized.standard_pkg_qty,
				no_of_unit: normalized.no_of_unit,
				accepted_unit: normalized.accepted_unit,
				rejected_unit: normalized.rejected_unit,
				accepted_qty: normalized.accepted_qty,
				rejected_qty: normalized.rejected_qty,
			};
		})
	);
}

function get_row_batch_units(row) {
	const packing = flt(row.standard_pkg_qty) || 1;
	if (row.no_of_unit !== null && row.no_of_unit !== undefined && row.no_of_unit !== "") {
		return flt(row.no_of_unit);
	}
	return flt(row.batch_qty) / packing;
}

function normalize_grn_batch_row(row, saved = {}) {
	const batch_qty = flt(row.batch_qty);
	const standard_pkg_qty = flt(row.standard_pkg_qty ?? saved.standard_pkg_qty) || 1;
	const no_of_unit = get_row_batch_units({
		...row,
		standard_pkg_qty,
		no_of_unit: row.no_of_unit ?? saved.no_of_unit,
	});

	let accepted_unit = 0;
	if (saved.accepted_unit !== null && saved.accepted_unit !== undefined && saved.accepted_unit !== "") {
		accepted_unit = flt(saved.accepted_unit);
	} else if (
		saved.accepted_qty !== null &&
		saved.accepted_qty !== undefined &&
		saved.accepted_qty !== ""
	) {
		accepted_unit = standard_pkg_qty ? flt(saved.accepted_qty) / standard_pkg_qty : 0;
	} else if (
		row.accepted_unit !== null &&
		row.accepted_unit !== undefined &&
		row.accepted_unit !== ""
	) {
		accepted_unit = flt(row.accepted_unit);
	} else if (row.accepted_qty !== null && row.accepted_qty !== undefined && row.accepted_qty !== "") {
		accepted_unit = standard_pkg_qty ? flt(row.accepted_qty) / standard_pkg_qty : 0;
	}

	const normalized = {
		batch_no: row.batch_no,
		batch_qty,
		standard_pkg_qty,
		no_of_unit,
		accepted_unit,
	};

	return sync_row_from_accepted_unit(normalized).row;
}

function sync_row_from_accepted_unit(row) {
	const standard_pkg_qty = flt(row.standard_pkg_qty) || 1;
	const batch_units = get_row_batch_units(row);
	let accepted_unit = Math.max(flt(row.accepted_unit), 0);
	let capped = false;

	if (accepted_unit > batch_units) {
		accepted_unit = batch_units;
		capped = true;
	}

	const rejected_unit = batch_units - accepted_unit;
	const accepted_qty = standard_pkg_qty * accepted_unit;
	const rejected_qty = standard_pkg_qty * rejected_unit;

	row.accepted_unit = accepted_unit;
	row.rejected_unit = rejected_unit;
	row.accepted_qty = accepted_qty;
	row.rejected_qty = rejected_qty;

	return { row, capped };
}

function load_grn_batch_from_json(frm) {
	if (frm.doc.reference_type !== "GRN") {
		clear_grn_batch_html(frm);
		return;
	}

	frm._grn_batch_rows = parse_batch_qc_json_rows(frm.doc.batch_qc_json).map((row) =>
		normalize_grn_batch_row(row)
	);

	render_grn_batch_html(frm);
}

function load_grn_batch_details(frm) {
	if (frm.doc.reference_type !== "GRN" || !frm.doc.reference_name) {
		clear_grn_batch_html(frm);
		return;
	}

	if (frm.doc.docstatus >= 1) {
		load_grn_batch_from_json(frm);
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

			frm._grn_batch_rows = batches.map((row) => normalize_grn_batch_row(row, saved_rows[row.batch_no] || {}));

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
		render_batch_readings_matrix(frm);
		return;
	}

	const rows = frm._grn_batch_rows || [];
	if (!rows.length) {
		const message = frm.doc.reference_name
			? __("No batch details found for this GRN item.")
			: __("Select a GRN reference to load batch details.");
		$wrapper.html(`<div class="grn-batch-empty text-muted">${message}</div>`);
		ensure_grn_batch_styles();
		render_batch_readings_matrix(frm);
		return;
	}

	const is_read_only = frm.doc.docstatus === 1;
	const table_rows = rows
		.map((row, index) => {
			const standard_pkg_qty = format_batch_display(row.standard_pkg_qty);
			const no_of_unit = format_batch_display(get_row_batch_units(row));
			const accepted_unit = format_batch_input(row.accepted_unit);
			const rejected_unit = format_batch_display(row.rejected_unit);
			const accepted_qty = format_batch_display(row.accepted_qty);
			const rejected_qty = format_batch_display(calc_rejected_qty(row));
			const batch_qty = format_batch_display(row.batch_qty);

			if (is_read_only) {
				return `<tr data-batch-index="${index}">
					<td class="grn-batch-col-index">${index + 1}</td>
					<td class="grn-batch-col-batch">
						<span class="grn-batch-badge">${frappe.utils.escape_html(row.batch_no || "")}</span>
					</td>
					<td class="grn-batch-col-qty">${batch_qty}</td>
					<td class="grn-batch-col-qty">${standard_pkg_qty}</td>
					<td class="grn-batch-col-qty">${no_of_unit}</td>
					<td class="grn-batch-col-qty grn-batch-col-accepted">${format_batch_display(row.accepted_unit)}</td>
					<td class="grn-batch-col-qty grn-batch-col-rejected">${rejected_unit}</td>
					<td class="grn-batch-col-qty grn-batch-col-accepted">${accepted_qty}</td>
					<td class="grn-batch-col-qty grn-batch-col-rejected">${rejected_qty}</td>
				</tr>`;
			}

			return `<tr data-batch-index="${index}">
				<td class="grn-batch-col-index">${index + 1}</td>
				<td class="grn-batch-col-batch">
					<span class="grn-batch-badge">${frappe.utils.escape_html(row.batch_no || "")}</span>
				</td>
				<td class="grn-batch-col-qty">${batch_qty}</td>
				<td class="grn-batch-col-qty">${standard_pkg_qty}</td>
				<td class="grn-batch-col-qty">${no_of_unit}</td>
				<td class="grn-batch-col-input grn-batch-col-accepted">
					<input type="number" class="grn-batch-input grn-batch-accepted-unit"
						data-batch-index="${index}" min="0" max="${flt(get_row_batch_units(row))}"
						step="any" value="${accepted_unit}" placeholder="0">
				</td>
				<td class="grn-batch-col-qty grn-batch-col-rejected">
					<span class="grn-batch-rejected-unit-display" data-batch-index="${index}">${rejected_unit}</span>
				</td>
				<td class="grn-batch-col-qty grn-batch-col-accepted">
					<span class="grn-batch-accepted-qty-display" data-batch-index="${index}">${accepted_qty}</span>
				</td>
				<td class="grn-batch-col-qty grn-batch-col-rejected">
					<span class="grn-batch-rejected-display" data-batch-index="${index}">${rejected_qty}</span>
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
							<th class="grn-batch-col-qty">${__("Standard Pkg Qty")}</th>
							<th class="grn-batch-col-qty">${__("No of Unit")}</th>
							<th class="grn-batch-col-input grn-batch-col-accepted">${__("Accepted Unit")}</th>
							<th class="grn-batch-col-input grn-batch-col-rejected">${__("Rejected Unit")}</th>
							<th class="grn-batch-col-input grn-batch-col-accepted">${__("Accepted Qty")}</th>
							<th class="grn-batch-col-input grn-batch-col-rejected">${__("Rejected Qty")}</th>
						</tr>
					</thead>
					<tbody>${table_rows}</tbody>
					<tfoot>
						<tr>
							<td colspan="2" class="grn-batch-total-label">${__("Total")}</td>
							<td class="grn-batch-col-qty grn-batch-total-batch-qty">${format_batch_display(totals.batch_qty)}</td>
							<td class="grn-batch-col-qty"></td>
							<td class="grn-batch-col-qty grn-batch-total-no-of-unit">${format_batch_display(totals.no_of_unit)}</td>
							<td class="grn-batch-col-qty grn-batch-col-accepted grn-batch-total-accepted-unit">${format_batch_display(totals.accepted_unit)}</td>
							<td class="grn-batch-col-qty grn-batch-col-rejected grn-batch-total-rejected-unit">${format_batch_display(totals.rejected_unit)}</td>
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

	expand_batch_html_full_width(frm);
	ensure_grn_batch_styles();
	render_batch_readings_matrix(frm);
}

function bind_grn_batch_html_events(frm, $wrapper) {
	$wrapper
		.off("input blur", ".grn-batch-accepted-unit")
		.on("input blur", ".grn-batch-accepted-unit", function () {
			sync_grn_batch_row_inputs(frm, $wrapper, $(this));
		});
}

function calc_rejected_qty(row) {
	return flt(row.rejected_qty);
}

function sync_grn_batch_row_inputs(frm, $wrapper, $changed_input) {
	const index = parseInt($changed_input.attr("data-batch-index"), 10);
	const row = frm._grn_batch_rows?.[index];
	if (!row) {
		return;
	}

	const $accepted_input = $wrapper.find(`.grn-batch-accepted-unit[data-batch-index="${index}"]`);
	row.accepted_unit = $accepted_input.val();
	const { row: synced_row, capped } = sync_row_from_accepted_unit(row);

	$accepted_input.val(format_batch_input(synced_row.accepted_unit));
	$wrapper
		.find(`.grn-batch-rejected-unit-display[data-batch-index="${index}"]`)
		.text(format_batch_display(synced_row.rejected_unit));
	$wrapper
		.find(`.grn-batch-accepted-qty-display[data-batch-index="${index}"]`)
		.text(format_batch_display(synced_row.accepted_qty));
	$wrapper
		.find(`.grn-batch-rejected-display[data-batch-index="${index}"]`)
		.text(format_batch_display(synced_row.rejected_qty));

	if (capped) {
		$changed_input.addClass("grn-batch-input-capped");
		setTimeout(() => $changed_input.removeClass("grn-batch-input-capped"), 600);
	}

	frm._grn_batch_rows[index] = synced_row;

	const totals = get_grn_batch_totals(frm._grn_batch_rows);
	$wrapper.find(".grn-batch-total-no-of-unit").text(format_batch_display(totals.no_of_unit));
	$wrapper.find(".grn-batch-total-accepted-unit").text(format_batch_display(totals.accepted_unit));
	$wrapper.find(".grn-batch-total-rejected-unit").text(format_batch_display(totals.rejected_unit));
	$wrapper.find(".grn-batch-total-accepted-qty").text(format_batch_display(totals.accepted_qty));
	$wrapper.find(".grn-batch-total-rejected-qty").text(format_batch_display(totals.rejected_qty));

	frm.set_value("batch_qc_json", serialize_batch_qc_rows(frm._grn_batch_rows));
}

function get_grn_batch_totals(rows) {
	return (rows || []).reduce(
		(totals, row) => {
			totals.batch_qty += flt(row.batch_qty);
			totals.no_of_unit += get_row_batch_units(row);
			totals.accepted_unit += flt(row.accepted_unit);
			totals.rejected_unit += flt(row.rejected_unit);
			totals.accepted_qty += flt(row.accepted_qty);
			totals.rejected_qty += calc_rejected_qty(row);
			return totals;
		},
		{
			batch_qty: 0,
			no_of_unit: 0,
			accepted_unit: 0,
			rejected_unit: 0,
			accepted_qty: 0,
			rejected_qty: 0,
		}
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
			table-layout: fixed;
		}
		.grn-batch-table thead th {
			padding: 8px 6px;
			background: var(--subtle-fg, #f7fafc);
			border-bottom: 1px solid var(--border-color, #d1d8dd);
			font-weight: 600;
			color: var(--text-muted, #6c7680);
			text-transform: uppercase;
			font-size: 10px;
			letter-spacing: 0.02em;
			white-space: nowrap;
			overflow: hidden;
			text-overflow: ellipsis;
		}
		.grn-batch-table tbody td,
		.grn-batch-table tfoot td {
			padding: 6px 6px;
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
			width: 3%;
			text-align: center;
			color: var(--text-muted, #6c7680);
		}
		.grn-batch-col-batch {
			width: 14%;
			white-space: nowrap;
			overflow: hidden;
			text-overflow: ellipsis;
		}
		.grn-batch-col-qty {
			width: 10%;
			text-align: right;
			font-variant-numeric: tabular-nums;
		}
		.grn-batch-col-input {
			width: 11%;
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
		.grn-batch-rejected-display,
		.grn-batch-rejected-unit-display,
		.grn-batch-accepted-qty-display {
			display: block;
			text-align: right;
			padding: 4px 8px;
			font-variant-numeric: tabular-nums;
		}
		.grn-batch-badge {
			display: inline-block;
			max-width: 100%;
			padding: 2px 8px;
			border-radius: 4px;
			background: var(--subtle-accent, #edf2ff);
			color: var(--text-color, #1f272e);
			font-size: 12px;
			font-weight: 500;
			white-space: nowrap;
			overflow: hidden;
			text-overflow: ellipsis;
			vertical-align: middle;
		}
		.grn-batch-input {
			width: 100%;
			max-width: none;
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
		.grn-batch-accepted-unit {
			border-color: rgba(34, 197, 94, 0.45);
			background: rgba(34, 197, 94, 0.06);
			color: #15803d;
			font-weight: 600;
		}
		.grn-batch-accepted-unit:focus {
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

// ---------------------------------------------------------------------------
// Batch-wise Readings matrix
// Rows = parameters (readings), Columns = batches (from Batch QC Details).
// Each cell writes the observed value into the parameter row's reading_<col>
// field AND is mirrored into batch_readings_json. Status is a manual dropdown
// per batch column. Manual Inspection stays on the parameter row and applies
// to every batch in that row.
// ---------------------------------------------------------------------------

const BATCH_READINGS_MAX = 10; // reading_1 .. reading_10

function get_batch_readings_columns(frm) {
	return (frm._grn_batch_rows || [])
		.map((row) => row.batch_no)
		.filter(Boolean)
		.slice(0, BATCH_READINGS_MAX);
}

function parse_batch_readings_rows(value) {
	if (!value) {
		return [];
	}
	try {
		const parsed = JSON.parse(value);
		return Array.isArray(parsed) ? parsed : [];
	} catch {
		return [];
	}
}

function parse_batch_readings_map(value) {
	return Object.fromEntries(
		parse_batch_readings_rows(value).map((row) => [row.batch_no, row])
	);
}

function get_reading_criteria_text(reading) {
	if (cint(reading.formula_based_criteria)) {
		return __("Formula based");
	}
	if (cint(reading.numeric)) {
		const has_min = ![undefined, null, ""].includes(reading.min_value);
		const has_max = ![undefined, null, ""].includes(reading.max_value);
		if (!has_min && !has_max) {
			return "";
		}
		return `${__("Min")} <b>${flt(reading.min_value)}</b> · ${__("Max")} <b>${flt(
			reading.max_value
		)}</b>`;
	}
	const value = (reading.value || "").trim();
	return value ? `${__("Expected")}: <b>${frappe.utils.escape_html(value)}</b>` : "";
}

// Numeric pass rule: value within [min, max]. A bound of 0 means "no limit"
// (e.g. Max 0 => no upper bound), matching how Batch QC criteria are configured.
function bread_param_status(reading, value) {
	const v = (value === null || value === undefined ? "" : String(value)).trim();

	if (cint(reading.numeric)) {
		if (!v) return ""; // not entered yet
		const parsed = flt(v);
		const min_value = flt(reading.min_value);
		const max_value = flt(reading.max_value);
		const ok_min = min_value === 0 || parsed >= min_value;
		const ok_max = max_value === 0 || parsed <= max_value;
		return ok_min && ok_max ? "Accepted" : "Rejected";
	}

	if (cint(reading.formula_based_criteria)) {
		// Formula cannot be evaluated client-side; accept once a value is present.
		return v ? "Accepted" : "";
	}

	// Text/value based
	const expected = (reading.value || "").trim();
	if (!v) return "";
	if (!expected) return "Accepted";
	return v.toLowerCase() === expected.toLowerCase() ? "Accepted" : "Rejected";
}

// Batch status from all its parameter readings:
// any Rejected -> Rejected, any blank -> Pending, else Accepted.
function bread_batch_status(frm, col) {
	const readings = frm.doc.readings || [];
	const field = `reading_${col + 1}`;
	let has_blank = false;
	for (const reading of readings) {
		const status = bread_param_status(reading, reading[field]);
		if (status === "Rejected") return "Rejected";
		if (status === "") has_blank = true;
	}
	return has_blank ? "Pending" : "Accepted";
}

function bread_collect_values(frm, col) {
	const readings = frm.doc.readings || [];
	const field = `reading_${col + 1}`;
	const values = {};
	readings.forEach((reading) => {
		values[reading.specification || reading.name] = reading[field] || "";
	});
	return values;
}

function bread_get_rows(frm) {
	return parse_batch_readings_rows(frm.doc.batch_readings_json);
}

// Merge a patch for one batch into batch_readings_json, keeping batch order.
function bread_upsert(frm, batch_no, patch) {
	const batches = get_batch_readings_columns(frm);
	const map = parse_batch_readings_map(frm.doc.batch_readings_json);
	map[batch_no] = Object.assign({ batch_no: batch_no, status: "", added: false, values: {} }, map[batch_no] || {}, patch);
	const rows = batches.map((b) => map[b] || { batch_no: b, status: "", added: false, values: {} });
	frm.set_value("batch_readings_json", JSON.stringify(rows));
}

function bread_added_batches(frm) {
	const map = parse_batch_readings_map(frm.doc.batch_readings_json);
	return get_batch_readings_columns(frm).filter((b) => map[b] && map[b].added);
}

function bread_pending_batches(frm) {
	const map = parse_batch_readings_map(frm.doc.batch_readings_json);
	return get_batch_readings_columns(frm).filter(
		(b) => !(map[b] && map[b].added) || !["Accepted", "Rejected"].includes((map[b].status || "").trim())
	);
}

// Roll batch statuses up to the document (top) status automatically.
function bread_roll_up_parent_status(frm) {
	if (frm.doc.docstatus >= 1 || (frm.doc.status || "").trim() === "Rework") {
		return;
	}
	const batches = get_batch_readings_columns(frm);
	if (!batches.length) return;

	const map = parse_batch_readings_map(frm.doc.batch_readings_json);
	const statuses = batches.map((b) => (map[b] && map[b].added ? (map[b].status || "").trim() : ""));

	let parent_status = "Pending";
	if (statuses.some((s) => s === "Rejected")) {
		parent_status = "Rejected";
	} else if (statuses.length && statuses.every((s) => s === "Accepted")) {
		parent_status = "Accepted";
	}

	if ((frm.doc.status || "").trim() !== parent_status) {
		frm.set_value("status", parent_status);
	}
}

// Save-time warning: list batches whose readings have not been added yet.
function warn_incomplete_batch_readings(frm) {
	if (frm.doc.reference_type !== "GRN" || frm.doc.docstatus >= 1) {
		return;
	}
	const batches = get_batch_readings_columns(frm);
	if (!batches.length || !(frm.doc.readings || []).length) {
		return;
	}
	const pending = bread_pending_batches(frm);
	if (pending.length) {
		frappe.msgprint({
			title: __("Incomplete Batch Readings"),
			indicator: "orange",
			message: __("Readings not added for {0} of {1} batch(es): {2}. Please add readings for every batch.", [
				pending.length,
				batches.length,
				pending.join(", "),
			]),
		});
	}
}

function render_batch_readings_matrix(frm) {
	const field = frm.fields_dict.batch_readings_html;
	if (!field?.$wrapper) {
		return;
	}
	const $wrapper = field.$wrapper;

	if (frm.doc.reference_type !== "GRN") {
		$wrapper.empty();
		return;
	}

	const batches = get_batch_readings_columns(frm);
	const readings = frm.doc.readings || [];

	if (!batches.length || !readings.length) {
		const message = !batches.length
			? __("Add batches in Batch QC Details to enter batch-wise readings.")
			: __("Select a Quality Inspection Template to load parameters.");
		$wrapper.html(`<div class="grn-batch-empty text-muted">${message}</div>`);
		ensure_grn_batch_styles();
		ensure_batch_readings_styles();
		return;
	}

	const map = parse_batch_readings_map(frm.doc.batch_readings_json);
	const is_read_only = frm.doc.docstatus === 1;

	// Default selected batch -> first batch that has not been added yet.
	if (!frm._bread_selected || !batches.includes(frm._bread_selected)) {
		frm._bread_selected = batches.find((b) => !(map[b] && map[b].added)) || batches[0];
	}
	const selected = frm._bread_selected;
	const col = batches.indexOf(selected);

	// --- Batch selector dropdown ---
	const options = batches
		.map((b) => {
			const entry = map[b];
			let tag = " •"; // pending
			if (entry && entry.added) {
				tag = entry.status === "Rejected" ? "  ✗ Rejected" : entry.status === "Accepted" ? "  ✓ Accepted" : "  • Pending";
			}
			return `<option value="${frappe.utils.escape_html(b)}"${b === selected ? " selected" : ""}>${frappe.utils.escape_html(
				b
			)}${tag}</option>`;
		})
		.join("");

	const dropdown_html = `
		<div class="bread-picker">
			<label class="bread-picker-label">${__("Select Batch")}</label>
			<select class="bread-batch-select" ${is_read_only ? "disabled" : ""}>${options}</select>
			${is_read_only ? "" : `<button class="btn btn-primary btn-sm bread-add-btn">${__("Add / Update Batch")}</button>`}
		</div>`;

	// --- Entry table for the selected batch ---
	const entry_rows = readings
		.map((reading, rIdx) => {
			const reading_field = `reading_${col + 1}`;
			const cell_val = frappe.utils.escape_html(reading[reading_field] || "");
			const name = frappe.utils.escape_html(reading.specification || __("(unnamed)"));
			const is_numeric = cint(reading.numeric);
			const type_label = cint(reading.formula_based_criteria) ? __("Formula") : is_numeric ? __("Numeric") : __("Text");
			const type_badge = `<span class="bread-type-badge ${is_numeric ? "bread-type-numeric" : "bread-type-text"}">${type_label}</span>`;
			const criteria = get_reading_criteria_text(reading);
			const criteria_html = criteria
				? `<span class="bread-param-criteria">${criteria}</span>`
				: `<span class="bread-param-criteria text-muted">${__("No criteria")}</span>`;
			const input_html = is_read_only
				? `<span class="bread-readonly-value">${cell_val || "—"}</span>`
				: `<input type="text" class="bread-input bread-entry-input" data-row="${rIdx}" value="${cell_val}" placeholder="${__(
						"Enter value"
				  )}">`;
			return `<tr>
				<td class="bread-entry-param"><span class="bread-param-name">${name}</span> ${type_badge}</td>
				<td class="bread-entry-criteria">${criteria_html}</td>
				<td class="bread-entry-value">${input_html}</td>
			</tr>`;
		})
		.join("");

	const entry_html = `
		<div class="bread-entry-card">
			<div class="bread-entry-head">
				<span class="bread-card-batch-label">${__("Readings for Batch")}</span>
				<span class="grn-batch-badge">${frappe.utils.escape_html(selected)}</span>
			</div>
			<table class="bread-entry-table">
				<thead><tr>
					<th>${__("Parameter")}</th>
					<th>${__("Criteria")}</th>
					<th>${__("Observed Value")}</th>
				</tr></thead>
				<tbody>${entry_rows}</tbody>
			</table>
		</div>`;

	// --- Summary ("niche") table of all batches ---
	const summary_rows = batches
		.map((b, i) => {
			const entry = map[b];
			const added = !!(entry && entry.added);
			const status = (entry && entry.status) || "";
			const status_cell = added ? batch_status_badge(status) : `<span class="bread-status-badge bread-badge-pending">${__("Not Added")}</span>`;
			const actions = is_read_only
				? ""
				: `<button class="btn btn-xs btn-default bread-edit-btn" data-batch="${frappe.utils.escape_html(b)}">${__("Edit")}</button>
				   ${added ? `<button class="btn btn-xs btn-default bread-remove-btn" data-batch="${frappe.utils.escape_html(b)}">${__("Clear")}</button>` : ""}`;
			return `<tr class="${added ? "" : "bread-row-pending"}">
				<td class="grn-batch-col-index">${i + 1}</td>
				<td><span class="grn-batch-badge">${frappe.utils.escape_html(b)}</span></td>
				<td>${status_cell}</td>
				<td class="bread-summary-actions">${actions}</td>
			</tr>`;
		})
		.join("");

	const added_count = bread_added_batches(frm).length;
	const summary_html = `
		<div class="bread-summary-card">
			<div class="grn-batch-qc-header">
				<span class="grn-batch-qc-title">${__("Batch Readings Status")}</span>
				<span class="grn-batch-qc-subtitle">${added_count} / ${batches.length} ${__("added")}</span>
			</div>
			<table class="grn-batch-table bread-summary-table">
				<thead><tr>
					<th class="grn-batch-col-index">#</th>
					<th>${__("Batch No")}</th>
					<th>${__("Status")}</th>
					<th>${__("Action")}</th>
				</tr></thead>
				<tbody>${summary_rows}</tbody>
			</table>
		</div>`;

	const subtitle = `${readings.length} ${__("parameter(s)")} · ${batches.length} ${__("batch(es)")}`;

	$wrapper.html(`
		<div class="grn-batch-qc-wrapper bread-wrapper">
			<div class="grn-batch-qc-header">
				<span class="grn-batch-qc-title">${__("Batch-wise Readings")}</span>
				<span class="grn-batch-qc-subtitle">${subtitle}</span>
			</div>
			<div class="bread-body">
				${dropdown_html}
				${entry_html}
				${summary_html}
			</div>
		</div>
	`);

	if (!is_read_only) {
		bind_batch_readings_events(frm, $wrapper);
	}

	expand_batch_readings_full_width(frm);
	ensure_grn_batch_styles();
	ensure_batch_readings_styles();
}

function batch_status_badge(status) {
	if (!status) {
		return `<span class="text-muted">—</span>`;
	}
	let cls = "bread-badge-pending";
	if (status === "Accepted") cls = "bread-badge-accepted";
	else if (status === "Rejected") cls = "bread-badge-rejected";
	return `<span class="bread-status-badge ${cls}">${__(status)}</span>`;
}

function bind_batch_readings_events(frm, $wrapper) {
	// Switch selected batch
	$wrapper
		.off("change", ".bread-batch-select")
		.on("change", ".bread-batch-select", function () {
			frm._bread_selected = $(this).val();
			render_batch_readings_matrix(frm);
		});

	// Live-write observed values into the parameter row's reading_<col> field
	$wrapper
		.off("change", ".bread-entry-input")
		.on("change", ".bread-entry-input", function () {
			const rIdx = parseInt($(this).attr("data-row"), 10);
			set_batch_reading_value(frm, rIdx, $(this).val());
		});

	// Add / update the selected batch into the summary table
	$wrapper
		.off("click", ".bread-add-btn")
		.on("click", ".bread-add-btn", function () {
			add_or_update_batch(frm);
		});

	// Edit an existing batch -> select it
	$wrapper
		.off("click", ".bread-edit-btn")
		.on("click", ".bread-edit-btn", function () {
			frm._bread_selected = $(this).attr("data-batch");
			render_batch_readings_matrix(frm);
		});

	// Clear a batch's readings
	$wrapper
		.off("click", ".bread-remove-btn")
		.on("click", ".bread-remove-btn", function () {
			remove_batch_readings(frm, $(this).attr("data-batch"));
		});
}

function set_batch_reading_value(frm, rIdx, value) {
	const batches = get_batch_readings_columns(frm);
	const col = batches.indexOf(frm._bread_selected);
	const reading = (frm.doc.readings || [])[rIdx];
	if (col < 0 || !reading) {
		return;
	}
	frappe.model.set_value(reading.doctype, reading.name, `reading_${col + 1}`, value);
}

function add_or_update_batch(frm) {
	const batches = get_batch_readings_columns(frm);
	const selected = frm._bread_selected;
	const col = batches.indexOf(selected);
	if (col < 0) {
		return;
	}

	const status = bread_batch_status(frm, col);
	bread_upsert(frm, selected, {
		status: status,
		added: true,
		values: bread_collect_values(frm, col),
	});
	bread_roll_up_parent_status(frm);

	// Move to the next batch that still needs readings.
	const next = bread_pending_batches(frm)[0];
	frm._bread_selected = next || selected;

	render_batch_readings_matrix(frm);
	frappe.show_alert({
		message: __("Batch {0} saved ({1})", [selected, status]),
		indicator: status === "Rejected" ? "red" : status === "Accepted" ? "green" : "orange",
	});
}

function remove_batch_readings(frm, batch_no) {
	const batches = get_batch_readings_columns(frm);
	const col = batches.indexOf(batch_no);
	if (col >= 0) {
		(frm.doc.readings || []).forEach((reading) => {
			frappe.model.set_value(reading.doctype, reading.name, `reading_${col + 1}`, "");
		});
	}
	bread_upsert(frm, batch_no, { status: "", added: false, values: {} });
	bread_roll_up_parent_status(frm);
	frm._bread_selected = batch_no;
	render_batch_readings_matrix(frm);
}

function expand_batch_readings_full_width(frm) {
	const field = frm.fields_dict.batch_readings_html;
	if (!field?.$wrapper || frm.doc.reference_type !== "GRN") {
		return;
	}
	const $section = field.$wrapper.closest(".form-section");
	if (!$section.length) {
		return;
	}
	$section.find("> .section-body > .form-column").addClass("col-sm-12").removeClass("col-sm-6");
	$section.find(".column-break").hide();
}

function ensure_batch_readings_styles() {
	let style = document.getElementById("batch-readings-styles");
	if (!style) {
		style = document.createElement("style");
		style.id = "batch-readings-styles";
		document.head.appendChild(style);
	}

	style.textContent = `
		.bread-cards {
			display: grid;
			grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
			gap: 12px;
			padding: 12px;
		}
		.bread-card {
			border: 1px solid var(--border-color, #d1d8dd);
			border-radius: var(--border-radius, 8px);
			background: var(--card-bg, #fff);
			display: flex;
			flex-direction: column;
			overflow: hidden;
		}
		.bread-card.bread-card-accepted {
			border-color: rgba(34, 197, 94, 0.5);
		}
		.bread-card.bread-card-rejected {
			border-color: rgba(239, 68, 68, 0.5);
		}
		.bread-card-head {
			display: flex;
			align-items: center;
			gap: 8px;
			padding: 10px 12px;
			background: var(--subtle-fg, #f7fafc);
			border-bottom: 1px solid var(--border-color, #d1d8dd);
		}
		.bread-card-batch-label {
			font-size: 11px;
			font-weight: 600;
			text-transform: uppercase;
			letter-spacing: 0.03em;
			color: var(--text-muted, #6c7680);
		}
		.bread-card-body {
			padding: 4px 12px;
		}
		.bread-param-block {
			padding: 9px 0;
			border-bottom: 1px solid var(--border-color, #eef1f4);
		}
		.bread-param-block:last-child {
			border-bottom: none;
		}
		.bread-param-top {
			display: flex;
			align-items: center;
			flex-wrap: wrap;
			gap: 6px;
			margin-bottom: 6px;
		}
		.bread-param-name {
			font-weight: 600;
			font-size: 13px;
			color: var(--text-color, #1f272e);
		}
		.bread-type-badge {
			display: inline-block;
			padding: 1px 7px;
			border-radius: 4px;
			font-size: 10px;
			font-weight: 600;
			text-transform: uppercase;
			letter-spacing: 0.02em;
		}
		.bread-type-numeric {
			background: rgba(36, 144, 239, 0.12);
			color: #1d6fc0;
		}
		.bread-type-text {
			background: rgba(124, 58, 237, 0.12);
			color: #6d28d9;
		}
		.bread-manual-check {
			display: inline-flex;
			align-items: center;
			gap: 4px;
			margin: 0;
			padding: 1px 7px;
			border-radius: 4px;
			background: rgba(245, 158, 11, 0.12);
			color: #b45309;
			font-size: 10px;
			font-weight: 600;
			text-transform: uppercase;
			letter-spacing: 0.02em;
			cursor: pointer;
			user-select: none;
		}
		.bread-manual-check input {
			margin: 0;
			cursor: pointer;
		}
		.bread-param-bottom {
			display: flex;
			align-items: center;
			justify-content: space-between;
			gap: 10px;
		}
		.bread-param-criteria {
			font-size: 12px;
			color: var(--text-muted, #6c7680);
			white-space: nowrap;
			font-variant-numeric: tabular-nums;
		}
		.bread-param-criteria b {
			color: var(--text-color, #1f272e);
		}
		.bread-input {
			width: 130px;
			flex: 0 0 130px;
			height: 30px;
			padding: 4px 10px;
			border: 1px solid var(--border-color, #d1d8dd);
			border-radius: var(--border-radius-sm, 5px);
			background: var(--control-bg, #fff);
			color: var(--text-color, #1f272e);
			font-size: 13px;
			text-align: right;
			transition: border-color 0.15s, box-shadow 0.15s;
		}
		.bread-input:focus {
			outline: none;
			border-color: var(--primary, #2490ef);
			box-shadow: 0 0 0 2px rgba(36, 144, 239, 0.15);
		}
		.bread-readonly-value {
			min-width: 130px;
			text-align: right;
			font-weight: 600;
			color: var(--text-color, #1f272e);
			font-variant-numeric: tabular-nums;
		}
		.bread-card-foot {
			display: flex;
			align-items: center;
			justify-content: space-between;
			gap: 10px;
			padding: 10px 12px;
			background: var(--subtle-fg, #f7fafc);
			border-top: 1px solid var(--border-color, #d1d8dd);
			margin-top: auto;
		}
		.bread-card-foot-label {
			font-size: 12px;
			font-weight: 600;
			color: var(--text-color, #1f272e);
		}
		.bread-status-select {
			width: 150px;
			height: 30px;
			padding: 3px 8px;
			border: 1px solid var(--border-color, #d1d8dd);
			border-radius: var(--border-radius-sm, 5px);
			background: var(--control-bg, #fff);
			color: var(--text-color, #1f272e);
			font-size: 12px;
		}
		.bread-status-badge {
			display: inline-block;
			padding: 2px 12px;
			border-radius: 10px;
			font-size: 12px;
			font-weight: 600;
		}
		.bread-badge-accepted {
			background: rgba(34, 197, 94, 0.12);
			color: #15803d;
		}
		.bread-badge-rejected {
			background: rgba(239, 68, 68, 0.12);
			color: #b91c1c;
		}
		.bread-badge-pending {
			background: rgba(245, 158, 11, 0.12);
			color: #b45309;
		}
		.bread-body {
			padding: 12px;
			display: flex;
			flex-direction: column;
			gap: 14px;
		}
		.bread-picker {
			display: flex;
			align-items: center;
			gap: 10px;
			flex-wrap: wrap;
		}
		.bread-picker-label {
			font-size: 12px;
			font-weight: 600;
			text-transform: uppercase;
			letter-spacing: 0.03em;
			color: var(--text-muted, #6c7680);
			margin: 0;
		}
		.bread-batch-select {
			min-width: 220px;
			height: 32px;
			padding: 4px 10px;
			border: 1px solid var(--border-color, #d1d8dd);
			border-radius: var(--border-radius-sm, 5px);
			background: var(--control-bg, #fff);
			color: var(--text-color, #1f272e);
			font-size: 13px;
		}
		.bread-entry-card,
		.bread-summary-card {
			border: 1px solid var(--border-color, #d1d8dd);
			border-radius: var(--border-radius, 8px);
			background: var(--card-bg, #fff);
			overflow: hidden;
		}
		.bread-entry-head {
			display: flex;
			align-items: center;
			gap: 8px;
			padding: 10px 12px;
			background: var(--subtle-fg, #f7fafc);
			border-bottom: 1px solid var(--border-color, #d1d8dd);
		}
		.bread-entry-table,
		.bread-summary-table {
			width: 100%;
			border-collapse: collapse;
			font-size: 13px;
		}
		.bread-entry-table th,
		.bread-entry-table td {
			padding: 8px 12px;
			border-bottom: 1px solid var(--border-color, #eef1f4);
			text-align: left;
			vertical-align: middle;
		}
		.bread-entry-table thead th {
			background: var(--subtle-fg, #f7fafc);
			font-size: 10px;
			text-transform: uppercase;
			letter-spacing: 0.02em;
			color: var(--text-muted, #6c7680);
		}
		.bread-entry-value {
			text-align: right;
			width: 180px;
		}
		.bread-entry-value .bread-input {
			width: 150px;
		}
		.bread-row-pending td {
			background: rgba(245, 158, 11, 0.05);
		}
		.bread-summary-actions {
			display: flex;
			gap: 6px;
		}
	`;
}