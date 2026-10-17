// Copyright (c) 2026, pratap_dev contributors
// For license information, please see license.txt

frappe.ui.form.on("Maintenance Checklist Template", {
	setup(frm) {
		frm.set_query("check_point", "checklist_items", () => ({ filters: { disabled: 0 } }));
	},
});
