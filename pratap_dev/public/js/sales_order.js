// Live credit / payment info on the Sales Order form.
// Fields are read-only and auto-populated; see pratap_dev/sales_order_financials.py.

frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		pratap_load_so_financials(frm);
	},
	customer(frm) {
		pratap_load_so_financials(frm);
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
			// Set in-memory + refresh only (does NOT dirty the form).
			frm.doc.custom_credit_limit = m.credit_limit;
			frm.doc.custom_current_outstanding = m.current_outstanding;
			frm.doc.custom_payment_received_against_order = m.payment_received;
			frm.refresh_field("custom_credit_limit");
			frm.refresh_field("custom_current_outstanding");
			frm.refresh_field("custom_payment_received_against_order");
		},
	});
}
