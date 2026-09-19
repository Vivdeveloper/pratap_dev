import frappe

def total_unique_customers():
    return frappe.db.count("Customer", filters={"customer_group": "Customer"})