# Copyright (c) 2026, exacuer and contributors
# For license information, please see license.txt

import frappe
from erpnext.accounts.utils import get_fiscal_year
from frappe import _
from frappe.query_builder.functions import Count, Extract
from frappe.utils import add_days, add_months, getdate, nowdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	show_yearly = bool(filters.get("show_yearly"))

	if show_yearly:
		columns = get_columns(_("Year"))
		data = get_yearly_data()
	else:
		fiscal_year = get_selected_fiscal_year(filters.get("fiscal_year"))
		columns = get_columns(_("Month"))
		data = get_monthly_data(fiscal_year.year_start_date, fiscal_year.year_end_date)

	return columns, data, None, get_chart(data)


def get_columns(period_label):
	return [
		{
			"fieldname": "period",
			"label": period_label,
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"fieldname": "customer_count",
			"label": _("Customers Created"),
			"fieldtype": "Int",
			"width": 160,
		},
	]


def get_selected_fiscal_year(fiscal_year_name=None):
	if fiscal_year_name:
		return get_fiscal_year(fiscal_year=fiscal_year_name, as_dict=True)

	return get_fiscal_year(nowdate(), as_dict=True)


def get_monthly_data(year_start_date, year_end_date):
	Customer = frappe.qb.DocType("Customer")
	year = Extract("year", Customer.creation)
	month = Extract("month", Customer.creation)

	counts = (
		frappe.qb.from_(Customer)
		.select(year.as_("year"), month.as_("month"), Count(Customer.name).as_("customer_count"))
		.where(Customer.creation >= year_start_date)
		.where(Customer.creation < add_days(year_end_date, 1))
		.groupby(year, month)
		.run(as_dict=True)
	)
	count_by_month = {(row.year, row.month): row.customer_count for row in counts}

	data = []
	current_month = getdate(year_start_date).replace(day=1)
	last_month = getdate(year_end_date).replace(day=1)
	while current_month <= last_month:
		data.append(
			{
				"period": current_month.strftime("%b %Y"),
				"customer_count": count_by_month.get((current_month.year, current_month.month), 0),
			}
		)
		current_month = add_months(current_month, 1)

	return data


def get_yearly_data():
	Customer = frappe.qb.DocType("Customer")
	year = Extract("year", Customer.creation)

	counts = (
		frappe.qb.from_(Customer)
		.select(year.as_("year"), Count(Customer.name).as_("customer_count"))
		.groupby(year)
		.orderby(year)
		.run(as_dict=True)
	)

	return [{"period": str(row.year), "customer_count": row.customer_count} for row in counts]


def get_chart(data):
	return {
		"data": {
			"labels": [row["period"] for row in data],
			"datasets": [
				{
					"name": _("Customers Created"),
					"values": [row["customer_count"] for row in data],
				}
			],
		},
		"type": "bar",
		"colors": ["#5e64ff"],
	}
