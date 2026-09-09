// Copyright (c) 2026, exacuer and contributors
// For license information, please see license.txt

frappe.query_reports["Customer Growth"] = {
	filters: [
		{
			fieldname: "show_yearly",
			label: __("Show Yearly"),
			fieldtype: "Check",
			default: 0,
		},
		{
			fieldname: "fiscal_year",
			label: __("Fiscal Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today()),
			depends_on: "eval:!doc.show_yearly",
			mandatory_depends_on: "eval:!doc.show_yearly",
		},
	],
};
