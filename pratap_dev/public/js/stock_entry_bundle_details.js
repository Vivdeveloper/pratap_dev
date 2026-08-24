// Show, per Stock Entry row, which batches a Serial and Batch Bundle contains and how
// much each holds — both in the pen-icon row detail form (HTML section) and on hover
// over the bundle cell in the items grid (popover).

let _se_bundle_cache = {};

function se_fetch_bundle_batches(bundle) {
	if (!bundle) {
		return Promise.resolve([]);
	}
	if (_se_bundle_cache[bundle]) {
		return Promise.resolve(_se_bundle_cache[bundle]);
	}
	return frappe
		.call({ method: "pratap_dev.stock_entry_bundle.get_bundle_batches", args: { bundle } })
		.then((r) => {
			const rows = (r && r.message) || [];
			_se_bundle_cache[bundle] = rows;
			return rows;
		});
}

function se_render_bundle_html(bundle, rows) {
	if (!bundle) {
		return '<div class="text-muted small">' + __("No Serial and Batch Bundle set.") + "</div>";
	}
	if (!rows || !rows.length) {
		return (
			'<div class="text-muted small">' +
			__("Bundle {0} has no batch details.", [frappe.utils.escape_html(bundle)]) +
			"</div>"
		);
	}
	const cell = "padding:4px 8px;border-top:1px solid var(--border-color,#d1d8dd);";
	const body = rows
		.map(
			(r) =>
				"<tr><td style=\"" +
				cell +
				'">' +
				frappe.utils.escape_html(r.batch_no) +
				'</td><td style="' +
				cell +
				'text-align:right;">' +
				format_number(r.qty) +
				"</td></tr>"
		)
		.join("");
	return (
		'<div style="border:1px solid var(--border-color,#d1d8dd);border-radius:6px;overflow:hidden;max-width:360px;">' +
		'<div style="padding:6px 8px;background:var(--subtle-fg,#f7fafc);font-weight:600;font-size:12px;">' +
		__("Batches in {0}", [frappe.utils.escape_html(bundle)]) +
		"</div>" +
		'<table style="width:100%;border-collapse:collapse;font-size:12px;">' +
		'<thead><tr><th style="padding:4px 8px;text-align:left;">' +
		__("Batch") +
		'</th><th style="padding:4px 8px;text-align:right;">' +
		__("Qty") +
		"</th></tr></thead><tbody>" +
		body +
		"</tbody></table></div>"
	);
}

frappe.ui.form.on("Stock Entry Detail", {
	// Pen-icon row detail form: render the bundle's batches into the HTML field.
	form_render(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const grid_row = frm.fields_dict.items.grid.grid_rows_by_docname[cdn];
		const field =
			grid_row && grid_row.grid_form && grid_row.grid_form.fields_dict.custom_bundle_batches_html;
		if (!field) {
			return;
		}
		if (!row.serial_and_batch_bundle) {
			field.$wrapper.html(se_render_bundle_html(null, []));
			return;
		}
		field.$wrapper.html('<div class="text-muted small">' + __("Loading…") + "</div>");
		se_fetch_bundle_batches(row.serial_and_batch_bundle).then((rows) => {
			field.$wrapper.html(se_render_bundle_html(row.serial_and_batch_bundle, rows));
		});
	},
});

frappe.ui.form.on("Stock Entry", {
	refresh(frm) {
		// Bundles can change after re-allocation, so drop the cache each render.
		_se_bundle_cache = {};
		setup_bundle_grid_hover(frm);
	},
});

// Lazy hover popover on the "Serial and Batch Bundle" cells in the items grid.
function setup_bundle_grid_hover(frm) {
	const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
	if (!grid || grid._bundle_hover_bound) {
		return;
	}
	grid.wrapper.on(
		"mouseenter",
		'.grid-row [data-fieldname="serial_and_batch_bundle"]',
		function () {
			const $cell = $(this);
			if ($cell.data("bundle-popover-init")) {
				return;
			}
			const cdn = $cell.closest(".grid-row").attr("data-name");
			const row = cdn && locals["Stock Entry Detail"] && locals["Stock Entry Detail"][cdn];
			if (!row || !row.serial_and_batch_bundle) {
				return;
			}
			$cell.data("bundle-popover-init", true);
			se_fetch_bundle_batches(row.serial_and_batch_bundle).then((rows) => {
				if (!$cell.popover) {
					// Fallback to a plain-text tooltip if popover isn't available.
					$cell.attr(
						"title",
						rows.map((r) => r.batch_no + ": " + format_number(r.qty)).join("\n")
					);
					return;
				}
				$cell.popover({
					trigger: "hover",
					html: true,
					placement: "top",
					container: "body",
					content: se_render_bundle_html(row.serial_and_batch_bundle, rows),
				});
				$cell.popover("show");
			});
		}
	);
	grid._bundle_hover_bound = true;
}
