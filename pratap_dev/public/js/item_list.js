frappe.listview_settings["Item"] = {
	onload(listview) {
		// Global button: compute + save each item's average monthly procurement over the
		// last completed quarter (item + its alternates, total received / 3 months) into
		// custom_quarterly_avg_procurement. Runs for all main items of Item Alternative
		// groups (a quarterly cron will call the same server method later).
		listview.page.add_inner_button(__("Update Quarterly Avg Procurement"), () => {
			frappe.confirm(
				__(
					"Compute the last completed quarter's average monthly procurement (item + alternates, received / 3) and save it on each item? This runs for every item that has alternates."
				),
				() => {
					frappe.call({
						method: "pratap_dev.item_quarterly_procurement.update_quarterly_avg",
						freeze: true,
						freeze_message: __("Calculating quarterly averages…"),
						callback(r) {
							const m = r.message || {};
							frappe.msgprint({
								title: __("Quarterly Avg Procurement Updated"),
								indicator: "green",
								message: __(
									"Updated {0} item(s) for {1}. The value is saved on each item as <b>Quarterly Avg Procurement (per month)</b>.",
									[m.updated || 0, m.quarter || "-"]
								),
							});
							listview.refresh();
						},
					});
				}
			);
		});
	},
};
