// Asset Maintenance Log — Maintenance Checklist from its Asset Maintenance.
// Rows are Asset Maintenance Log Checklist (check point, description, status, observation).
// Changing Asset Maintenance on a draft log reloads the check points, unless a status or
// observation has already been entered. (Logs ERPNext creates are filled server-side.)

frappe.ui.form.on("Asset Maintenance Log", {
	setup(frm) {
		frm.set_query("check_point", "maintenance_checklists", (doc, cdt, cdn) =>
			unused_check_point_query(doc.maintenance_checklists, cdn)
		);
	},

	asset_maintenance(frm) {
		if (frm.doc.docstatus !== 0) {
			return;
		}
		const started = (frm.doc.maintenance_checklists || []).some(
			(row) => row.status || row.observation
		);
		if (started) {
			return;
		}
		if (!frm.doc.asset_maintenance) {
			frm.clear_table("maintenance_checklists");
			frm.refresh_field("maintenance_checklists");
			return;
		}
		frappe
			.xcall("pratap_dev.pratap_maintenance.server.asset_maintenance_checklist.get_asset_maintenance_checklist", {
				asset_maintenance: frm.doc.asset_maintenance,
			})
			.then((rows) => {
				frm.clear_table("maintenance_checklists");
				(rows || []).forEach((row) => {
					frm.add_child("maintenance_checklists", {
						check_point: row.check_point,
						description: row.description,
					});
				});
				frm.refresh_field("maintenance_checklists");
			});
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
