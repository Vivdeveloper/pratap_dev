frappe.ui.form.on("BOM", {
	setup(frm) {
		// Restrict Raw Materials "Item Code" to items under the "Raw Material" group tree.
		// Runs after ERPNext's own setup handler, so this query wins.
		frm.set_query("item_code", "items", function () {
			return {
				query: "pratap_dev.bom_custom.raw_material_item_query",
				filters: {
					include_item_in_manufacturing: 1,
					is_fixed_asset: 0,
				},
			};
		});
	},
});
