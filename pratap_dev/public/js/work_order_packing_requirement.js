// Render the "Packing Material Requirement" table into the Work Order's Packing Requirement
// tab. Available Qty in Source comes from the WO's source warehouse; MR Week 1-4 show the
// Material Request raised per week-of-month for this WO (server-side). The operator may edit
// MR Qty per row and click "Create Packing Material Request" to raise ONE draft Material
// Request (Material Transfer) for any row short of stock in the source warehouse.

frappe.ui.form.on("Work Order", {
	refresh(frm) {
		render_wo_packing_requirement(frm);
	},
});

function render_wo_packing_requirement(frm) {
	const field = frm.fields_dict.custom_packing_requirement_html;
	if (!field || !field.$wrapper) {
		return;
	}
	if (frm.is_new() || !frm.doc.name || !frm.doc.production_item) {
		field.$wrapper.html(
			`<div class="text-muted" style="padding:8px">${__("Save the Work Order to see its packing material requirement.")}</div>`
		);
		return;
	}

	frappe.call({
		method: "pratap_dev.work_order_packing.get_wo_packing_requirement",
		args: { work_order: frm.doc.name },
		callback(r) {
			draw_packing_table(frm, field.$wrapper, r.message || {});
		},
	});
}

function draw_packing_table(frm, $wrapper, data) {
	const rows = data.rows || [];
	const fmt = (v) => frappe.format(flt(v), { fieldtype: "Float" });
	const esc = (v) => frappe.utils.escape_html(v || "");
	// Editable + button only on a live (non-cancelled) Work Order.
	const editable = frm.doc.docstatus !== 2;

	if (!rows.length) {
		$wrapper.html(
			`<div class="text-muted" style="padding:8px">${__("No packing material details found for {0}.", [esc(data.fg)])}</div>`
		);
		return;
	}

	const th = (label, right) =>
		`<th class="${right ? "text-right" : ""}" style="padding:6px 10px;">${label}</th>`;
	const td = (val, right) =>
		`<td class="${right ? "text-right" : ""}" style="padding:6px 10px;">${val}</td>`;
	// Light-green header/cell for the "In Week" (received) columns, so they stand out next to
	// the "MR Week" (requested) columns they are interleaved with.
	const IN_GREEN = "background:#e6f4ea;";
	const thg = (label) =>
		`<th class="text-right" style="padding:6px 10px;${IN_GREEN}">${label}</th>`;
	const tdg = (val) =>
		`<td class="text-right" style="padding:6px 10px;${IN_GREEN}">${val}</td>`;

	const fg = esc(data.fg || "");
	const body = rows
		.map((d, i) => {
			const fgCell =
				i === 0
					? `<td rowspan="${rows.length}" style="padding:6px 10px;vertical-align:middle;font-weight:600;">${fg}</td>`
					: "";
			// Qty to Pack — blank, editable. On entry, MR Qty = max(0, Qty to Pack - Available).
			const pack_cell = editable
				? `<td class="text-right" style="padding:4px 6px;">
						<input type="number" class="form-control input-xs wo-pk-topack text-right"
							min="0" step="any" style="min-width:90px;"
							data-pk="${esc(d.packing_material)}" data-avail="${flt(d.source_qty)}" value="">
					</td>`
				: td("", true);
			const mrq_cell = editable
				? `<td class="text-right" style="padding:4px 6px;">
						<input type="number" class="form-control input-xs wo-pk-mrqty text-right"
							min="0" step="any" style="min-width:90px;"
							data-pk="${esc(d.packing_material)}" value="${flt(d.mr_qty)}">
					</td>`
				: td(`<b>${fmt(d.mr_qty)}</b>`, true);
			return `<tr>
				${fgCell}
				${td(esc(d.packed_good_name || d.packed_good))}
				${td(fmt(d.filling_capacity), true)}
				${td(esc(d.packing_material))}
				${td(fmt(d.qty_sf), true)}
				${td(fmt(d.source_qty), true)}
				${pack_cell}
				${mrq_cell}
				${td(fmt(d.mr_w1), true)}
				${tdg(fmt(d.in_w1))}
				${td(fmt(d.mr_w2), true)}
				${tdg(fmt(d.in_w2))}
				${td(fmt(d.mr_w3), true)}
				${tdg(fmt(d.in_w3))}
				${td(fmt(d.mr_w4), true)}
				${tdg(fmt(d.in_w4))}
			</tr>`;
		})
		.join("");

	const src = esc(data.source_warehouse || __("Not set"));
	const button_html = editable
		? `<div style="margin-top:8px;">
				<button class="btn btn-primary btn-sm wo-pk-create-mr">${__("Create Packing Material Request")}</button>
				<span class="text-muted" style="margin-left:10px;font-size:11px;">${__(
					"Rows where MR Qty exceeds Available Qty in Source raise one draft Material Request (Material Transfer) into the source warehouse."
				)}</span>
			</div>`
		: "";

	$wrapper.html(`
		<div style="margin-bottom:6px;">
			<span style="font-weight:600;">${__("Packing Material Requirement")}</span>
			<span class="text-muted" style="margin-left:10px;">${__("Source Warehouse")}: ${src}</span>
		</div>
		<div class="table-responsive pratap-scroll">
			<table class="table table-bordered" style="margin:0;font-size:12px;white-space:nowrap;min-width:max-content;">
				<thead><tr style="background:#f0f0f0;">
					${th(__("FG"))}
					${th(__("Packed Good (SF)"))}
					${th(__("Filling Capacity"), true)}
					${th(__("Packing Material"))}
					${th(__("Qty (SF)"), true)}
					${th(__("Available Qty in Source"), true)}
					${th(__("Qty to Pack"), true)}
					${th(__("MR Qty"), true)}
					${th(__("MR Week 1"), true)}
					${thg(__("In Week 1"))}
					${th(__("MR Week 2"), true)}
					${thg(__("In Week 2"))}
					${th(__("MR Week 3"), true)}
					${thg(__("In Week 3"))}
					${th(__("MR Week 4"), true)}
					${thg(__("In Week 4"))}
				</tr></thead>
				<tbody>${body}</tbody>
			</table>
		</div>
		${button_html}
	`);

	if (editable) {
		$wrapper.find(".wo-pk-create-mr").on("click", () => create_packing_material_request(frm, $wrapper));

		// Typing a "Qty to Pack" auto-updates that row's MR Qty = max(0, Qty to Pack - Available).
		// MR Qty stays editable, so the user may still override it afterwards.
		$wrapper.find(".wo-pk-topack").on("input", function () {
			const $row = $(this).closest("tr");
			const to_pack = flt($(this).val());
			const available = flt($(this).data("avail"));
			const mr_qty = Math.max(0, to_pack - available);
			$row.find(".wo-pk-mrqty").val(mr_qty);
		});
	}
}

function create_packing_material_request(frm, $wrapper) {
	const rows = [];
	$wrapper.find(".wo-pk-mrqty").each(function () {
		const pk = $(this).data("pk");
		const mr_qty = flt($(this).val());
		if (pk && mr_qty > 0) {
			rows.push({ packing_material: pk, mr_qty: mr_qty });
		}
	});

	if (!rows.length) {
		frappe.msgprint(__("Enter an MR Qty on at least one row first."));
		return;
	}

	frappe.call({
		method: "pratap_dev.work_order_packing.create_packing_material_request",
		args: { work_order: frm.doc.name, rows: JSON.stringify(rows) },
		freeze: true,
		freeze_message: __("Checking stock and creating Material Request..."),
		callback(r) {
			const res = r.message || {};
			if (res.created) {
				frappe.show_alert({ message: res.message, indicator: "green" }, 7);
				frappe.set_route("Form", "Material Request", res.created);
			} else {
				frappe.msgprint(res.message || __("Nothing to request."));
			}
		},
	});
}
