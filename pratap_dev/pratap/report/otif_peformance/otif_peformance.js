// Copyright (c) 2026, saurabh@exacuer.com and contributors
// For license information, please see license.txt

frappe.query_reports["OTIF Peformance"] = {
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
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -3),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "delivery_status",
			label: __("Delivery Status"),
			fieldtype: "Select",
			options: ["", "On Time", "Delayed", "Not Delivered"],
		},
		{
			fieldname: "otif_status",
			label: __("OTIF Status"),
			fieldtype: "Select",
			options: ["", "Yes", "No"],
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.df && value) {
			if (column.df.fieldname === "delivery_status") {
				var color = value === "On Time" ? "#28a745" : value === "Delayed" ? "#dc3545" : "#6c757d";
				return "<span style='color:" + color + "; font-weight: bold;'>" + value + "</span>";
			}
			if (column.df.fieldname === "otif_status") {
				var color = value === "Yes" ? "#28a745" : "#dc3545";
				return "<span style='color:" + color + "; font-weight: bold;'>" + value + "</span>";
			}
		}
		return value;
	},
};
