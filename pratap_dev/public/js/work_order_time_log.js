// Renders the "Time Log" tab on the Work Order form: batch / job-card / rework
// time-stamps and per-item/operation logs. Read-only report; data from
// pratap_dev.work_order_transfer.get_wo_time_log. Nothing here changes the transfer popup.

frappe.ui.form.on("Work Order", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.docstatus !== 1) {
			return;
		}
		render_time_log(frm);
	},
});

function tl_dt(v) {
	return v ? frappe.datetime.str_to_user(v) : "—";
}

function tl_field(label, value) {
	return `<div style="min-width:200px;">
		<div class="text-muted small">${frappe.utils.escape_html(label)}</div>
		<div style="font-weight:600;">${frappe.utils.escape_html(value || "—")}</div>
	</div>`;
}

function tl_fields_row(pairs) {
	return `<div style="display:flex;flex-wrap:wrap;gap:24px;margin:6px 0 12px;">${pairs
		.map((p) => tl_field(p[0], p[1]))
		.join("")}</div>`;
}

function tl_events_table(events) {
	if (!events || !events.length) {
		return `<div class="text-muted small">${__("No timer / transfer events yet.")}</div>`;
	}
	const rows = events
		.map(
			(e) =>
				`<tr><td>${frappe.utils.escape_html(e.action)}</td><td>${frappe.utils.escape_html(
					tl_dt(e.time)
				)}</td></tr>`
		)
		.join("");
	return `<table class="table table-bordered" style="font-size:13px;margin:6px 0;">
		<thead><tr><th style="width:40%">${__("Event")}</th><th>${__("Time")}</th></tr></thead>
		<tbody>${rows}</tbody></table>`;
}

function tl_transfers_table(transfers) {
	if (!transfers || !transfers.length) {
		return "";
	}
	const rows = transfers
		.map(
			(t) =>
				`<tr><td>${frappe.utils.escape_html(t.batch_no || "")}</td>
				<td class="text-right">${format_number(t.qty)}</td>
				<td>${frappe.utils.escape_html(t.posting_date || "")}</td>
				<td><a href="/app/stock-entry/${encodeURIComponent(t.stock_entry)}" target="_blank" rel="noopener">${frappe.utils.escape_html(
					t.stock_entry
				)}</a></td></tr>`
		)
		.join("");
	return `<div class="text-muted small" style="margin-top:6px;">${__("Transfers")}</div>
	<table class="table table-bordered" style="font-size:13px;margin:4px 0;">
		<thead><tr><th>${__("Batch")}</th><th class="text-right">${__("Qty")}</th><th>${__("Date")}</th><th>${__("Stock Entry")}</th></tr></thead>
		<tbody>${rows}</tbody></table>`;
}

function tl_jc_logs_table(logs) {
	if (!logs || !logs.length) {
		return `<div class="text-muted small">${__("No time logs.")}</div>`;
	}
	const rows = logs
		.map(
			(l) =>
				`<tr>
				<td>${frappe.utils.escape_html(tl_dt(l.from_time))}</td>
				<td>${frappe.utils.escape_html(l.to_time ? tl_dt(l.to_time) : "—")}</td>
				<td class="text-right">${l.mins || 0}</td>
				<td>${frappe.utils.escape_html(l.employee_name || l.employee || "")}</td>
				<td class="text-right">${format_number(l.completed_qty)}</td>
			</tr>`
		)
		.join("");
	return `<table class="table table-bordered" style="font-size:13px;margin:6px 0;">
		<thead><tr><th>${__("From")}</th><th>${__("To")}</th><th class="text-right">${__("Mins")}</th><th>${__("Employee")}</th><th class="text-right">${__("Qty")}</th></tr></thead>
		<tbody>${rows}</tbody></table>`;
}

function tl_section_title(t) {
	return `<h5 style="margin:18px 0 8px;border-bottom:1px solid var(--border-color,#d1d8dd);padding-bottom:6px;">${frappe.utils.escape_html(
		t
	)}</h5>`;
}

function render_time_log(frm) {
	const field = frm.get_field("custom_time_log_html");
	if (!field || !field.$wrapper) {
		return;
	}
	const $w = field.$wrapper;
	$w.html(`<div class="text-muted">${__("Loading time log…")}</div>`);

	frappe.call({
		method: "pratap_dev.work_order_transfer.get_wo_time_log",
		args: { work_order: frm.doc.name },
		callback: (r) => {
			const d = r.message;
			if (!d) {
				$w.html(`<div class="text-muted">${__("No time-log data.")}</div>`);
				return;
			}
			build_time_log(frm, $w, d);
		},
	});
}

function build_time_log(frm, $w, d) {
	// ---- Batch ----
	const b = d.batch || {};
	let html = tl_section_title(__("Batch — Material Transfer"));
	html += `<div style="display:flex;flex-wrap:wrap;gap:24px;margin:6px 0 12px;">
		<div style="display:flex;flex-direction:column;gap:8px;min-width:200px;">
			${tl_field(__("Batch Started At"), tl_dt(b.start_batch))}
			${tl_field(__("Batch Ended At"), tl_dt(b.batch_ended))}
		</div>
		${tl_field(__("First Material Transfer"), tl_dt(b.first_transfer))}
		${tl_field(__("Last Material Transfer"), tl_dt(b.last_transfer))}
	</div>`;
	html += `<div class="text-muted small">${__("Item")}</div>
		<select class="form-control tl-batch-item" style="max-width:420px;margin:4px 0 8px;">
			<option value="">${__("Select an item to see its log…")}</option>
			${(b.items || [])
				.map(
					(it) =>
						`<option value="${it.row}">${frappe.utils.escape_html(it.item_code)} — ${frappe.utils.escape_html(
							it.item_name || ""
						)}</option>`
				)
				.join("")}
		</select>
		<div class="tl-batch-detail"></div>`;

	// ---- Job Cards ----
	const j = d.job_cards || {};
	html += tl_section_title(__("Job Cards / Operations"));
	html += tl_fields_row([
		[__("First Job Card Started"), tl_dt(j.first_started)],
		[__("Last Job Card Submitted"), tl_dt(j.last_submitted)],
	]);
	html += `<div class="text-muted small">${__("Job Card")}</div>
		<select class="form-control tl-jc" style="max-width:420px;margin:4px 0 8px;">
			<option value="">${__("Select a job card to see its log…")}</option>
			${(j.list || [])
				.map(
					(jc) =>
						`<option value="${frappe.utils.escape_html(jc.name)}">${frappe.utils.escape_html(
							jc.operation || jc.name
						)} — ${frappe.utils.escape_html(jc.name)}</option>`
				)
				.join("")}
		</select>
		<div class="tl-jc-detail"></div>`;

	// ---- Rework (single item dropdown across all rework QCs) ----
	const rw = d.rework || {};
	html += tl_section_title(__("Rework"));
	html += tl_fields_row([
		[__("First Rework Transfer"), tl_dt(rw.first_transfer)],
		[__("Last Rework Transfer"), tl_dt(rw.last_transfer)],
	]);
	// Flatten every rework item across all rework QCs into one list; each item keeps
	// its own log, and remembers which QC it came from for the detail panel.
	const rwItems = [];
	(rw.qcs || []).forEach((qc) => {
		(qc.items || []).forEach((it) => {
			rwItems.push(
				Object.assign({}, it, {
					qc_name: qc.name,
					qc_status: qc.status,
					qc_notes: qc.rework_notes,
				})
			);
		});
	});
	if (!rwItems.length) {
		html += `<div class="text-muted small">${__("No rework items.")}</div>`;
	} else {
		html += `<div class="text-muted small">${__("Item")}</div>
			<select class="form-control tl-rw" style="max-width:420px;margin:4px 0 8px;">
				<option value="">${__("Select an item to see its log…")}</option>
				${rwItems
					.map(
						(it, k) =>
							`<option value="${k}">${frappe.utils.escape_html(it.item_code)} — ${frappe.utils.escape_html(
								it.item_name || ""
							)} (${frappe.utils.escape_html(it.qc_name)})</option>`
					)
					.join("")}
			</select>
			<div class="tl-rw-detail"></div>`;
	}

	$w.html(`<div style="padding:4px 2px;">${html}</div>`);

	// ---- wire dropdowns ----
	const itemDetail = (it) =>
		`<div class="text-muted small">${__("Total addition time")}: <b>${it.duration_mins || 0}</b> ${__(
			"min"
		)}</div>${tl_events_table(it.events)}${tl_transfers_table(it.transfers)}`;

	$w.find(".tl-batch-item").on("change", function () {
		const it = (b.items || []).find((x) => x.row === $(this).val());
		$w.find(".tl-batch-detail").html(it ? itemDetail(it) : "");
	});

	$w.find(".tl-jc").on("change", function () {
		const jc = (j.list || []).find((x) => x.name === $(this).val());
		if (!jc) {
			$w.find(".tl-jc-detail").html("");
			return;
		}
		const meta = tl_fields_row([
			[__("Started"), tl_dt(jc.started)],
			[__("Ended"), tl_dt(jc.ended)],
			[__("Submitted"), tl_dt(jc.submitted)],
			[__("Total Time (min)"), String(jc.total_time_in_mins || 0)],
		]);
		$w.find(".tl-jc-detail").html(meta + tl_jc_logs_table(jc.time_logs));
	});

	$w.find(".tl-rw").on("change", function () {
		const it = rwItems[parseInt($(this).val(), 10)];
		if (!it) {
			$w.find(".tl-rw-detail").html("");
			return;
		}
		const ctx = `<div style="display:flex;gap:10px;align-items:center;margin:2px 0 6px;">
				<b>${__("Rework QC")}</b>
				<span class="indicator-pill orange">${frappe.utils.escape_html(it.qc_status || "")}</span>
				<a href="/app/pratap-quality-inspection/${encodeURIComponent(it.qc_name)}" target="_blank" rel="noopener">${frappe.utils.escape_html(
					it.qc_name
				)} ↗</a>
			</div>${it.qc_notes ? `<div class="text-muted small" style="margin-bottom:6px;">${frappe.utils.escape_html(it.qc_notes)}</div>` : ""}`;
		$w.find(".tl-rw-detail").html(ctx + itemDetail(it));
	});
}
