frappe.ui.form.on("Material Request", {
	refresh(frm) {
		frm.remove_custom_button(__("Purchase Order"), __("Create"));
		(frm.doc.items || []).forEach((row) => {
			set_rm_warehouse_qty(frm, row.doctype, row.name);
		});
	},
});

frappe.ui.form.on("Material Request Item", {
	item_code(frm, cdt, cdn) {
		set_rm_warehouse_qty(frm, cdt, cdn);
	},
	custom_packing_qty(frm, cdt, cdn) {
		calculate_quantity(frm, cdt, cdn);
	},
	custom_total_qty(frm, cdt, cdn) {
		calculate_quantity(frm, cdt, cdn);
	}

});

function calculate_quantity(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const quantity = (row.custom_packing_qty || 0) * (row.custom_total_qty || 0);
	frappe.model.set_value(cdt, cdn, "qty", quantity);
}
function set_rm_warehouse_qty(frm, cdt, cdn) {
	if (frm.doc.docstatus !== 0) {
		return;
	}

	const row = locals[cdt][cdn];
	if (!row.item_code || !frm.doc.company) {
		frappe.model.set_value(cdt, cdn, "custom_wip_rm_qty", 0);
		frappe.model.set_value(cdt, cdn, "custom_main_store_rm_qty", 0);
		return;
	}

	Promise.all([
		frappe.db.get_value("Warehouse", { warehouse_name: "WIP RM", company: frm.doc.company }, "name"),
		frappe.db.get_value(
			"Warehouse",
			{ warehouse_name: "Main Store RM", company: frm.doc.company },
			"name"
		),
	])
		.then(([wip_warehouse, main_store_warehouse]) => {
			const wip_wh = wip_warehouse?.message?.name;
			const main_wh = main_store_warehouse?.message?.name;

			return Promise.all([
				wip_wh
					? frappe
							.xcall("erpnext.stock.utils.get_latest_stock_qty", {
								item_code: row.item_code,
								warehouse: wip_wh,
							})
							.then((qty) => flt(qty))
					: Promise.resolve(0),
				main_wh
					? frappe
							.xcall("erpnext.stock.utils.get_latest_stock_qty", {
								item_code: row.item_code,
								warehouse: main_wh,
							})
							.then((qty) => flt(qty))
					: Promise.resolve(0),
			]);
		})
		.then(([wip_qty, main_qty]) => {
			frappe.model.set_value(cdt, cdn, "custom_wip_rm_qty", flt(wip_qty));
			frappe.model.set_value(cdt, cdn, "custom_main_store_rm_qty", flt(main_qty));
		})
		.catch(() => {
			frappe.model.set_value(cdt, cdn, "custom_wip_rm_qty", 0);
			frappe.model.set_value(cdt, cdn, "custom_main_store_rm_qty", 0);
		});
}
