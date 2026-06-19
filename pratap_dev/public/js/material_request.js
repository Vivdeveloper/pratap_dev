frappe.ui.form.on("Material Request", {
	refresh(frm) {
		frm.remove_custom_button(__("Purchase Order"), __("Create"));

		frm.set_query("custom_supplier_", "items", function (doc, cdt, cdn) {
			const row = locals[cdt][cdn];
			return {
				query: "auto_po_creation.api.supplier_link_query",
				filters: { item_code: row.item_code || "" },
			};
		});

		if (!frm.doc.__islocal && frm.doc.docstatus === 1 && frm.doc.material_request_type === "Purchase") {
			frm.add_custom_button(__("Supplier Quotation"), () => {
				open_mr_document_dialog(frm, MR_SQ_CONFIG);
			});
		}
	},
});

frappe.ui.form.on("Material Request Item", {
	item_code(frm, cdt, cdn) {
		set_rm_warehouse_qty(frm, cdt, cdn);
		set_supplier_if_single_vendor(frm, cdt, cdn);
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

function set_supplier_if_single_vendor(frm, cdt, cdn) {
	if (frm.doc.docstatus !== 0 || frm.doc.material_request_type !== "Purchase") {
		return;
	}

	const row = locals[cdt][cdn];
	if (!row?.item_code) {
		return;
	}

	frappe.call({
		method: "auto_po_creation.api.get_item_suppliers",
		args: { item_code: row.item_code },
		callback(r) {
			const suppliers = r.message || [];
			if (suppliers.length !== 1) {
				return;
			}

			const supplier = suppliers[0].supplier;
			if (row.custom_supplier_ === supplier) {
				return;
			}

			frappe.model.set_value(cdt, cdn, "custom_supplier_", supplier);
		},
	});
}

function set_rm_qty_field(cdt, cdn, fieldname, value) {
	const row = locals[cdt][cdn];
	const next_value = flt(value);

	if (flt(row[fieldname]) === next_value) {
		return;
	}

	frappe.model.set_value(cdt, cdn, fieldname, next_value, null, true);
}

function set_rm_warehouse_qty(frm, cdt, cdn) {
	if (frm.doc.docstatus !== 0) {
		return;
	}

	const row = locals[cdt][cdn];
	if (!row.item_code || !frm.doc.company) {
		set_rm_qty_field(cdt, cdn, "custom_wip_rm_qty", 0);
		set_rm_qty_field(cdt, cdn, "custom_main_store_rm_qty", 0);
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
			set_rm_qty_field(cdt, cdn, "custom_wip_rm_qty", wip_qty);
			set_rm_qty_field(cdt, cdn, "custom_main_store_rm_qty", main_qty);
		})
		.catch(() => {
			set_rm_qty_field(cdt, cdn, "custom_wip_rm_qty", 0);
			set_rm_qty_field(cdt, cdn, "custom_main_store_rm_qty", 0);
		});
}
