// Copyright (c) 2026, saurabh@exacuer.com and contributors
// For license information, please see license.txt

frappe.query_reports["CRM"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -12),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "prospect",
			label: __("Prospect"),
			fieldtype: "Link",
			options: "Prospect",
		},
		{
			fieldname: "territory",
			label: __("Territory"),
			fieldtype: "Link",
			options: "Territory",
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		// Highlight stage columns when value present (flow progress)
		if (column.df && data) {
			var fn = column.df.fieldname;
			if (fn === "sample_request" && data.sample_request) {
				value = "<span style='color:#0d6efd;'>" + value + "</span>";
			}
			if (fn === "product_trial" && data.product_trial) {
				value = "<span style='color:#0d6efd;'>" + value + "</span>";
			}
			if (fn === "quotation" && data.quotation) {
				value = "<span style='color:#28a745; font-weight: bold;'>" + value + "</span>";
			}
			if (fn === "trial_status" && data.trial_status === "Successful") {
				value = "<span style='color:#28a745;'>" + value + "</span>";
			}
			if (fn === "conversion_done") {
				if (data.conversion_done === __("Done")) {
					value = "<span style='color:#28a745; font-weight: bold;'>" + value + "</span>";
				} else {
					value = "<span style='color:#6c757d;'>" + value + "</span>";
				}
			}
		}
		return value;
	},
};
