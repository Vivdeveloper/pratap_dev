// Copyright (c) 2026, saurabh@exacuer.com and contributors
// For license information, please see license.txt

frappe.query_reports["Sample to Order Conversion"] = {
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
			fieldname: "conversion_status",
			label: __("Conversion Status"),
			fieldtype: "Select",
			options: ["", "Converted", "Not Converted"],
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.df && column.df.fieldname === "conversion_status" && value) {
			var color = value === "Converted" ? "#28a745" : "#6c757d";
			return "<span style='color:" + color + "; font-weight: bold;'>" + value + "</span>";
		}
		return value;
	},
};
