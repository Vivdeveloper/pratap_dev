// Hide a few Work Order fields from the UI only (non-destructive — the fields and their
// data are untouched; they're just not shown on the form). Done client-side so it works
// even for fields that exist only on some sites (added via Customize Form on prod).

const PRATAP_WO_HIDDEN_FIELDNAMES = [
	"custom_sales_forecast_id",
	"custom_filling_capacity_of_packed_goods",
	"custom_packed_qty_of_blender",
];

// Fallback match by label — covers fields whose fieldname we can't assume (e.g. prod-only
// custom fields not present on local).
const PRATAP_WO_HIDDEN_LABELS = [
	"Filling Capacity of Packed Goods",
	"Sales Forecast ID",
	"Packed Qty of Blender",
];

function hide_pratap_wo_fields(frm) {
	PRATAP_WO_HIDDEN_FIELDNAMES.forEach((fieldname) => {
		if (frm.fields_dict[fieldname]) {
			frm.set_df_property(fieldname, "hidden", 1);
		}
	});

	(frm.meta.fields || []).forEach((df) => {
		if (PRATAP_WO_HIDDEN_LABELS.includes(df.label) && frm.fields_dict[df.fieldname]) {
			frm.set_df_property(df.fieldname, "hidden", 1);
		}
	});
}

frappe.ui.form.on("Work Order", {
	refresh(frm) {
		hide_pratap_wo_fields(frm);
	},
	onload_post_render(frm) {
		hide_pratap_wo_fields(frm);
	},
});
