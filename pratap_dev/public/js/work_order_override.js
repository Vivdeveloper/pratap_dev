frappe.ui.form.on("Work Order", {
    refresh(frm) {
        if (frm.doc.docstatus != 1) {
            return;
        }

        frm.add_custom_button(__("Create Pratap QC"), () => {
            frappe.new_doc("Pratap Quality Inspection", {
                inspection_type: "In Process",
                reference_type: "Work Order",
                reference_doctype: "Work Order",
                reference_name: frm.doc.name,
                company: frm.doc.company,
                production_item: frm.doc.production_item,
                item_name: frm.doc.item_name,
                reference_qty: frm.doc.qty,
            });
        });
    },
});

