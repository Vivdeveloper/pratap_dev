frappe.ui.form.on("BOM", {
	setup(frm) {
		// Filter dropdown: show only parent (group) item groups, e.g. Finished
		// Goods / Raw Material — not the leaf item groups.
		frm.set_query("custom_item_group_filter", function () {
			return {
				filters: {
					is_group: 1,
				},
			};
		});

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
	refresh(frm) {
		set_bom_total_quantity(frm);
	},
	// Fires when a BOM Item row is removed.
	items_remove(frm) {
		set_bom_total_quantity(frm);
	},
});

frappe.ui.form.on("BOM Item", {
	// Live-update Total Quantity as each row's Qty changes.
	qty(frm) {
		set_bom_total_quantity(frm);
	},
});

// Total Quantity (custom_total_percentage) = sum of all BOM Item Qty values.
function set_bom_total_quantity(frm) {
	if (!frm.fields_dict.custom_total_percentage) {
		return;
	}
	let total = 0;
	(frm.doc.items || []).forEach((row) => {
		total += flt(row.qty);
	});
	// Only write when it actually differs, so a plain refresh doesn't dirty the form.
	if (flt(frm.doc.custom_total_percentage) !== flt(total)) {
		frm.set_value("custom_total_percentage", total);
	}
}
