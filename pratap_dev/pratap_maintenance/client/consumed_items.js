// Consumed Maintenance Items — shared form logic, loaded first in the doctype_js lists of
// Asset Maintenance Log and Pratap Downtime Entry; each calls pratap_consumed_items.setup()
// with its own field names.
// Item picker: enabled stock items, limited to Pratap Asset Settings > Allowed Item Groups
// (with sub-groups) when set — also enforced on save. Source Warehouse defaults from the
// settings; Available Qty shows its stock (checked again on submit).
// On a submitted document with consumed items: View Stock Entry once one exists, otherwise
// Create Stock Entry (Manual mode, or Auto mode after its Stock Entry was cancelled).

window.pratap_consumed_items = {
	API: "pratap_dev.pratap_maintenance.server.maintenance_stock_entry",

	// opts: { items_field, warehouse_field } — the parent's table and Source Warehouse fields
	setup(doctype, child_doctype, opts) {
		const pci = this;
		const cfg = Object.assign({ doctype }, opts);

		frappe.ui.form.on(doctype, {
			setup(frm) {
				frm.set_query(cfg.warehouse_field, () => ({ filters: { is_group: 0 } }));
				frm.set_query("item_code", cfg.items_field, () => {
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
				frappe.xcall(`${pci.API}.get_consumed_item_settings`, { doctype }).then((settings) => {
					frm._pm_item_groups = settings.item_groups || [];
					frm._pm_default_warehouse = settings.default_source_warehouse || "";
					if (frm.is_new()) {
						pci.set_default_source_warehouse(frm, cfg);
					}
				});
			},

			refresh(frm) {
				// onload sets it once the settings arrive; this covers a new form shown again.
				if (frm.is_new()) {
					pci.set_default_source_warehouse(frm, cfg);
				}
				pci.add_stock_entry_button(frm, cfg);
			},

			[cfg.warehouse_field](frm) {
				pci.refresh_available_qty(frm, cfg);
			},
		});

		frappe.ui.form.on(child_doctype, {
			item_code(frm) {
				// The warehouse field's own change handler refreshes Available Qty when set here.
				if (!pci.set_default_source_warehouse(frm, cfg)) {
					pci.refresh_available_qty(frm, cfg);
				}
			},
			[`${cfg.items_field}_remove`](frm) {
				pci.refresh_available_qty(frm, cfg);
			},
		});
	},

	// Pratap Asset Settings > Default Source Warehouse into an empty draft; true if set.
	set_default_source_warehouse(frm, cfg) {
		if (frm.doc.docstatus !== 0 || frm.doc[cfg.warehouse_field] || !frm._pm_default_warehouse) {
			return false;
		}
		frm.set_value(cfg.warehouse_field, frm._pm_default_warehouse);
		return true;
	},

	refresh_available_qty(frm, cfg) {
		const rows = frm.doc[cfg.items_field] || [];
		const warehouse = frm.doc[cfg.warehouse_field];
		if (frm.doc.docstatus !== 0 || !rows.length) {
			return;
		}
		if (!warehouse) {
			rows.forEach((row) => frappe.model.set_value(row.doctype, row.name, "available_qty", 0));
			return;
		}
		frappe
			.xcall(`${this.API}.get_available_qty`, {
				doctype: cfg.doctype,
				warehouse,
				items: rows.map((row) => row.item_code).filter(Boolean),
			})
			.then((qty) => {
				rows.forEach((row) => {
					frappe.model.set_value(row.doctype, row.name, "available_qty", qty[row.item_code] || 0);
				});
			});
	},

	add_stock_entry_button(frm, cfg) {
		if (frm.doc.docstatus !== 1 || !(frm.doc[cfg.items_field] || []).length) {
			return;
		}
		frappe
			.xcall(`${this.API}.get_stock_entry_state`, { doctype: cfg.doctype, name: frm.doc.name })
			.then((state) => {
				if (state.stock_entry) {
					frm.add_custom_button(__("View Stock Entry"), () =>
						frappe.set_route("Form", "Stock Entry", state.stock_entry)
					);
					return;
				}
				frm.add_custom_button(__("Create Stock Entry"), () => {
					frappe.call({
						method: `${this.API}.make_stock_entry`,
						args: { doctype: cfg.doctype, name: frm.doc.name },
						freeze: true,
						freeze_message: __("Creating Stock Entry..."),
						callback: (r) => r.message && frappe.set_route("Form", "Stock Entry", r.message),
					});
				}).addClass("btn-primary");
			});
	},
};
