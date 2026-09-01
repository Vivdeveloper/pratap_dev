// Item-by-item, batch-wise Material Transfer for Manufacture, opened from the Work
// Order "Start" button (replaces the bulk transfer popup). Supports Save-as-Draft
// (resume later) and a logged Start/Hold/Submit time-trail per item (no running timer).

frappe.ui.form.on("Work Order", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.docstatus !== 1) {
			return;
		}
		frm.remove_custom_button(__("Start"));
		const pending = (frm.doc.required_items || []).some(
			(r) => flt(r.transferred_qty) < flt(r.required_qty)
		);
		if (!pending) {
			return;
		}
		const btn = frm.add_custom_button(__("Start"), () => open_wo_transfer_dialog(frm));
		btn.addClass("btn-primary");
	},
});

function open_wo_transfer_dialog(frm) {
	frappe.call({
		method: "pratap_dev.work_order_transfer.get_wo_transfer_context",
		args: { work_order: frm.doc.name },
		freeze: true,
		freeze_message: __("Loading items…"),
		callback(r) {
			const ctx = r.message;
			if (!ctx || !(ctx.items || []).length) {
				frappe.msgprint(__("No required items to transfer."));
				return;
			}
			render_wo_transfer_dialog(frm, ctx);
		},
	});
}

function render_wo_transfer_dialog(frm, ctx) {
	const dialog = new frappe.ui.Dialog({
		title: __("Material Transfer for Manufacture — by Item / Batch"),
		size: "extra-large",
		fields: [{ fieldtype: "HTML", fieldname: "body" }],
		primary_action_label: __("Save as Draft"),
		primary_action() {
			save_all_drafts(frm, dialog, ctx);
		},
	});
	const $body = dialog.fields_dict.body.$wrapper;
	$body.html(ctx.items.map((it) => item_block_html(it)).join(""));
	dialog._dirty = false;
	ctx.items.forEach((it) => wire_item_block(frm, dialog, $body, it));

	// "Set Plan" — saves the blueprint once the draft covers every item fully.
	// Manufacturing User: once; Manager/Admin: any time (permission from ctx.can_set_plan).
	dialog.add_custom_action(
		__("Set Plan"),
		() => do_set_plan(frm, dialog, ctx),
		"btn-primary wo-set-plan-btn"
	);
	// Recompute the button's enabled state as the draft changes.
	$body.on("input change", ".wo-b-batch, .wo-b-pkg, .wo-b-units, .wo-b-qty", () =>
		update_set_plan_state(dialog, ctx)
	);
	$body.on("click", ".wo-tr-addbatch, .wo-b-del", () =>
		setTimeout(() => update_set_plan_state(dialog, ctx), 0)
	);

	dialog.show();
	dialog.$wrapper.find(".modal-dialog").css("max-width", "min(1100px, 96vw)");
	update_set_plan_state(dialog, ctx);
	// First Start with a complete FIFO prefill -> persist the blueprint automatically.
	maybe_auto_set_plan(frm, dialog, ctx);

	// Warn before closing (backdrop click / Esc / X) if there are unsaved batch edits,
	// so the operator doesn't lose them by mistake — nudge them to Save as Draft.
	dialog.$wrapper.on("hide.bs.modal", function (e) {
		if (!dialog._dirty || dialog._allow_close) {
			return;
		}
		e.preventDefault();
		frappe.confirm(
			__(
				"You have unsaved changes that will be lost. Use <b>Save as Draft</b> to keep them for later.<br><br>Close without saving?"
			),
			() => {
				dialog._allow_close = true;
				dialog.hide();
			}
		);
	});
}

function item_block_html(it) {
	const full = it.is_full;
	// Light tint for a fully-transferred item, but NO opacity dim — the timer buttons
	// stay active (Start/Stop/Finish remain usable after full transfer).
	const bg = full ? "background:var(--gray-100);" : "background:#fff;";
	const instr = it.instruction_marathi
		? `<div class="wo-tr-instr" style="text-align:center;font-weight:600;margin-bottom:8px;padding-bottom:6px;border-bottom:1px dashed var(--border-color,#d1d8dd);">${frappe.utils.escape_html(
				it.instruction_marathi
		  )}</div>`
		: "";
	return `
	<div class="wo-tr-item" data-row="${it.row}" data-full="${full ? "1" : "0"}"
		style="border:1px solid var(--border-color,#d1d8dd);border-radius:8px;padding:10px 12px;margin-bottom:12px;${bg}">
		${instr}
		<div style="display:flex;flex-wrap:wrap;gap:12px;align-items:center;">
			<b>${frappe.utils.escape_html(it.item_code)}</b>
			<span class="text-muted">${frappe.utils.escape_html(it.item_name || "")}</span>
			<span class="wo-tr-nums" style="margin-left:auto;">
				${__("Required")}: <b>${format_number(it.required_qty)}</b> ·
				${__("Transferred")}: <b class="wo-tr-transferred">${format_number(it.transferred_qty)}</b> ·
				${__("Remaining")}: <b class="wo-tr-remaining">${format_number(it.remaining_qty)}</b> ${it.uom || ""}
			</span>
			${full ? `<span class="indicator-pill green">${__("Fully Transferred")}</span>` : ""}
		</div>
		<div class="wo-tr-taken">${transfers_table_html(it.transfers)}</div>
		${full ? "" : batch_area_html(it)}
		${full ? time_controls_html(it) : ""}
		<div class="wo-tr-log text-muted small" style="margin-top:8px;white-space:pre-line;">${
			it.addition_log
				? "<b>" + __("Log") + ":</b>\n" + frappe.utils.escape_html(it.addition_log)
				: ""
		}</div>
	</div>`;
}

// The item's actual transfers rendered as a table (Batch / Std Pkg / Units / Qty /
// Stock Entry) — same shape as the input rows, sourced from the submitted Stock
// Entries so it's the single "what was transferred" view.
function transfers_table_html(transfers) {
	if (!transfers || !transfers.length) {
		return "";
	}
	const body = transfers
		.map(
			(t) =>
				`<tr>
					<td>${frappe.utils.escape_html(t.batch_no)}</td>
					<td class="text-right">${format_number(t.std_pkg)}</td>
					<td class="text-right">${format_number(t.units)}</td>
					<td class="text-right">${format_number(t.qty)}</td>
					<td><a href="/app/stock-entry/${encodeURIComponent(t.stock_entry)}" target="_blank">${frappe.utils.escape_html(
						t.stock_entry
					)}</a></td>
				</tr>`
		)
		.join("");
	return `
	<div style="margin-top:8px;">
		<div class="small text-muted" style="margin-bottom:4px;"><b>${__("Transferred")}</b></div>
		<table class="table table-bordered" style="font-size:12px;margin-bottom:0;">
			<thead><tr>
				<th>${__("Batch")}</th>
				<th class="text-right">${__("Std Pkg Qty")}</th>
				<th class="text-right">${__("No of Units")}</th>
				<th class="text-right">${__("Qty")}</th>
				<th>${__("Stock Entry")}</th>
			</tr></thead>
			<tbody>${body}</tbody>
		</table>
	</div>`;
}

// Start / Stop time controls + running total. Always shown (even after the item is
// fully transferred) so time logging can continue.
function time_controls_html(it, inline) {
	// `inline` -> rendered on the right end of the batch button row (no top margin, no
	// left auto-push of its own). Standalone -> its own row below (used for fully
	// transferred items which have no Material Transfer button row).
	const wrap = inline ? "" : "margin-top:10px;";
	return `
	<div class="wo-tr-timer" style="display:flex;gap:8px;align-items:center;${wrap}">
		<button class="btn btn-xs btn-success wo-tr-start">▶ ${__("Start")}</button>
		<button class="btn btn-xs btn-danger wo-tr-stop">■ ${__("Stop")}</button>
		<button class="btn btn-xs btn-primary wo-tr-finish">✓ ${__("Finish")}</button>
		<span class="text-muted small" style="margin-left:6px;">${__("Total time")}: <b class="wo-tr-total">${fmt_dur(
			it.duration_mins || 0
		)}</b></span>
	</div>`;
}

// Minutes (float) -> "Xm Ys" for display.
function fmt_dur(mins) {
	const totalSec = Math.round(flt(mins) * 60);
	const m = Math.floor(totalSec / 60);
	const s = totalSec % 60;
	return `${m} ${__("min")} ${s} ${__("sec")}`;
}

function batch_area_html(it) {
	const opts = (it.batches || [])
		.map(
			(b) =>
				`<option value="${frappe.utils.escape_html(b.batch_no)}" data-pkg="${b.std_pkg}" data-avail="${b.available_qty}">${frappe.utils.escape_html(
					b.batch_no
				)} · ${__("std")} ${format_number(b.std_pkg)} (${__("avail")}: ${format_number(
					b.available_qty
				)})</option>`
		)
		.join("");
	return `
	<div class="wo-tr-batches" style="margin-top:10px;">
		<table class="table table-bordered" style="margin-bottom:6px;font-size:13px;">
			<thead><tr>
				<th style="width:34%">${__("Batch")}</th>
				<th style="width:20%">${__("Std Pkg Qty")}</th>
				<th style="width:18%">${__("No of Units")}</th>
				<th style="width:18%">${__("Qty")}</th>
				<th style="width:10%"></th>
			</tr></thead>
			<tbody class="wo-tr-rows"></tbody>
		</table>
		<div style="display:flex;flex-wrap:wrap;align-items:center;gap:8px;">
			<button class="btn btn-xs btn-default wo-tr-addbatch">+ ${__("Add Batch")}</button>
			<button class="btn btn-xs btn-primary wo-tr-transfer">⇄ ${__("Material Transfer")}</button>
			<div style="margin-left:auto;">${time_controls_html(it, true)}</div>
		</div>
		<div class="wo-tr-batchopts" style="display:none;">${opts}</div>
	</div>`;
}

function wire_item_block(frm, dialog, $body, it) {
	const $item = $body.find(`.wo-tr-item[data-row="${it.row}"]`);

	// Start / Stop time controls — wired ALWAYS (continue logging even after the item
	// is fully transferred). Start opens an interval; Stop closes it and the running
	// total (sum of all intervals) is shown.
	$item.on("click", ".wo-tr-start", (e) => {
		e.preventDefault();
		if ($item.find(".wo-tr-start").prop("disabled")) return;
		log_event(frm, $item, it.row, "Start");
	});
	$item.on("click", ".wo-tr-stop", (e) => {
		e.preventDefault();
		if ($item.find(".wo-tr-stop").prop("disabled")) return;
		log_event(frm, $item, it.row, "Stop");
	});
	// Finish -> last click: close any open interval, lock Start/Stop, show final time.
	$item.on("click", ".wo-tr-finish", (e) => {
		e.preventDefault();
		if ($item.find(".wo-tr-finish").prop("disabled")) return;
		frappe.confirm(
			__(
				"Finish time logging for this item? Start / Stop will be disabled and the total time locked."
			),
			() => log_event(frm, $item, it.row, "Finish")
		);
	});
	apply_timer_buttons($item, it.timer_running, it.finished);

	if (it.is_full) {
		return; // no batch selection / transfer once fully transferred
	}
	const optsHtml = $item.find(".wo-tr-batchopts").html();

	const addRow = (data) => {
		const $tr = $(`
			<tr>
				<td><select class="form-control input-xs wo-b-batch"><option value="">${__(
					"Select…"
				)}</option>${optsHtml}</select></td>
				<td><input type="number" class="form-control input-xs wo-b-pkg" min="0" step="any"></td>
				<td><input type="number" class="form-control input-xs wo-b-units text-right" min="0" step="any"></td>
				<td><input type="number" class="form-control input-xs wo-b-qty text-right" min="0" step="any"></td>
				<td><button class="btn btn-xs btn-default wo-b-del">✕</button></td>
			</tr>`);
		$item.find(".wo-tr-rows").append($tr);
		if (data) {
			$tr.find(".wo-b-batch").val(data.batch_no || "");
			$tr.find(".wo-b-pkg").val(data.std_pkg || "");
			$tr.find(".wo-b-units").val(data.units || "");
			$tr.find(".wo-b-qty").val(data.qty || "");
		}
	};

	// Resume a saved draft as-is; otherwise FIFO-prefill the required qty as the default
	// plan (so the planner can just click "Set Plan"). Empty row only if no batches.
	if ((it.draft_rows || []).length) {
		it.draft_rows.forEach((d) => addRow(d));
	} else {
		const prefilled = fifo_prefill_rows(it);
		if (prefilled.length) {
			prefilled.forEach((d) => addRow(d));
		} else {
			addRow();
		}
	}

	$item.on("click", ".wo-tr-addbatch", (e) => {
		e.preventDefault();
		addRow();
	});
	$item.on("click", ".wo-b-del", function (e) {
		e.preventDefault();
		$(this).closest("tr").remove();
	});
	$item.on("change", ".wo-b-batch", function () {
		const $sel = $(this).find("option:selected");
		const pkg = $sel.data("pkg");
		const $tr = $(this).closest("tr");
		// Always reset Std Pkg Qty to the newly selected batch's size (overwrite the
		// previous batch's value); if "Select…" is chosen, clear it.
		$tr.find(".wo-b-pkg").val($(this).val() && pkg ? pkg : "");
		recalc_row($tr, "units");
	});
	$item.on("input", ".wo-b-pkg", function () {
		recalc_row($(this).closest("tr"), "units");
	});
	$item.on("input", ".wo-b-units", function () {
		recalc_row($(this).closest("tr"), "units");
	});
	$item.on("input", ".wo-b-qty", function () {
		recalc_row($(this).closest("tr"), "qty");
	});

	// Track unsaved batch edits so we can warn before an accidental close.
	const markDirty = () => {
		dialog._dirty = true;
	};
	$item.on("input change", ".wo-b-batch, .wo-b-pkg, .wo-b-units, .wo-b-qty", markDirty);
	$item.on("click", ".wo-b-del", markDirty);

	// Material Transfer -> confirm, then create + submit the Stock Entry.
	$item.on("click", ".wo-tr-transfer", (e) => {
		e.preventDefault();
		frappe.confirm(__("Do you want to submit the materials?"), () =>
			submit_item_transfer(frm, dialog, $item, it)
		);
	});
}

// Time logging is only allowed AFTER the item is fully transferred. Before that (and
// once finished), Start/Stop/Finish are all disabled. When full and not finished, the
// Start/Stop sequence applies. The active (enabled) colored button stays bright.
//   not full OR finished -> Start, Stop, Finish all disabled
//   timer running        -> Start disabled, Stop enabled
//   not running          -> Start enabled, Stop disabled (no two in a row)
function apply_timer_buttons($item, running, finished) {
	const full = $item.attr("data-full") === "1";
	if (!full || finished) {
		$item.find(".wo-tr-start, .wo-tr-stop, .wo-tr-finish").prop("disabled", true);
		return;
	}
	$item.find(".wo-tr-start").prop("disabled", !!running);
	$item.find(".wo-tr-stop").prop("disabled", !running);
	$item.find(".wo-tr-finish").prop("disabled", false);
}

// Directional two-way calc, capped at 3 decimals.
function recalc_row($tr, from_field) {
	const pkg = flt($tr.find(".wo-b-pkg").val());
	if (from_field === "qty") {
		const qty = flt($tr.find(".wo-b-qty").val());
		$tr.find(".wo-b-units").val(pkg ? flt(qty / pkg, 3) : 0);
	} else {
		const units = flt($tr.find(".wo-b-units").val());
		$tr.find(".wo-b-qty").val(flt(pkg * units, 3));
	}
}

function collect_rows($item) {
	const rows = [];
	$item.find(".wo-tr-rows tr").each(function () {
		const batch_no = $(this).find(".wo-b-batch").val();
		const std_pkg = flt($(this).find(".wo-b-pkg").val());
		const units = flt($(this).find(".wo-b-units").val());
		const qty = flt($(this).find(".wo-b-qty").val());
		if (batch_no || std_pkg || units) {
			rows.push({ batch_no, std_pkg, units, qty: flt(std_pkg * units, 3) || qty });
		}
	});
	return rows;
}

// FIFO prefill: fill the item's full required qty from the oldest batches first
// (it.batches is already FIFO-ordered from the server — oldest Batch.creation first).
// Each batch contributes up to its available qty; No-of-Units is derived from the
// batch's Std Pkg. This becomes the default plan the planner can just "Set Plan".
function fifo_prefill_rows(it) {
	const rows = [];
	let need = flt(it.required_qty, 3);
	(it.batches || []).forEach((b) => {
		if (need <= 1e-6) return;
		const pkg = flt(b.std_pkg) || 1;
		const avail = flt(b.available_qty, 3);
		if (avail <= 0) return;
		// Never plan more than a batch actually holds: cap units at floor(avail / pkg).
		const availUnits = Math.floor((avail / pkg) * 1000) / 1000;
		if (availUnits <= 0) return;
		let units;
		if (avail < need - 1e-9) {
			units = availUnits; // batch can't finish it — take the whole batch, move on
		} else {
			// This batch can finish the requirement: round the closing units UP so the
			// plan total still meets required despite 3-dp rounding, but not past avail.
			units = Math.ceil((need / pkg) * 1000) / 1000;
			if (units > availUnits) units = availUnits;
		}
		const qty = flt(pkg * units, 3);
		rows.push({ batch_no: b.batch_no, std_pkg: pkg, units: units, qty: qty });
		need = flt(need - qty, 3);
	});
	return rows;
}

function set_log($item, log) {
	$item
		.find(".wo-tr-log")
		.html(log ? "<b>" + __("Log") + ":</b>\n" + frappe.utils.escape_html(log) : "");
}

function log_event(frm, $item, row_name, action) {
	frappe.call({
		method: "pratap_dev.work_order_transfer.log_addition_event",
		args: { work_order: frm.doc.name, row_name, action },
		callback(r) {
			if (!r.message) return;
			set_log($item, r.message.addition_log);
			$item.find(".wo-tr-total").text(fmt_dur(r.message.duration_mins || 0));
			apply_timer_buttons($item, r.message.running, r.message.finished);
		},
	});
}

// The draft covers every item's required qty (each item already full, or its rows sum
// to >= required) — i.e. the plan is complete enough to save.
function plan_is_complete(dialog, ctx) {
	const $body = dialog.fields_dict.body.$wrapper;
	return ctx.items.every((it) => {
		const $item = $body.find(`.wo-tr-item[data-row="${it.row}"]`);
		if (it.is_full || $item.attr("data-full") === "1") {
			return true;
		}
		const sum = collect_rows($item).reduce((a, r) => a + flt(r.qty), 0);
		return flt(sum, 3) + 1e-6 >= flt(it.required_qty, 3);
	});
}

function build_plan(dialog, ctx) {
	const plan = {};
	ctx.items.forEach((it) => {
		const $item = dialog.fields_dict.body.$wrapper.find(`.wo-tr-item[data-row="${it.row}"]`);
		plan[it.row] = collect_rows($item);
	});
	return plan;
}

// Enable "Set Plan" only when the user is allowed AND the draft covers every item.
function update_set_plan_state(dialog, ctx) {
	const $btn = dialog.$wrapper.find(".wo-set-plan-btn");
	if (!$btn.length) {
		return;
	}
	$btn.prop("disabled", !(ctx.can_set_plan && plan_is_complete(dialog, ctx)));
}

// On the first Start (no plan yet), the FIFO-prefilled rows are already a complete plan,
// so save that blueprint automatically. It does not use up the Manufacturing User's one
// manual save — they (and the manager) can still edit and re-save afterwards.
function maybe_auto_set_plan(frm, dialog, ctx) {
	if (ctx.plan_set || !ctx.can_set_plan || !plan_is_complete(dialog, ctx)) {
		return;
	}
	frappe.call({
		method: "pratap_dev.work_order_transfer.set_transfer_plan",
		args: { work_order: frm.doc.name, plan: JSON.stringify(build_plan(dialog, ctx)), auto: 1 },
		callback: (r) => {
			if (r.message && r.message.plan_set) {
				ctx.plan_set = true;
				ctx.can_set_plan = r.message.can_set_plan;
				update_set_plan_state(dialog, ctx);
				frappe.show_alert(
					{ message: __("Plan saved automatically (FIFO) — you can still edit and re-save."), indicator: "green" },
					5
				);
			}
		},
	});
}

function do_set_plan(frm, dialog, ctx) {
	const plan = build_plan(dialog, ctx);
	frappe.confirm(
		__("Set this as the plan (blueprint) for the whole Work Order?"),
		() => {
			frappe.call({
				method: "pratap_dev.work_order_transfer.set_transfer_plan",
				args: { work_order: frm.doc.name, plan: JSON.stringify(plan) },
				freeze: true,
				freeze_message: __("Saving plan…"),
				callback(r) {
					if (!r.message) return;
					ctx.plan_set = true;
					ctx.can_set_plan = r.message.can_set_plan;
					frappe.show_alert({ message: __("Plan set."), indicator: "green" }, 5);
					update_set_plan_state(dialog, ctx);
				},
			});
		}
	);
}

function save_all_drafts(frm, dialog, ctx) {
	const drafts = {};
	ctx.items.forEach((it) => {
		if (it.is_full) {
			return;
		}
		const $item = dialog.fields_dict.body.$wrapper.find(`.wo-tr-item[data-row="${it.row}"]`);
		drafts[it.row] = collect_rows($item);
	});
	frappe.call({
		method: "pratap_dev.work_order_transfer.save_transfer_draft",
		args: { work_order: frm.doc.name, drafts: JSON.stringify(drafts) },
		freeze: true,
		freeze_message: __("Saving draft…"),
		callback() {
			dialog._dirty = false; // saved -> no longer unsaved
			frappe.show_alert(
				{ message: __("Draft saved — you can resume later."), indicator: "green" },
				5
			);
		},
	});
}

function submit_item_transfer(frm, dialog, $item, it) {
	const batches = collect_rows($item).filter(
		(r) => r.batch_no && r.std_pkg > 0 && r.units > 0
	);
	if (!batches.length) {
		frappe.msgprint(__("Pick at least one batch with Std Pkg Qty and No of Units."));
		return;
	}
	frappe.call({
		method: "pratap_dev.work_order_transfer.transfer_item_for_manufacture",
		args: {
			work_order: frm.doc.name,
			row_name: it.row,
			batches: JSON.stringify(batches),
		},
		freeze: true,
		freeze_message: __("Creating Stock Entry…"),
		callback(r) {
			const res = r.message;
			if (!res) return;
			frappe.show_alert(
				{ message: __("Transferred. Stock Entry {0} submitted.", [res.stock_entry]), indicator: "green" },
				5
			);
			$item.find(".wo-tr-transferred").text(format_number(res.transferred_qty));
			$item.find(".wo-tr-remaining").text(format_number(res.remaining_qty));
			// Refresh the "Transferred" table (all Stock Entries for this item).
			$item.find(".wo-tr-taken").html(transfers_table_html(res.transfers));
			if (res.duration_mins != null) {
				$item.find(".wo-tr-total").text(fmt_dur(res.duration_mins));
			}
			if (res.is_full) {
				// Fully transferred -> now the Start/Stop time log becomes available.
				$item.attr("data-full", "1");
				// The timer was rendered INLINE on the batch button row, so removing the
				// batch area drops it. Re-add it as a standalone timer (like a full item
				// on load) so Start/Stop/Finish stay visible without needing a reopen.
				$item.find(".wo-tr-batches").remove();
				if (!$item.find(".wo-tr-timer").length) {
					$item.find(".wo-tr-taken").after(time_controls_html(it));
				}
				if (res.duration_mins != null) {
					$item.find(".wo-tr-total").text(fmt_dur(res.duration_mins));
				}
				$item.css({ background: "var(--gray-100)" });
				$item
					.find(".wo-tr-nums")
					.after(`<span class="indicator-pill green">${__("Fully Transferred")}</span>`);
				apply_timer_buttons($item, false, false); // enable Start
			} else {
				// leftover remains -> reset the batch rows for another transfer
				$item.find(".wo-tr-rows").empty();
				$item.find(".wo-tr-addbatch").click();
			}
			frm.reload_doc();
		},
	});
}
