// Asset Maintenance — Maintenance Checklist from a template.
// Check points are Asset Checklist masters. Picking a Maintenance Checklist Template
// loads its check points into the Maintenance Checklists table (Asset Maintenance
// Checklist rows; status and observations are recorded on the Asset Maintenance Log).
// Templates are limited to enabled ones, and to the asset's category when the template
// has one set (templates without a category are offered for every asset).

frappe.ui.form.on("Asset Maintenance", {
	setup(frm) {
		frm.set_query("custom_maintenance_checklist_template", () => {
			const filters = [["disabled", "=", 0]];
			if (frm.doc.asset_category) {
				filters.push(["asset_category", "in", [frm.doc.asset_category, ""]]);
			}
			return { filters };
		});
		frm.set_query("check_point", "maintenance_checklists", (doc, cdt, cdn) =>
			unused_check_point_query(doc.maintenance_checklists, cdn)
		);
	},

	refresh(frm) {
		// Template the current checklist came from — restored if a replace is declined.
		frm._checklist_template = frm.doc.custom_maintenance_checklist_template || "";
	},

	custom_maintenance_checklist_template(frm) {
		if (frm._reverting_checklist_template) {
			return;
		}
		const template = frm.doc.custom_maintenance_checklist_template;
		if (!template) {
			frm._checklist_template = "";
			return;
		}
		const has_rows = (frm.doc.maintenance_checklists || []).some((row) => row.check_point);
		if (has_rows) {
			frappe.confirm(
				__("Replace the existing checklist with the check points from {0}?", [template.bold()]),
				() => load_checklist_template(frm, template),
				() => revert_checklist_template(frm)
			);
		} else {
			load_checklist_template(frm, template);
		}
	},
});

function load_checklist_template(frm, template) {
	frappe.db.get_doc("Maintenance Checklist Template", template).then((doc) => {
		frm.clear_table("maintenance_checklists");
		(doc.checklist_items || []).forEach((item) => {
			frm.add_child("maintenance_checklists", {
				check_point: item.check_point,
				description: item.description,
			});
		});
		frm.refresh_field("maintenance_checklists");
		frm._checklist_template = template;
	});
}

// Replace declined: put the link back so it still matches the rows in the table.
function revert_checklist_template(frm) {
	frm._reverting_checklist_template = true;
	frm.set_value("custom_maintenance_checklist_template", frm._checklist_template || "").finally(
		() => {
			frm._reverting_checklist_template = false;
		}
	);
}

// Enabled check points not already in the table (the row being edited keeps its own).
function unused_check_point_query(rows, cdn) {
	const used = (rows || []).filter((row) => row.name !== cdn && row.check_point).map((row) => row.check_point);
	const filters = [["disabled", "=", 0]];
	if (used.length) {
		filters.push(["name", "not in", used]);
	}
	return { filters };
}
