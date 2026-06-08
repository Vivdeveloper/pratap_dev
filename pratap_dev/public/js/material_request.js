frappe.ui.form.on("Material Request", {
    refresh(frm) {
        console.log("Material Request form refreshed");
        frm.remove_custom_button(__("Purchase Order"),__("Create"));
    }
})