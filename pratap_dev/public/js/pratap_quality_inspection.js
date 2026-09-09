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
	},
});
