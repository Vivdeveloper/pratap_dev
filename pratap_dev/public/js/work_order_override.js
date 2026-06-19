frappe.ui.form.on("Work Order", {
    refresh(frm) {
        if (![0, 1].includes(frm.doc.docstatus)) {
            return;
        }
        if (frm.doc.custom_rework_qc && frm.doc.docstatus != 1) {
            handle_rework_consumption(frm);
        }
        if(frm.doc.docstatus != 1) {
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
        }
        },
});


function handle_rework_consumption(frm) {
    frm.add_custom_button(__("Rework Consumption"), () => {
        if (!frm.doc.custom_rework_qc) {
            frappe.msgprint(__("No Rework QC is linked to this Work Order."));
            return;
        }

        frappe.xcall(
            "pratap_dev.pratap.doctype.pratap_quality_inspection.pratap_quality_inspection.get_rework_stock_entry",
            {
                work_order_name: frm.doc.name,
            }
        ).then((stock_entry) => {
            frappe.model.sync(stock_entry);
            frappe.set_route("Form", "Stock Entry", stock_entry.name);
        });
        }, "").addClass("btn-primary");
}