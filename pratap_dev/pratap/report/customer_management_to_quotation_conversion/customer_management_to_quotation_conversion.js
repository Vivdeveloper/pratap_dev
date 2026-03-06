// Copyright (c) 2026, saurabh@exacuer.com and contributors
// For license information, please see license.txt

frappe.query_reports["Customer Management to Quotation Conversion"] = {
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
		if (column.df && column.df.fieldname === "converted_to_quotation" && data) {
			var converted = data.converted_to_quotation;
			if (converted === __("Yes")) {
				value = "<span style='color:#28a745; font-weight: bold;'>" + value + "</span>";
			} else {
				value = "<span style='color:#6c757d;'>" + value + "</span>";
			}
		}
		return value;
	},
};
