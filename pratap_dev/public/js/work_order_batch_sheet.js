// Work Order mirror of the BOM batch-sheet Notes table. The scalar fields
// (Remarks, Shelf Life, Sample Qty, Total %, Min Batch Qty, Effective Date) flow
// automatically via fetch_from on bom_no; the Notes table is copied here so it
// shows immediately when the BOM is picked/changed (server re-copies on save too).
frappe.ui.form.on("Work Order", {
	refresh(frm) {
		// "Refresh Batch Details from BOM" — re-pulls the batch-sheet fields + Notes
		// table from the BOM. Works on submitted Work Orders too (fetch_from only
		// populates at creation, so older WOs stay blank until refreshed).
		if (frm.is_new() || !frm.doc.bom_no) {
			return;
		}
		frm.add_custom_button(__("Refresh Batch Details from BOM"), () => {
			if (frm.is_dirty()) {
				frappe.msgprint(__("Please save the Work Order before refreshing from BOM."));
				return;
			}
			frappe.call({
				method: "pratap_dev.bom_batch_sheet.refresh_batch_details_from_bom",
				args: { work_order: frm.doc.name },
				freeze: true,
				freeze_message: __("Fetching batch details from BOM..."),
				callback(r) {
					if (r.exc) {
						return;
					}
					const m = r.message || {};
					frappe.show_alert(
						{
							message: __("Batch details refreshed from BOM ({0} field(s), {1} note(s)).", [
								m.scalars || 0,
								m.notes || 0,
							]),
							indicator: "green",
						},
						5
					);
					frm.reload_doc();
				},
			});
		});
	},

	bom_no(frm) {
		if (!frm.doc.bom_no) {
			frm.clear_table("custom_notes");
			frm.refresh_field("custom_notes");
			return;
		}
		frappe.call({
			method: "pratap_dev.bom_batch_sheet.get_bom_batch_sheet",
			args: { bom_no: frm.doc.bom_no },
			callback(r) {
				const notes = (r.message && r.message.notes) || [];
				frm.clear_table("custom_notes");
				notes.forEach((note) => {
					frm.add_child("custom_notes", { note });
				});
				frm.refresh_field("custom_notes");
			},
		});
	},
});
