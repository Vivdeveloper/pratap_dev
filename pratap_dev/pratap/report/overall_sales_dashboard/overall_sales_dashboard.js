// Copyright (c) 2026, saurabh@exacuer.com and contributors
// For license information, please see license.txt

frappe.query_reports["Overall Sales Dashboard"] = {
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
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
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
			fieldname: "fiscal_year",
			label: __("Fiscal Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			default: frappe.sys_defaults.fiscal_year,
		},
		{
			fieldname: "sales_person",
			label: __("Sales Person"),
			fieldtype: "Link",
			options: "Sales Person",
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		// Total row: bind each column to the correct field so alignment is guaranteed
		if (data && data.customer === __("Total") && column.df && column.df.fieldname) {
			const fn = column.df.fieldname;
			if (fn === "customer") {
				value = default_formatter(value, row, column, data);
				return value ? "<b>" + value + "</b>" : value;
			}
			if (fn === "revenue") return default_formatter(data.revenue, row, column, data);
			if (fn === "order_count") return default_formatter(data.order_count, row, column, data);
			if (fn === "target") return default_formatter(data.target, row, column, data);
			if (fn === "achieved") return default_formatter(data.achieved, row, column, data);
			// Empty columns in Total row (links, dates)
			if (["sales_person", "enquiry_id", "sales_order_id", "invoice_id", "order_date", "invoice_date"].includes(fn)) {
				return default_formatter("", row, column, data);
			}
		}
		return default_formatter(value, row, column, data);
	},
};
