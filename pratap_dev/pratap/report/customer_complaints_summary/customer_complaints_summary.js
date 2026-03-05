// Copyright (c) 2026, saurabh@exacuer.com and contributors
// For license information, please see license.txt

frappe.query_reports["Customer Complaints Summary"] = {
	filters: [
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
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Opened", "In Progress", "Closed", "Draft"],
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.df && column.df.fieldname === "status" && value) {
			var color = value === "Closed" ? "#28a745" : value === "In Progress" ? "#ffc107" : "#6c757d";
			return "<span style='color:" + color + "; font-weight: bold;'>" + value + "</span>";
		}
		if (column.df && column.df.fieldname === "risk_level" && value && value !== "—") {
			var color = value === "High" ? "#dc3545" : value === "Medium" ? "#fd7e14" : "#28a745";
			return "<span style='color:" + color + "'>" + value + "</span>";
		}
		return value;
	},
};
