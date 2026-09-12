frappe.ui.form.on("Pratap Quality Inspection", {
	setup(frm) {
		// "Filter" dropdown: only parent (group) item groups, e.g. Raw Material / Finished Good.
		frm.set_query("custom_item_group_filter", function () {
			return { filters: { is_group: 1 } };
		});

		// Filter the Raw Materials item_code list by the selected item group (and its children).
		frm.set_query("item_code", "raw_materials", function () {
			return {
				query: "pratap_dev.pratap.doctype.pratap_quality_inspection.pratap_quality_inspection.item_group_filtered_item_query",
				filters: {
					item_group_filter: frm.doc.custom_item_group_filter,
				},
			};
		});

		// Rework batch dropdown: batches of the row's item, showing the available qty right
		// in the dropdown (batch · Qty: N).
		frm.set_query("custom_batch", "raw_materials", function (doc, cdt, cdn) {
			const row = locals[cdt][cdn];
			return {
				query: "pratap_dev.rework_material_transfer.batch_with_qty_query",
				filters: { item: row.item_code || "" },
			};
		});
	},

	refresh(frm) {
		// "Rework Material Transfer" — for a rework QC linked to a Work Order, transfer the
		// per-row Transfer Qty from the WO source warehouse to WIP, auto-provisioning any
		// shortfall (creates a Rework Material Transfer MR + moves stock into the source).
		if (frm.is_new() || (frm.doc.reference_type || "") !== "Work Order") {
			return;
		}
		const has_transfer = (frm.doc.raw_materials || []).some((r) => flt(r.custom_transfer_qty) > 0);
		if (!has_transfer) {
			return;
		}
		frm.add_custom_button(__("Rework Material Transfer"), () => rework_material_transfer(frm));
	},
});

frappe.ui.form.on("Pratap Quality Inspection Raw Material", {
	item_code(frm, cdt, cdn) {
		populate_rework_stock(frm, cdt, cdn);
	},
	custom_batch(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.custom_batch || !row.item_code) {
			frappe.model.set_value(cdt, cdn, "custom_batch_qty", 0);
			return;
		}
		// Fill the selected batch's on-hand qty (across warehouses) for reference.
		frappe.call({
			method: "pratap_dev.rework_material_transfer.get_rework_item_stock",
			args: { item_code: row.item_code, company: frm.doc.company },
			callback(r) {
				const b = ((r.message && r.message.batches) || []).filter(
					(x) => x.batch_no === row.custom_batch
				);
				const qty = b.reduce((s, x) => s + flt(x.qty), 0);
				frappe.model.set_value(cdt, cdn, "custom_batch_qty", qty);
			},
		});
	},
});

// Populate the per-warehouse available-qty columns for a Raw Materials row.
function populate_rework_stock(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row || !row.item_code || !frm.doc.company) {
		return;
	}
	frappe.call({
		method: "pratap_dev.rework_material_transfer.get_rework_item_stock",
		args: { item_code: row.item_code, company: frm.doc.company },
		callback(r) {
			const w = (r.message && r.message.warehouses) || {};
			frappe.model.set_value(cdt, cdn, "custom_plant_1_wip_rm", flt(w.custom_plant_1_wip_rm));
			frappe.model.set_value(cdt, cdn, "custom_plant_2_wip_rm", flt(w.custom_plant_2_wip_rm));
			frappe.model.set_value(cdt, cdn, "custom_main_store_rm", flt(w.custom_main_store_rm));
		},
	});
}

// Transfer each rework row's Transfer Qty (source -> WIP), auto-provisioning shortfalls.
function rework_material_transfer(frm) {
	const rows = (frm.doc.raw_materials || []).filter((r) => flt(r.custom_transfer_qty) > 0 && r.item_code);
	if (!rows.length) {
		frappe.msgprint(__("Set a Transfer Qty on at least one Raw Materials row."));
		return;
	}
	frappe.confirm(
		__(
			"Transfer the entered quantities for {0} item(s)? If the source warehouse is short, a Rework Material Transfer Material Request will be auto-created and stock moved into the source.",
			[rows.length]
		),
		() => {
			const run = (i) => {
				if (i >= rows.length) {
					frappe.show_alert({ message: __("Rework material transfer complete."), indicator: "green" }, 5);
					frm.reload_doc();
					return;
				}
				const row = rows[i];
				frappe.call({
					method: "pratap_dev.rework_material_transfer.rework_transfer_with_provision",
					args: {
						work_order: frm.doc.reference_name,
						qc: frm.doc.name,
						item_code: row.item_code,
						qty: flt(row.custom_transfer_qty),
						batch: row.custom_batch || null,
					},
					freeze: true,
					freeze_message: __("Transferring {0}…", [row.item_code]),
					callback(r) {
						if (r.message) {
							const p = r.message.provision;
							if (p) {
								frappe.show_alert(
									{
										message: __("{0}: provisioned {1} via {2} (moved from {3}).", [
											row.item_code,
											p.shortfall,
											p.material_request,
											p.donor_warehouse,
										]),
										indicator: "blue",
									},
									7
								);
							}
						}
						run(i + 1);
					},
				});
			};
			run(0);
		}
	);
}
