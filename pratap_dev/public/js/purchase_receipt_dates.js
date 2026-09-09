// Grey out future dates in the GRN's Supplier Invoice Date picker (max = today),
// mirroring the Gate Pass rule. air-datepicker's maxDate needs a REAL Date object
// (a string throws and breaks the form render), so we pass `new Date()`. Wrapped in
// try/catch so a picker quirk can never blank the form. Backed by the server-side
// "no future date" validation in purchase_receipt.py.
frappe.ui.form.on("Purchase Receipt", {
	onload(frm) {
		restrict_supplier_invoice_date(frm);
	},
	refresh(frm) {
		restrict_supplier_invoice_date(frm);
	},
});

function restrict_supplier_invoice_date(frm) {
	const field = frm.fields_dict.custom_supplier_invoice_date;
	if (!field) {
		return;
	}
	try {
		const today = new Date();
		field.df.max_date = today;
		if (field.datepicker && typeof field.datepicker.update === "function") {
			field.datepicker.update({ maxDate: today });
		}
	} catch (e) {
		console.warn("Purchase Receipt: could not restrict supplier invoice date", e);
	}
}
