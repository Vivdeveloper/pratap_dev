frappe.ui.form.on("Purchase Receipt", {
    refresh(frm) {
        // remove the core button to create quality inspection as per Pratap Quality Inspection requirements
        frm.page.remove_inner_button(__("Quality Inspection(s)"));
    }
});