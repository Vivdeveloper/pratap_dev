// BOM — inline warning under the Item field.
//
// As soon as an Item is selected (or on opening a BOM), if that item already has ANOTHER
// BOM that is both Active and Default, show a small yellow warning right below the Item
// dropdown. Purely informational — nothing is blocked or changed.

frappe.ui.form.on("BOM", {
	item(frm) {
		check_existing_default_bom(frm);
	},
	refresh(frm) {
		check_existing_default_bom(frm);
	},
});

function check_existing_default_bom(frm) {
	const field = frm.fields_dict.item;
	if (!field || !field.$wrapper) return;

	const clear = () => field.$wrapper.find(".bom-default-warning").remove();

	if (!frm.doc.item) {
		clear();
		return;
	}

	frappe.db
		.get_list("BOM", {
			filters: {
				item: frm.doc.item,
				is_active: 1,
				is_default: 1,
				name: ["!=", frm.doc.name || ""],
			},
			fields: ["name"],
			limit: 1,
		})
		.then((rows) => {
			clear();
			if (rows && rows.length) {
				const msg = __(
					"⚠️ An active & default BOM ({0}) already exists for this item.",
					[frappe.utils.escape_html(rows[0].name)]
				);
				const $warn = $(
					`<div class="bom-default-warning" style="margin-top:6px;padding:6px 10px;` +
						`background:#fff3cd;border:1px solid #ffe69c;border-radius:6px;` +
						`color:#8a6d3b;font-size:12px;line-height:1.4;">${msg}</div>`
				);
				field.$wrapper.append($warn);
			}
		});
}
