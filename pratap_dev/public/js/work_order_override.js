frappe.ui.form.on("Work Order", {
    refresh(frm) {
        if (![0, 1].includes(frm.doc.docstatus)) {
            return;
        }
        // Show the Rework Consumption button whenever a Rework QC is linked — on both
        // draft and submitted Work Orders (rework typically happens on a submitted WO,
        // where the button used to disappear).
        if (frm.doc.custom_rework_qc) {
            handle_rework_consumption(frm);
        }
        // Show "Create Pratap QC" for both draft and submitted Work Orders
        // (no longer hidden once the Work Order is submitted).
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

        // Populate the Plant 1 / Plant 2 WIP RM (and Main Store RM) stock columns for
        // every required item on a draft Work Order.
        populate_wo_stock_all(frm);
        populate_wo_instructions(frm);
        },

    // When the item / BOM / qty changes, ERPNext re-fetches Required Items from the BOM
    // asynchronously. Re-scan the rows after a short delay so the stock columns fill in.
    item_to_manufacture(frm) {
        populate_wo_stock_all(frm, 1000);
        populate_wo_instructions(frm, 1000);
    },
    bom_no(frm) {
        populate_wo_stock_all(frm, 1000);
        populate_wo_instructions(frm, 1000);
    },
    qty(frm) {
        populate_wo_stock_all(frm, 1000);
        populate_wo_instructions(frm, 1000);
    },
});

// Copy the Operation Instruction columns from the BOM onto the Required Items rows.
// The server sets these on validate too; doing it here as well means they show up as
// soon as the rows appear, rather than only after the first save.
function populate_wo_instructions(frm, delay) {
    if (frm.doc.docstatus !== 0 || !frm.doc.bom_no) {
        return;
    }
    const run = () => {
        frappe
            .xcall("pratap_dev.work_order_instruction.get_bom_operation_instructions", {
                bom_no: frm.doc.bom_no,
            })
            .then((instructions) => {
                (frm.doc.required_items || []).forEach((row) => {
                    // A multi-level BOM explodes sub-assemblies, so some rows have no
                    // BOM Item row on this BOM; leave those blank.
                    const source = instructions[row.item_code] || {};
                    WO_INSTRUCTION_FIELDS.forEach((fieldname) => {
                        frappe.model.set_value(
                            row.doctype,
                            row.name,
                            fieldname,
                            source[fieldname] || "",
                            null,
                            true
                        );
                    });
                });
            })
            .catch(() => {});
    };
    if (delay) {
        setTimeout(run, delay);
    } else {
        run();
    }
}

const WO_INSTRUCTION_FIELDS = [
    "custom_operation_instruction",
    "custom_operation_instruction_marathi",
];

frappe.ui.form.on("Work Order Item", {
    item_code(frm, cdt, cdn) {
        set_wo_warehouse_stock(frm, cdt, cdn);
    },
});

// Scan every Required Items row and fill its warehouse stock columns. Optional `delay`
// (ms) waits for BOM-driven row population to finish before scanning.
function populate_wo_stock_all(frm, delay) {
    if (frm.doc.docstatus !== 0) {
        return;
    }
    const run = () =>
        (frm.doc.required_items || []).forEach((row) =>
            set_wo_warehouse_stock(frm, row.doctype, row.name)
        );
    if (delay) {
        setTimeout(run, delay);
    } else {
        run();
    }
}

// Warehouses to show per required-item row: [warehouse_name prefix, target field].
const WO_STOCK_WAREHOUSES = [
    ["Plant 1 WIP RM", "custom_plant_1_wip_rm"],
    ["Plant 2 WIP RM", "custom_plant_2_wip_rm"],
    ["Main Store RM", "custom_main_store_rm"],
];

// Fetch each required item's on-hand stock in the Plant 1 / Plant 2 WIP RM (and Main
// Store RM) warehouses and write it into the read-only columns on the row.
function set_wo_warehouse_stock(frm, cdt, cdn) {
    if (frm.doc.docstatus !== 0) {
        return;
    }
    const row = locals[cdt][cdn];
    if (!row || !row.item_code || !frm.doc.company) {
        WO_STOCK_WAREHOUSES.forEach(([, fieldname]) => set_wo_qty_field(cdt, cdn, fieldname, 0));
        return;
    }
    WO_STOCK_WAREHOUSES.forEach(([warehouse_name, fieldname]) => {
        get_wo_warehouse_stock(row.item_code, warehouse_name, frm.doc.company).then((qty) => {
            set_wo_qty_field(cdt, cdn, fieldname, qty);
        });
    });
}

// Warehouse names may carry a trailing space (e.g. "Plant 1 WIP RM "), so match by prefix.
function get_wo_warehouse_stock(item_code, warehouse_name, company) {
    return frappe.db
        .get_list("Warehouse", {
            filters: { warehouse_name: ["like", `${warehouse_name}%`], company: company },
            fields: ["name"],
            limit: 1,
        })
        .then((rows) => {
            const warehouse = rows && rows.length ? rows[0].name : null;
            if (!warehouse) {
                return 0;
            }
            return frappe
                .xcall("erpnext.stock.utils.get_latest_stock_qty", { item_code, warehouse })
                .then((qty) => flt(qty));
        })
        .catch(() => 0);
}

function set_wo_qty_field(cdt, cdn, fieldname, value) {
    const row = locals[cdt][cdn];
    const next_value = flt(value);
    // Always write a number so "no stock" shows 0, not blank. Skip only when the row
    // already holds a value equal to it (an unset/null field must still be set to 0).
    const current = row[fieldname];
    if (current !== undefined && current !== null && current !== "" && flt(current) === next_value) {
        return;
    }
    frappe.model.set_value(cdt, cdn, fieldname, next_value, null, true);
}


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