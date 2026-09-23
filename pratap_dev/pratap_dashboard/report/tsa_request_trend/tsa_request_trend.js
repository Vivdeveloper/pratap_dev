// Copyright (c) 2026, saurabh@exacuer.com and contributors
// For license information, please see license.txt

frappe.query_reports["TSA Request Trend"] = {
	filters: [

		{
			fieldname: "period_type",
			label: __("Period Type"),
			fieldtype: "Select",
			options: ["Financial Year", "Monthly", "Weekly"],
			default: "Financial Year",
			reqd: 1,
		},
		{
			fieldname: "fiscal_year",
			label: __("Fiscal Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today()),
			reqd: 1,
		},
		{
			fieldname: "month",
			label: __("Month"),
			fieldtype: "Select",
			options: [
				"",
				"January",
				"February",
				"March",
				"April",
				"May",
				"June",
				"July",
				"August",
				"September",
				"October",
				"November",
				"December",
			],
			default: [
				"January",
				"February",
				"March",
				"April",
				"May",
				"June",
				"July",
				"August",
				"September",
				"October",
				"November",
				"December",
			][frappe.datetime.str_to_obj(frappe.datetime.get_today()).getMonth()],
			depends_on: "eval:doc.period_type=='Monthly'",
			mandatory_depends_on: "eval:doc.period_type=='Monthly'",
		},
		{
			fieldname: "week_date",
			label: __("Week Of"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			depends_on: "eval:doc.period_type=='Weekly'",
			mandatory_depends_on: "eval:doc.period_type=='Weekly'",
		},

		{
			fieldname: "date_based_on",
			label: __("Date Based On"),
			fieldtype: "Select",
			options: ["Created Date", "Dispatch Date", "Document Creation"],
			default: "Dispatch Date",
			reqd: 1,
		},

		{
			fieldname: "periodicity",
			label: __("Periodicity"),
			fieldtype: "Select",
			options: ["Monthly", "Quarterly", "Yearly"],
			default: "Monthly",
			reqd: 1,
		},

		{
			fieldname: "item_code",
			label: __("Item Code"),
			fieldtype: "Link",
			options: "Item",
		},
		{
			fieldname: "custom_erp",
			label: __("ERP"),
			fieldtype: "Link",
			options: "EPR",
		},
		{
			fieldname: "custom_category_type",
			label: __("Category Type"),
			fieldtype: "Link",
			options: "Category Type",
		},
		{
			fieldname: "custom_material_base",
			label: __("Material Base"),
			fieldtype: "Link",
			options: "Material Base",
		},
		{
			fieldname: "custom_product_type",
			label: __("Product Type"),
			fieldtype: "Link",
			options: "Product Type",
		},
		{
			fieldname: "custom_product_category",
			label: __("Product Category"),
			fieldtype: "Link",
			options: "Product Category",
		},

		{
			fieldname: "tsa_request_type",
			label: __("Request Type"),
			fieldtype: "Select",
			options: ["", "Stock", "Complaint"],
		},
		{
			fieldname: "workflow_state",
			label: __("Status"),
			fieldtype: "Link",
			options: "Workflow State",
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "customer_group",
			label: __("Customer Group"),
			fieldtype: "Link",
			options: "Customer Group",
		},
		{
			fieldname: "territory",
			label: __("Territory"),
			fieldtype: "Data",
		},
		{
			fieldname: "region",
			label: __("Region"),
			fieldtype: "Data",
		},
		{
			fieldname: "creator",
			label: __("Creator"),
			fieldtype: "Link",
			options: "User",
		},
		{
			fieldname: "courier_details",
			label: __("Courier"),
			fieldtype: "Link",
			options: "Courier Details",
		},

	],
};
