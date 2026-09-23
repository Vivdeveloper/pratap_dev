# Copyright (c) 2026, saurabh@exacuer.com and contributors
# For license information, please see license.txt

from erpnext.accounts.utils import get_fiscal_year
from frappe import _
from frappe.utils import (
	add_months,
	cint,
	get_first_day,
	get_first_day_of_week,
	get_last_day,
	get_last_day_of_week,
	getdate,
	nowdate,
)


def apply_period_filters(filters, require_limit=True):
	"""Resolve from_date/to_date from Financial Year / Monthly / Weekly period filters."""
	from frappe import throw

	period_type = filters.get("period_type") or "Financial Year"
	if period_type not in ("Financial Year", "Monthly", "Weekly"):
		throw(_("Please select a valid Period Type."))

	filters.period_type = period_type

	if not filters.get("fiscal_year"):
		filters.fiscal_year = get_fiscal_year(nowdate())[0]

	from_date, to_date = get_period_dates(filters)
	filters.from_date = from_date
	filters.to_date = to_date

	if require_limit:
		limit = cint(filters.get("limit") or 10)
		if limit < 1:
			throw(_("Limit must be at least 1."))
		filters.limit = limit

	return filters


def get_month_number(month):
	months = {
		"January": 1,
		"February": 2,
		"March": 3,
		"April": 4,
		"May": 5,
		"June": 6,
		"July": 7,
		"August": 8,
		"September": 9,
		"October": 10,
		"November": 11,
		"December": 12,
	}
	if month in months:
		return months[month]
	return cint(month) or getdate().month


def get_period_dates(filters):
	from frappe import throw

	fiscal_year = get_fiscal_year(fiscal_year=filters.fiscal_year, as_dict=True)
	year_start = getdate(fiscal_year.year_start_date)
	year_end = getdate(fiscal_year.year_end_date)

	if filters.period_type == "Monthly":
		month = get_month_number(filters.get("month"))
		current = get_first_day(year_start)
		matched = None
		while current <= year_end:
			if current.month == month:
				matched = current
				break
			current = add_months(current, 1)
		if not matched:
			throw(_("Selected month is not in Fiscal Year {0}.").format(filters.fiscal_year))
		return matched, get_last_day(matched)

	if filters.period_type == "Weekly":
		week_date = getdate(filters.get("week_date") or nowdate())
		from_date = get_first_day_of_week(week_date)
		to_date = get_last_day_of_week(week_date)
		if from_date < year_start:
			from_date = year_start
		if to_date > year_end:
			to_date = year_end
		if from_date > to_date:
			throw(_("Selected week is not in Fiscal Year {0}.").format(filters.fiscal_year))
		return from_date, to_date

	return year_start, year_end
