// Asset Maintenance Log — Consumed Maintenance Items.
// Item picker: stock items, limited to Pratap Asset Settings > Allowed Item Groups
// (with sub-groups) when that is set — also enforced on save.
// Available Qty shows the stock in the Source Warehouse (checked again on submit).
// Pratap Asset Settings > Stock Entry Creation:
//   Auto   — the Material Issue Stock Entry is created when the log is submitted;
//   Manual — a submitted log with consumed items gets a Create Stock Entry button.
// Either way, once a Stock Entry exists the button opens it instead.

const PM_SE_API = "pratap_dev.pratap_maintenance.server.maintenance_stock_entry";

frappe.ui.form.on("Asset Maintenance Log", {
	setup(frm) {
		frm.set_query("custom_source_warehouse", () => ({ filters: { is_group: 0 } }));
		frm.set_query("item_code", "custom_consumed_items", () => {
			const filters = [
				["is_stock_item", "=", 1],
				["disabled", "=", 0],
				["has_variants", "=", 0],
			];
			if ((frm._pm_item_groups || []).length) {
				filters.push(["item_group", "in", frm._pm_item_groups]);
			}
			return { filters };
		});
	},

	onload(frm) {
		frappe.xcall(`${PM_SE_API}.get_consumed_item_settings`).then((settings) => {
			frm._pm_item_groups = settings.item_groups || [];
			frm._pm_default_warehouse = settings.default_source_warehouse || "";
			if (frm.is_new()) {
				set_default_source_warehouse(frm);
			}
		});
	},

	refresh(frm) {
		add_stock_entry_button(frm);
	},

	custom_source_warehouse(frm) {
		refresh_available_qty(frm);
	},
});

frappe.ui.form.on("Asset Maintenance Consumed Item", {
	item_code(frm) {
		// The field's own change handler refreshes Available Qty when it gets set here.
		if (!set_default_source_warehouse(frm)) {
			refresh_available_qty(frm);
		}
	},
	custom_consumed_items_remove(frm) {
		refresh_available_qty(frm);
	},
});

// Pratap Asset Settings > Default Source Warehouse into an empty draft log; true if set.
function set_default_source_warehouse(frm) {
	if (frm.doc.docstatus !== 0 || frm.doc.custom_source_warehouse || !frm._pm_default_warehouse) {
		return false;
	}
	frm.set_value("custom_source_warehouse", frm._pm_default_warehouse);
	return true;
}

function refresh_available_qty(frm) {
	const rows = frm.doc.custom_consumed_items || [];
	const warehouse = frm.doc.custom_source_warehouse;
	if (frm.doc.docstatus !== 0 || !rows.length) {
		return;
	}
	if (!warehouse) {
		rows.forEach((row) => frappe.model.set_value(row.doctype, row.name, "available_qty", 0));
		return;
	}
	frappe
		.xcall(`${PM_SE_API}.get_available_qty`, {
			warehouse,
			items: rows.map((row) => row.item_code).filter(Boolean),
		})
		.then((qty) => {
			rows.forEach((row) => {
				frappe.model.set_value(row.doctype, row.name, "available_qty", qty[row.item_code] || 0);
			});
		});
}

function add_stock_entry_button(frm) {
	if (frm.doc.docstatus !== 1 || !(frm.doc.custom_consumed_items || []).length) {
		return;
	}
	frappe.xcall(`${PM_SE_API}.get_stock_entry_state`, { log: frm.doc.name }).then((state) => {
		if (state.stock_entry) {
			frm.add_custom_button(__("View Stock Entry"), () =>
				frappe.set_route("Form", "Stock Entry", state.stock_entry)
			);
		} else if (state.mode === "Manual") {
			frm.add_custom_button(__("Create Stock Entry"), () => {
				frappe
					.xcall(`${PM_SE_API}.make_stock_entry`, { log: frm.doc.name })
					.then((name) => frappe.set_route("Form", "Stock Entry", name));
			}).addClass("btn-primary");
		}
	});
}
