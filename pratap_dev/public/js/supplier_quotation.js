frappe.ui.form.on("Supplier Quotation", {
	refresh(frm) {
		if (pratap_dev.last_buying_rates.should_show(frm)) {
			frm.add_custom_button(
				__("Last Buying Rate"),
				() => show_last_buying_rates(frm),
				__("Tools")
			);
		}
	},

	async before_save(frm) {
		if (pratap_dev.last_buying_rates.should_show(frm)) {
			await show_last_buying_rates(frm);
		}
	},

	async after_workflow_action(frm) {
		if (pratap_dev.last_buying_rates.should_show(frm)) {
			await show_last_buying_rates(frm);
		}
	},
});

frappe.ui.form.on("Supplier Quotation Item", {
	item_code(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		frm.model.set_value(cdt, cdn, "rate", "");
	},
});
function show_last_buying_rates(frm) {
	return pratap_dev.last_buying_rates.show(frm, {
		rate_column_label: __("Rate"),
		current_po: "",
	});
}
