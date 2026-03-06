// Copyright (c) 2026, saurabh@exacuer.com and contributors
// For license information, please see license.txt

frappe.query_reports["Customer Product Health Index"] = {
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
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -12),
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
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		var status = data && data.health_status;
		var rowBg = (status === "Green" && "#d4edda") || (status === "Amber" && "#fff3cd") || (status === "Red" && "#f8d7da") || "";
		if (rowBg) {
			value = "<span style='background-color:" + rowBg + "; display: block; margin: -4px -8px; padding: 4px 8px;'>" + value + "</span>";
		}
		if (column.df && column.df.fieldname === "health_status" && status) {
			var textColor = status === "Green" ? "#28a745" : status === "Amber" ? "#ffc107" : "#dc3545";
			value = rowBg
				? "<span style='background-color:" + rowBg + "; display: block; margin: -4px -8px; padding: 4px 8px;'><span style='color:" + textColor + "; font-weight: bold;'>" + (data.health_status || "") + "</span></span>"
				: "<span style='color:" + textColor + "; font-weight: bold;'>" + value + "</span>";
		}
		return value;
	},
};
