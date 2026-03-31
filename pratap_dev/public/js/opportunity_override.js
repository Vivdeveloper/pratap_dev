function set_opportunity_from_options(frm) {
    frm.set_df_property("opportunity_from", "options", "\nCustomer\nProspect");
}

frappe.ui.form.on("Opportunity", {
    setup(frm) {
        set_opportunity_from_options(frm);
    },
    refresh(frm) {
        set_opportunity_from_options(frm);
    },
});