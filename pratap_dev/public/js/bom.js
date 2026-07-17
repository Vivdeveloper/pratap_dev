frappe.ui.form.on("BOM", {
	setup(frm) {
		// Runs after ERPNext's own setup handler, so this query wins.
		frm.set_query("item_code", "items", function () {
			return {
				query: "pratap_dev.bom_custom.item_group_filtered_item_query",
				filters: {
					item_group_filter: frm.doc.custom_item_group_filter,
					include_item_in_manufacturing: 1,
					is_fixed_asset: 0,
				},
			};
		});
	},
});
