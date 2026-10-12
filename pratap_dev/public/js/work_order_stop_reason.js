// Stopping a Work Order must capture a mandatory reason. Instead of fiddling with the
// toolbar buttons (which races with ERPNext's own button-adding), we override
// erpnext.work_order.change_work_order_status: the core "Stop" button still calls it with
// status "Stopped", but we intercept that one case to open a reason dialog (the Stop button
// is disabled until a reason is entered), save the reason on the WO, then stop. Every other
// status transition (Close, Re-open, …) and the Start flow are left exactly as they were.

frappe.ui.form.on("Work Order", {
	onload() {
		install_stop_override();
	},
	refresh() {
		install_stop_override();
	},
});

function install_stop_override() {
	if (!window.erpnext || !erpnext.work_order || erpnext.work_order._pratap_stop_patched) {
		return;
	}
	const original = erpnext.work_order.change_work_order_status;
	erpnext.work_order.change_work_order_status = function (frm, status) {
		if (status === "Stopped") {
			open_stop_reason_dialog(frm);
			return;
		}
		return original.call(this, frm, status);
	};
	erpnext.work_order._pratap_stop_patched = true;
}

function open_stop_reason_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Stop Work Order"),
		fields: [
			{
				fieldname: "reason",
				fieldtype: "Small Text",
				label: __("Reason for Stopping"),
				reqd: 1,
				description: __("Required — the Work Order cannot be stopped without a reason."),
			},
		],
		primary_action_label: __("Stop Work Order"),
		primary_action(values) {
			const reason = (values.reason || "").trim();
			if (!reason) {
				return;
			}
			dialog.hide();
			frappe.call({
				method: "pratap_dev.work_order_class.stop_work_order_with_reason",
				args: { work_order: frm.doc.name, reason: reason },
				freeze: true,
				freeze_message: __("Stopping Work Order..."),
				callback(r) {
					if (r.message) {
						frm.reload_doc();
						frappe.show_alert(
							{ message: __("Work Order stopped."), indicator: "orange" },
							5
						);
					}
				},
			});
		},
	});

	dialog.show();

	// Disable the Stop button until a non-empty reason is entered.
	const $btn = dialog.get_primary_btn();
	$btn.prop("disabled", true);
	const toggle = () => $btn.prop("disabled", !(dialog.get_value("reason") || "").trim());
	dialog.fields_dict.reason.$input.on("input keyup change", toggle);
}
