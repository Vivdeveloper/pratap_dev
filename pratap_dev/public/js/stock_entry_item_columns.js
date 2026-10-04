// Stock Entry — Items grid column control.
//
// 1. Always REMOVE these 4 columns from the Items grid, for every stock entry type.
//    They stay in the row's edit popup (we only drop them from the grid column list;
//    we never set `hidden`, so the detail form still shows them):
//        Allow Zero Valuation Rate, Use Serial No / Batch Fields,
//        Serial and Batch Bundle, Serial No
// 2. Show "Filling Capacity" (fetched from Item.custom_filling_capacity) as a grid
//    column ONLY when Stock Entry Type = "Finished Goods Material Transfer". The field is
//    permanent (always in the row edit popup); only its column visibility toggles.
//
// How: the grid columns are driven by a per-user "Configure Columns" (GridView) setting
// that force-enables the 4 fields, so server-side in_list_view can't control them. We
// correct the column SOURCE inside setup_user_defined_columns (so header + body compute
// the exact same set), and do a full reset_grid() rebuild on load / type change so the
// header and data rows never drift out of sync.

const SE_HIDE_COLS = new Set([
	"allow_zero_valuation_rate",
	"use_serial_batch_fields",
	"serial_and_batch_bundle",
	"serial_no",
]);
const SE_FILLING_CAPACITY = "custom_filling_capacity";
const SE_FG_TRANSFER = "Finished Goods Material Transfer";

frappe.ui.form.on("Stock Entry", {
	onload_post_render(frm) {
		patch_se_items_grid(frm);
		rebuild_se_items_grid(frm);
	},
	refresh(frm) {
		patch_se_items_grid(frm);
		rebuild_se_items_grid(frm);
	},
	stock_entry_type(frm) {
		rebuild_se_items_grid(frm);
	},
});

// Install (once per grid) a wrapper that corrects the column source before the grid
// computes its visible columns.
function patch_se_items_grid(frm) {
	const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
	if (!grid || grid._se_cols_patched) return;

	const original_setup = grid.setup_user_defined_columns.bind(grid);
	grid.setup_user_defined_columns = function () {
		original_setup(); // (re)builds this.user_defined_columns from the user's GridView

		const show_fc = frm.doc.stock_entry_type === SE_FG_TRANSFER;

		// Keep the Filling Capacity docfield's list-view flag in step with the type —
		// covers the case where there is NO user GridView (columns come from docfields).
		const fc_df = (this.docfields || []).find((d) => d.fieldname === SE_FILLING_CAPACITY);
		if (fc_df) {
			fc_df.in_list_view = show_fc ? 1 : 0;
			fc_df.columns = fc_df.columns || 2;
		}

		if (this.user_defined_columns && this.user_defined_columns.length) {
			let cols = this.user_defined_columns.filter(
				(c) => !SE_HIDE_COLS.has(c.fieldname) && c.fieldname !== SE_FILLING_CAPACITY
			);
			if (show_fc && fc_df) {
				const idx = cols.findIndex((c) => c.fieldname === "item_code");
				if (idx >= 0) cols.splice(idx + 1, 0, fc_df);
				else cols.push(fc_df);
			}
			this.user_defined_columns = cols;
		}
	};
	grid._se_cols_patched = true;
}

// Full, clean rebuild so the header row and data rows recompute from the same column set.
function rebuild_se_items_grid(frm) {
	const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
	if (!grid || !grid.reset_grid) return;
	grid.reset_grid();
}
