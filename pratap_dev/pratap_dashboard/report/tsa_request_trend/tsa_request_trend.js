frappe.query_reports["TSA Request Trend"] = {
	filters: [

		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today(), true)[1],
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today(), true)[2],
			reqd: 1,
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
		{
			fieldname: "item_code",
			label: __("Item"),
			fieldtype: "Link",
			options: "Item",
		},
	],
};
