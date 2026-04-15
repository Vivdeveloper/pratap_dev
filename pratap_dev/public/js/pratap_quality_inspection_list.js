frappe.listview_settings["Pratap Quality Inspection"] = {
	add_fields: ["status", "docstatus"],
	has_indicator_for_draft: 1,
	get_indicator(doc) {
		const status = (doc.status || "").trim();

		if (doc.docstatus === 2) {
			return [__("Cancelled"), "red", "docstatus,=,2"];
		} else if (status === "Pending") {
			return [__(status), "purple", "status,=," + status];
		} else if (status === "Accepted") {
			return [__(status), "green", "status,=," + status];
		} else if (status === "Rejected") {
			return [__(status), "red", "status,=," + status];
		} else if (status === "Rework") {
			return [__(status), "blue", "status,=," + status];
		}
	},
};
