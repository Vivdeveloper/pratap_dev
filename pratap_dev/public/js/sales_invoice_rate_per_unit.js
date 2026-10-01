// Sales Invoice — fill "Rate Per Unit" (custom_rate_in_kg) from the Item Price the Rate came
// from. Within the invoice's selling price list, a CUSTOMER-specific Item Price wins over the
// generic one (same way the Rate itself is picked), falling back to the standard price.
frappe.ui.form.on("Sales Invoice Item", {
	item_code(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.item_code) {
			return;
		}
		const price_list = frm.doc.selling_price_list;
		if (!price_list) {
			return;
		}
		frappe
			.call({
				method: "pratap_dev.item_rate_per_unit.get_rate_per_unit",
				args: {
					item_code: row.item_code,
					price_list: price_list,
					customer: frm.doc.customer || null,
				},
			})
			.then((r) => {
				frappe.model.set_value(cdt, cdn, "custom_rate_in_kg", flt(r.message) || 0);
			});
	},
});
