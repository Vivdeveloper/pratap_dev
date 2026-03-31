frappe.ui.form.on('Opportunity', {
    setup(frm) {

        // Completely override options
        frm.fields_dict.opportunity_from.df.options = [
            "",
            "Customer",
            "Prospect"   // or your "Customer Management"
        ];

        frm.refresh_field('opportunity_from');
    }
});