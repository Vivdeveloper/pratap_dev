// Live credit / payment info on the Sales Order form + credit-limit gating of the
// Delivery Note button. See pratap_dev/sales_order_financials.py.

frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		pratap_load_so_financials(frm);
	},
	customer(frm) {
		pratap_load_so_financials(frm);
	},
	custom_allow_access_order(frm) {
		// Re-evaluate button/warning immediately when the override is toggled.
		pratap_apply_credit_gate(frm, frm._pratap_fin);
	},
});

function pratap_load_so_financials(frm) {
	if (!frm.doc.customer || !frm.doc.company) return;

	frappe.call({
		method: "pratap_dev.sales_order_financials.get_sales_order_financials",
		args: {
			customer: frm.doc.customer,
			company: frm.doc.company,
			sales_order: frm.doc.__islocal ? null : frm.doc.name,
		},
		callback(r) {
			if (!r || !r.message) return;
			const m = r.message;
			frm._pratap_fin = m;

			// Set in-memory + refresh only (does NOT dirty the form).
			frm.doc.custom_credit_limit = m.credit_limit;
			frm.doc.custom_current_outstanding = m.current_outstanding;
			frm.doc.custom_payment_received_against_order = m.payment_received;
			frm.refresh_field("custom_credit_limit");
			frm.refresh_field("custom_current_outstanding");
			frm.refresh_field("custom_payment_received_against_order");

			pratap_apply_credit_gate(frm, m);
		},
	});
}

function pratap_apply_credit_gate(frm, m) {
	if (!m) return;

	const credit_limit = flt(m.credit_limit);
	const outstanding = flt(m.current_outstanding);
	const this_order = flt(frm.doc.grand_total);
	const over_limit = credit_limit > 0 && this_order + outstanding > credit_limit;
	const allowed = !over_limit || frm.doc.custom_allow_access_order;

	// Clear any previous banner before re-deciding.
	frm.dashboard.clear_comment();

	if (over_limit && !allowed) {
		// Hide the Delivery Note button(s) until the order is allowed.
		frm.remove_custom_button(__("Delivery Note"), __("Create"));
		frm.remove_custom_button(__("Delivery Note"));

		const fmt = (v) => format_currency(v, frm.doc.currency);
		frm.dashboard.add_comment(
			__(
				"Credit limit exceeded — Limit {0}, Outstanding {1}, This Order {2}. " +
					"Tick <b>Allow Access Order</b> to override.",
				[fmt(credit_limit), fmt(outstanding), fmt(this_order)]
			),
			"red",
			true
		);
	}
}
