// Work Order mirror of the BOM batch-sheet Notes table. The scalar fields
// (Remarks, Shelf Life, Sample Qty, Total %, Min Batch Qty, Effective Date) flow
// automatically via fetch_from on bom_no; the Notes table is copied here so it
// shows immediately when the BOM is picked/changed (server re-copies on save too).
frappe.ui.form.on("Work Order", {
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
