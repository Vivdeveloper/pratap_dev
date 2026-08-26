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

        add_material_request_button(frm);

        // Stock columns (Plant 1 / Plant 2 WIP RM + Main Store RM) are NO LONGER
        // auto-fetched on open. They update only when the user clicks "Refresh Stock
        // Count" (draft only), and the fetched snapshot then persists (once saved)
        // until the next click.
        add_refresh_stock_button(frm);
        populate_wo_instructions(frm);
        },

    // When the item / BOM / qty changes, ERPNext re-fetches Required Items from the BOM
    // asynchronously. Re-scan the rows after a short delay so the instruction columns
    // fill in. (Stock counts are intentionally NOT auto-fetched here — button-only.)
    item_to_manufacture(frm) {
        populate_wo_instructions(frm, 1000);
    },
    bom_no(frm) {
        populate_wo_instructions(frm, 1000);
    },
    qty(frm) {
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
                        const next_value = source[fieldname] || "";
                        // Skip when unchanged — always writing here (even when equal)
                        // marks the form dirty on every refresh with no real change.
                        if ((row[fieldname] || "") === next_value) {
                            return;
                        }
                        frappe.model.set_value(row.doctype, row.name, fieldname, next_value, null, true);
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

// Warehouses to show per required-item row: [warehouse_name prefix, target field].
const WO_STOCK_WAREHOUSES = [
    ["Plant 1 WIP RM", "custom_plant_1_wip_rm"],
    ["Plant 2 WIP RM", "custom_plant_2_wip_rm"],
    ["Main Store RM", "custom_main_store_rm"],
];

// "Refresh Stock Count" button — available on draft AND submitted Work Orders. On a
// submitted WO the fetched counts can't be saved (the doc is frozen), so they're just
// an in-session view; the user re-clicks to see fresh numbers. (Cancelled WOs are
// already excluded by the refresh handler's docstatus guard.)
function add_refresh_stock_button(frm) {
    frm.add_custom_button(__("Refresh Stock Count"), () => refresh_wo_stock_counts(frm));
}

// Fetch the latest on-hand counts for EVERY required item, once, on button click.
// Values are written with the dirty flag on so the snapshot persists after Save and
// does not change again until the button is clicked next.
function refresh_wo_stock_counts(frm) {
    const rows = frm.doc.required_items || [];
    if (!rows.length) {
        frappe.msgprint(__("No required items to refresh."));
        return;
    }
    if (!frm.doc.company) {
        frappe.msgprint(__("Set Company before refreshing stock counts."));
        return;
    }

    frappe.dom.freeze(__("Fetching latest stock counts..."));
    Promise.all(rows.map((row) => fetch_row_stock(frm, row)))
        .catch(() => {})
        .then(() => {
            frappe.dom.unfreeze();
            frm.refresh_field("required_items");
            frappe.show_alert(
                { message: __("Stock counts refreshed — Save to persist."), indicator: "green" },
                5
            );
        });
}

// Fetch one required-item row's on-hand stock across the tracked warehouses and write
// it into the read-only columns. Returns a promise that resolves when the row is done.
function fetch_row_stock(frm, row) {
    if (!row || !row.item_code) {
        WO_STOCK_WAREHOUSES.forEach(([, fieldname]) =>
            set_wo_qty_field(row.doctype, row.name, fieldname, 0)
        );
        return Promise.resolve();
    }
    return Promise.all(
        WO_STOCK_WAREHOUSES.map(([warehouse_name, fieldname]) =>
            get_wo_warehouse_stock(row.item_code, warehouse_name, frm.doc.company).then((qty) =>
                set_wo_qty_field(row.doctype, row.name, fieldname, qty)
            )
        )
    );
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
    if (!row) {
        return;
    }
    // Round to a fixed precision so repeated live-stock lookups settle on the same
    // stored value instead of drifting on floating-point noise (these are Data fields
    // with no precision of their own, so nothing normalizes this for us otherwise).
    const next_value = flt(value, 3);
    // Skip when the row already holds a value within tolerance (an unset/null field
    // must still be set to 0). A strict === here false-triggers on float noise.
    const current = row[fieldname];
    if (
        current !== undefined &&
        current !== null &&
        current !== "" &&
        Math.abs(flt(current) - next_value) < 1e-6
    ) {
        return;
    }
    // Mark the form dirty (no skip flag) so the refreshed snapshot can be saved and
    // persists until the user clicks "Refresh Stock Count" again.
    frappe.model.set_value(cdt, cdn, fieldname, next_value);
}


// "Create Material Request" for the required items that are short (MR Qty > 0).
// Fully-stocked rows carry MR Qty 0 and are skipped server-side, so a single item with
// enough stock no longer blocks the request for every other item.
//
// Deliberately a standalone button, not an entry under the "Create" group: the site's
// "Hide Create Dropdown" Client Script hides that whole group 300ms after refresh, which
// would swallow this button too.
function add_material_request_button(frm) {
    if (frm.doc.docstatus !== 1) {
        return;
    }
    const has_shortage = (frm.doc.required_items || []).some(
        (row) => flt(row.custom_qty_amount) > 0
    );
    if (!has_shortage) {
        return;
    }

    frm.add_custom_button(
        __("Create Material Request"),
        () => {
            frappe
                .xcall("pratap_dev.work_order_material_request.create_and_submit_material_request", {
                    work_order_name: frm.doc.name,
                })
                .then((result) => {
                    if (!result) {
                        return;
                    }
                    // Say how many rows were left out, so a short Material Request does not
                    // look like items went missing.
                    const skipped_note = result.skipped
                        ? " " +
                          __("{0} item(s) already in stock were skipped.", [result.skipped])
                        : "";
                    frappe.show_alert({
                        message:
                            __("Material Request {0} submitted.", [result.name]) + skipped_note,
                        indicator: "green",
                    });
                    frappe.set_route("Form", "Material Request", result.name);
                });
        }
    );
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