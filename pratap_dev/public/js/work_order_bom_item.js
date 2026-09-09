// Show the frozen "BOM Item" for each required item, with correct names/links.
//
// custom_bom_item records what the BOM originally called for. We populate it in
// the browser on load (= item_code when empty), BEFORE any "Alternate Item" swap,
// so it stays fixed on the original recipe item. The server (before_validate)
// persists the same value on save (using original_item as a fallback).
//
// We also keep the displayed item NAMES correct:
//   - Item Code cell: after a swap ERPNext changes item_code but not item_name,
//     leaving a stale "code: name". We refresh item_name from the new code.
//   - BOM Item cell: it's a Link to Item; the grid needs the item's title in the
//     link-title cache to show "code: name". We prime that cache.

frappe.provide("pratap_dev");

// Capture custom_bom_item = item_code (when empty) for every required item.
pratap_dev.set_bom_items = function (frm) {
	(frm.doc.required_items || []).forEach((row) => {
		if (!row.custom_bom_item && row.item_code) {
			// set directly (not via set_value) so we don't mark the form dirty on load
			row.custom_bom_item = row.item_code;
		}
	});
};

// Keep item names/titles correct so both columns read "code: name".
//
// ERPNext's Item link formatter shows "code: name" only when the cell value equals
// the row's item_code (using the row's single item_name). So:
//   - Item Code: we refresh the row's item_name after a swap (else it's stale).
//   - BOM Item: for a SWAPPED row its value != item_code, so the formatter would
//     show a bare code. For those rows only, we prime the link-title cache with
//     "code: name" so the BOM Item cell still shows the original code and name.
pratap_dev.fix_item_titles = function (frm) {
	const rows = frm.doc.required_items || [];
	const codes = new Set();
	rows.forEach((r) => {
		if (r.item_code) codes.add(r.item_code);
		if (r.custom_bom_item) codes.add(r.custom_bom_item);
	});
	if (!codes.size) return;

	frappe.db
		.get_list("Item", {
			filters: { name: ["in", Array.from(codes)] },
			fields: ["name", "item_name"],
			limit: 0,
		})
		.then((items) => {
			const name_map = {};
			items.forEach((it) => (name_map[it.name] = it.item_name));

			rows.forEach((r) => {
				// Item Code column: keep the row's item_name in sync with item_code.
				if (r.item_code && name_map[r.item_code] && r.item_name !== name_map[r.item_code]) {
					r.item_name = name_map[r.item_code];
				}
				// BOM Item column: only swapped rows need a primed "code: name" title.
				if (r.custom_bom_item && r.custom_bom_item !== r.item_code) {
					const nm = name_map[r.custom_bom_item];
					if (nm && nm !== r.custom_bom_item) {
						frappe.utils.add_link_title(
							"Item",
							r.custom_bom_item,
							r.custom_bom_item + ": " + nm
						);
					}
				}
			});
			if (frm.fields_dict.required_items) {
				frm.fields_dict.required_items.grid.refresh();
			}
		});
};

pratap_dev.refresh_bom_items = function (frm) {
	pratap_dev.set_bom_items(frm);
	pratap_dev.fix_item_titles(frm);
};

frappe.ui.form.on("Work Order", {
	refresh(frm) {
		pratap_dev.refresh_bom_items(frm);
	},
	onload_post_render(frm) {
		pratap_dev.refresh_bom_items(frm);
	},
});

frappe.ui.form.on("Work Order Item", {
	item_code(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		// Only capture BOM item when empty — a swap changes item_code but must not
		// overwrite an already-captured BOM item.
		if (row && !row.custom_bom_item && row.item_code) {
			row.custom_bom_item = row.item_code;
		}
		// A swap changed item_code: refresh names/titles so both columns read right.
		pratap_dev.fix_item_titles(frm);
	},
});
