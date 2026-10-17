// Copyright (c) 2026, pratap_dev contributors
// For license information, please see license.txt

frappe.listview_settings["Pratap Downtime Entry"] = {
	add_fields: ["status", "downtime_type"],
	get_indicator(doc) {
		const colors = { Open: "orange", Completed: "green", Cancelled: "red" };
		return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
	},
};
