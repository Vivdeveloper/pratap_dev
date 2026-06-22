frappe.provide("pratap_dev.last_buying_rates");

pratap_dev.last_buying_rates = {
	normalize_workflow_state(state) {
		return (state || "").replace(/\s+/g, " ").trim().toLowerCase();
	},

	should_show(frm) {
		if (!frm.doc.items?.length) {
			return false;
		}

		const state = this.normalize_workflow_state(frm.doc.workflow_state);
		if (state === "draft" || state === "waiting for approval") {
			return true;
		}

		return frm.doc.docstatus === 0 && !state;
	},

	show(frm, options = {}) {
		const item_codes = (frm.doc.items || []).map((row) => row.item_code).filter(Boolean);
		if (!item_codes.length) {
			return Promise.resolve();
		}

		const rate_column_label = options.rate_column_label || __("Rate");
		const current_po = options.current_po ?? frm.doc.name ?? "";

		return frappe
			.call({
				method: "get_last_buying_rate",
				args: {
					supplier: frm.doc.supplier,
					item_codes: JSON.stringify(item_codes),
					current_po,
					doc: frm.doc,
				},
				freeze: true,
				freeze_message: __("Loading Last Buying Rates..."),
			})
			.then((response) => {
				const rows = this.enrich_rows(response.message || [], frm);
				if (!rows.length) {
					return;
				}
				return this.open_dialog(rows, rate_column_label);
			});
	},

	enrich_rows(rows, frm) {
		const item_map = {};
		(frm.doc.items || []).forEach((item) => {
			if (item.item_code) {
				item_map[item.item_code] = item;
			}
		});

		return rows.map((row) => {
			const item = item_map[row.item_code] || {};
			return {
				...row,
				supplier_item:
					row.supplier_item ||
					item.supplier_part_no ||
					item.item_name ||
					item.item_code ||
					row.item_code,
				po_rate: row.po_rate ?? item.rate,
				po_uom: row.po_uom || item.uom,
			};
		});
	},

	open_dialog(rows, rate_column_label) {
		return new Promise((resolve) => {
			let settled = false;
			const finish = () => {
				if (settled) {
					return;
				}
				settled = true;
				resolve();
			};

			const table_rows = rows
				.map((row) => {
					return `<tr>
					<td>${frappe.utils.escape_html(row.item_code || "")}</td>
					<td>${frappe.utils.escape_html(row.supplier_item || "")}</td>
					<td class="text-right">${this.format_rate(row.po_rate)}</td>
					<td class="text-right">${this.format_rate(row.last_buying_rate)}</td>
					<td>${frappe.utils.escape_html(row.last_uom || "")}</td>
					<td>${frappe.utils.escape_html(row.last_supplier || "")}</td>
				</tr>`;
				})
				.join("");

			const dialog = new frappe.ui.Dialog({
				title: __("Please check the last buying rates and UOM"),
				size: "large",
				fields: [
					{
						fieldtype: "HTML",
						fieldname: "rates_html",
						options: `<div class="table-responsive">
							<table class="table table-bordered">
								<thead>
									<tr>
										<th>${__("Item Code")}</th>
										<th>${__("Supplier Item")}</th>
										<th class="text-right">${rate_column_label}</th>
										<th class="text-right">${__("Last Buying Rate")}</th>
										<th>${__("Last UOM")}</th>
										<th>${__("Last Supplier")}</th>
									</tr>
								</thead>
								<tbody>${table_rows}</tbody>
							</table>
						</div>`,
					},
				],
				primary_action_label: __("OK"),
				primary_action() {
					dialog.hide();
					finish();
				},
			});

			dialog.show();
			dialog.$wrapper.on("hidden.bs.modal", finish);
		});
	},

	format_rate(value) {
		if (value === null || value === undefined || value === "") {
			return "";
		}
		return frappe.format(value, { fieldtype: "Float" });
	},
};
