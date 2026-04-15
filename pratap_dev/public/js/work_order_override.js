frappe.ui.form.on("Work Order", {
    refresh(frm) {
        if (frm.doc.docstatus != 1) {
            return;
        }

        frm.add_custom_button(__("Create QC"), () => {
            frappe.new_doc("Pratap Quality Inspection", {
                work_order: frm.doc.name,
                company: frm.doc.company,
                production_item: frm.doc.production_item,
                item_name: frm.doc.item_name,
                reference_qty: frm.doc.qty,
            });
        });
    },
});

