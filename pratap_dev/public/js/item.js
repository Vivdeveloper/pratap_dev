frappe.ui.form.on("Item", {
	setup(frm) {
		// Manufacturing Location: only the FG WIP warehouses (Plant 1 WIP FG / Plant 2 WIP FG).
		frm.set_query("custom_manufacturing_location", function () {
			return {
				filters: {
					is_group: 0,
					warehouse_name: ["like", "%Plant%WIP FG%"],
				},
			};
		});

		// Job Work Warehouse: only the JOB WORK warehouses (Plant 1 / Plant 2 WIP RM- JOB WORK).
		frm.set_query("custom_job_work_warehouse", function () {
			return {
				filters: {
					is_group: 0,
					warehouse_name: ["like", "%JOB WORK%"],
				},
			};
		});
	},
});
