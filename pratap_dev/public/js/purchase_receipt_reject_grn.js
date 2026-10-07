// "Reject GRN" flow on the Purchase Receipt.
//
// Ticking Reject GRN moves every item's Accepted Quantity (qty) into Rejected Quantity
// (rejected_qty), setting Accepted = 0 — so the whole receipt is rejected. The server then
// skips the Pratap Quality Inspection requirement on submit (nothing is accepted into stock,
// so there is nothing to inspect). Unticking restores the rejected qty back to accepted.

frappe.ui.form.on("Purchase Receipt", {
	custom_reject_grn(frm) {
		if (frm.doc.docstatus !== 0) {
			return;
		}
		const reject = !!frm.doc.custom_reject_grn;

		(frm.doc.items || []).forEach((row) => {
			if (reject) {
				// Accepted -> Rejected, Accepted = 0.
				const accepted = flt(row.qty);
				if (accepted > 0) {
					frappe.model.set_value(row.doctype, row.name, "rejected_qty", flt(row.rejected_qty) + accepted);
					frappe.model.set_value(row.doctype, row.name, "qty", 0);
				}
			} else {
				// Restore: Rejected -> Accepted, Rejected = 0.
				const rejected = flt(row.rejected_qty);
				if (rejected > 0) {
					frappe.model.set_value(row.doctype, row.name, "qty", flt(row.qty) + rejected);
					frappe.model.set_value(row.doctype, row.name, "rejected_qty", 0);
				}
			}
		});

		frm.refresh_field("items");

		if (reject) {
			frappe.show_alert(
				{
					message: __("All Accepted Qty moved to Rejected Qty. QC is not required to submit this GRN."),
					indicator: "orange",
				},
				7
			);
			// Rejected qty needs a Rejected Warehouse — nudge the user if it's missing.
			const missing_wh = (frm.doc.items || []).some(
				(row) => flt(row.rejected_qty) > 0 && !row.rejected_warehouse
			);
			if (missing_wh && !frm.doc.rejected_warehouse) {
				frappe.msgprint({
					title: __("Set Rejected Warehouse"),
					indicator: "orange",
					message: __(
						"Set a Rejected Warehouse (header or per row) before submitting — rejected stock needs a warehouse."
					),
				});
			}
		}
	},
});
