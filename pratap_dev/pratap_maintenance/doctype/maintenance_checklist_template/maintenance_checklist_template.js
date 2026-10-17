// Copyright (c) 2026, pratap_dev contributors
// For license information, please see license.txt

frappe.ui.form.on("Maintenance Checklist Template", {
	setup(frm) {
		frm.set_query("check_point", "checklist_items", (doc, cdt, cdn) =>
			unused_check_point_query(doc.checklist_items, cdn)
		);
	},
});

// Enabled check points not already in the table (the row being edited keeps its own).
function unused_check_point_query(rows, cdn) {
	const used = (rows || []).filter((row) => row.name !== cdn && row.check_point).map((row) => row.check_point);
	const filters = [["disabled", "=", 0]];
	if (used.length) {
		filters.push(["name", "not in", used]);
	}
	return { filters };
}
