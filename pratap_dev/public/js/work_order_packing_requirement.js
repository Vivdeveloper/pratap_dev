// Render the "Packing Material Requirement" table into the Work Order's Packing Requirement
// tab — mirrors the Forecast Club table. Display only (no material transfer). Pack Qty in
// Source comes from the WO's source warehouse, computed server-side.

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
			draw_packing_table(field.$wrapper, r.message || {});
		},
	});
}

function draw_packing_table($wrapper, data) {
	const rows = data.rows || [];
	const fmt = (v) => frappe.format(flt(v), { fieldtype: "Float" });
	const esc = (v) => frappe.utils.escape_html(v || "");

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

	const fg = esc(data.fg || "");
	const body = rows
		.map((d, i) => {
			const fgCell =
				i === 0
					? `<td rowspan="${rows.length}" style="padding:6px 10px;vertical-align:middle;font-weight:600;">${fg}</td>`
					: "";
			return `<tr>
				${fgCell}
				${td(esc(d.packed_good_name || d.packed_good))}
				${td(fmt(d.filling_capacity), true)}
				${td(esc(d.packing_material))}
				${td(fmt(d.qty_sf), true)}
				${td(fmt(d.source_qty), true)}
				${td(`<b>${fmt(d.mr_qty)}</b>`, true)}
			</tr>`;
		})
		.join("");

	const src = esc(data.source_warehouse || __("Not set"));
	$wrapper.html(`
		<div style="margin-bottom:6px;">
			<span style="font-weight:600;">${__("Packing Material Requirement")}</span>
			<span class="text-muted" style="margin-left:10px;">${__("Source Warehouse")}: ${src}</span>
		</div>
		<div class="table-responsive">
			<table class="table table-bordered" style="margin:0;font-size:12px;">
				<thead><tr style="background:#f0f0f0;">
					${th(__("FG"))}
					${th(__("Packed Good (SF)"))}
					${th(__("Filling Capacity"), true)}
					${th(__("Packing Material"))}
					${th(__("Qty (SF)"), true)}
					${th(__("Pack Qty in Source"), true)}
					${th(__("MR Qty"), true)}
				</tr></thead>
				<tbody>${body}</tbody>
			</table>
		</div>
	`);
}
