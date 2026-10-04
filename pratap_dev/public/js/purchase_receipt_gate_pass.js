// Purchase Receipt (GRN) — auto-fill the Transporter Details tab from the Gate Pass.
//
// When the user lands on the "Transporter Details" tab of a draft GRN, we pull the
// matching transporter fields from the LATEST Gate Pass linked to the GRN's Purchase
// Order(s) and fill any that are still empty. No new fields are created — only fields
// that exist on both the Gate Pass and the Transporter Details tab are copied:
//     Transporter Name, Vehicle No, Driver (Link), Driver Name.

frappe.ui.form.on("Purchase Receipt", {
	refresh(frm) {
		bind_transporter_tab_autofill(frm);
	},
});

function bind_transporter_tab_autofill(frm) {
	if (frm.doc.docstatus !== 0) return; // only editable drafts

	const $link = frm.$wrapper.find(
		'.nav-link[data-fieldname="custom_transporter_details"]'
	);
	if (!$link.length) return;

	// Fill the moment the Transporter Details tab becomes visible.
	$link.off("shown.bs.tab.gatepass").on("shown.bs.tab.gatepass", () => {
		fill_transporter_from_gate_pass(frm);
	});
}

function fill_transporter_from_gate_pass(frm) {
	if (frm.doc.docstatus !== 0) return;

	const pos = [
		...new Set((frm.doc.items || []).map((r) => r.purchase_order).filter(Boolean)),
	];
	if (!pos.length && !frm.doc.custom_gate_pass) return;

	frappe.call({
		method: "pratap_dev.purchase_receipt.get_transporter_from_gate_pass",
		args: { purchase_orders: pos, gate_pass: frm.doc.custom_gate_pass || null },
		callback(r) {
			const data = r.message || {};
			const link_fields = ["transporter", "driver"];
			const data_fields = ["transporter_name", "vehicle_no", "driver_name"];
			const has = (f) => data[f] !== undefined && data[f] !== null && data[f] !== "";

			// Snapshot which GRN fields were empty BEFORE we touch anything, so that even
			// if setting a link auto-fetches (e.g. transporter -> transporter_name), we
			// still honour the Gate Pass value for originally-empty fields.
			const was_empty = {};
			[...link_fields, ...data_fields].forEach((f) => (was_empty[f] = !frm.doc[f]));

			let filled = false;
			link_fields.forEach((f) => {
				if (has(f) && was_empty[f]) {
					frm.set_value(f, data[f]);
					filled = true;
				}
			});

			// Set the plain-data fields after the link fetches settle, so Gate Pass values win.
			setTimeout(() => {
				data_fields.forEach((f) => {
					if (has(f) && was_empty[f]) frm.set_value(f, data[f]);
				});
			}, 400);

			if (filled || data_fields.some((f) => has(f) && was_empty[f])) {
				frappe.show_alert({
					message: __("Transporter details filled from Gate Pass {0}", [
						data._gate_pass,
					]),
					indicator: "green",
				});
			}
		},
	});
}
