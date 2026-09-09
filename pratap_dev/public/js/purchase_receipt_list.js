// Show the GRN QC lifecycle on the Purchase Receipt list: a draft GRN that has been
// sent for QC shows an orange "QC Pending" indicator. All other cases fall back to
// ERPNext's standard status indicator (Draft / To Bill / Completed / Submitted …).
(() => {
	const existing = frappe.listview_settings["Purchase Receipt"] || {};
	const prev_get_indicator = existing.get_indicator;

	frappe.listview_settings["Purchase Receipt"] = Object.assign({}, existing, {
		add_fields: [...(existing.add_fields || []), "custom_qc_status", "docstatus"],
		get_indicator(doc) {
			if (doc.docstatus === 0 && doc.custom_qc_status === "QC Pending") {
				return [__("QC Pending"), "orange", "custom_qc_status,=,QC Pending"];
			}
			if (prev_get_indicator) {
				return prev_get_indicator(doc);
			}
			return undefined;
		},
	});
})();
