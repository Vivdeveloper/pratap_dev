// Copyright (c) 2026, saurabh@exacuer.com and contributors
// For license information, please see license.txt

frappe.query_reports["Receivable Aging"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "as_on_date",
			label: __("As On Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("Invoice From Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("Invoice To Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "aging_bucket",
			label: __("Aging Bucket"),
			fieldtype: "Select",
			options: ["", "Not Due", "0-30", "30-60", "60-90", "90+"],
		},
		{
			fieldname: "show_only_outstanding",
			label: __("Show Only Outstanding"),
			fieldtype: "Check",
			default: 1,
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.df && column.df.fieldname === "aging_bucket" && value) {
			var color = value === "Not Due" ? "#28a745" : value === "90+" ? "#dc3545" : value === "60-90" ? "#fd7e14" : "#ffc107";
			return "<span style='color:" + color + "; font-weight: bold;'>" + value + "</span>";
		}
		return value;
	},
};
