# Copyright (c) 2026, pratap_dev contributors
# License: MIT

"""Delete orphan Request for Quotation child rows whose parent RFQ no longer exists.

The supplier portal list page (/rfq) builds its list from `Request for Quotation Supplier`
rows and then loads each parent RFQ with frappe.get_doc(). If an RFQ was deleted but a
child row survived (an orphan), get_doc() raises DoesNotExistError and the whole /rfq page
throws "Uncaught Server Exception" for that supplier. Removing the orphan child rows — which
reference nothing and are invalid data — fixes the crash. Idempotent."""

import frappe

RFQ_CHILD_TABLES = [
	"Request for Quotation Supplier",
	"Request for Quotation Item",
]


def execute():
	for child in RFQ_CHILD_TABLES:
		if not frappe.db.table_exists(child):
			continue
		frappe.db.sql(
			"""
			DELETE c FROM `tab{child}` c
			LEFT JOIN `tabRequest for Quotation` rq ON rq.name = c.parent
			WHERE c.parenttype = 'Request for Quotation' AND rq.name IS NULL
			""".format(child=child)
		)
	frappe.db.commit()
