// Batch-sheet fields on the BOM. Effective Date pre-fills today and can only be
// today or a future date (the server also enforces "no past date").
frappe.ui.form.on("BOM", {
	onload(frm) {
		if (frm.is_new() && !frm.doc.custom_effective_date) {
			frm.set_value("custom_effective_date", frappe.datetime.get_today());
		}
		set_effective_date_min(frm);
	},
	refresh(frm) {
		set_effective_date_min(frm);
	},
});

function set_effective_date_min(frm) {
	const field = frm.fields_dict.custom_effective_date;
	if (!field || !field.datepicker) {
		return;
	}
	// Pass a Date object (a string throws inside air-datepicker's update()).
	try {
		field.datepicker.update({ minDate: frappe.datetime.str_to_obj(frappe.datetime.get_today()) });
	} catch (e) {
		// datepicker not ready yet — harmless, server still blocks past dates.
	}
}
