// Copyright (c) 2026, pratap_dev contributors
// For license information, please see license.txt

frappe.query_reports["Quotation Comparison Sheet"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -3),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "item_code",
			label: __("Item Code"),
			fieldtype: "Link",
			options: "Item",
		},
		{
			fieldname: "material_request",
			label: __("Material Request (PR)"),
			fieldtype: "Link",
			options: "Material Request",
		},
		{
			fieldname: "request_for_quotation",
			label: __("RFQ"),
			fieldtype: "Link",
			options: "Request for Quotation",
		},
		{
			fieldname: "purchase_order",
			label: __("Purchase Order"),
			fieldtype: "Link",
			options: "Purchase Order",
		},
		{
			fieldname: "supplier",
			label: __("Supplier"),
			fieldtype: "Link",
			options: "Supplier",
		},
		{
			fieldname: "sq_state",
			label: __("Supplier Quotation State"),
			fieldtype: "Select",
			options: ["", "Draft", "Submitted"].join("\n"),
		},
		{
			fieldname: "rfq_status",
			label: __("RFQ Status"),
			fieldtype: "Select",
			options: ["", "Draft", "Submitted", "Cancelled"].join("\n"),
		},
		{
			fieldname: "po_status",
			label: __("PO Status"),
			fieldtype: "Select",
			options: [
				"",
				"Draft",
				"On Hold",
				"To Receive and Bill",
				"To Bill",
				"To Receive",
				"Completed",
				"Closed",
				"Cancelled",
			].join("\n"),
		},
		{
			fieldname: "po_rank",
			label: __("PO Placed at Rank"),
			fieldtype: "Select",
			options: ["", "L1", "L2", "L3"].join("\n"),
		},
	],
};
