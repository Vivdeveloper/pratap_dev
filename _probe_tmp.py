import frappe

def run():
    print("PROBE| START")
    log = []
    GRN = "PR-26-00057"
    try:
        from pratap_dev.purchase_receipt import create_rejection_documents_if_any
        grn = frappe.get_doc("Purchase Receipt", GRN)
        print("PROBE| calling function...")
        create_rejection_documents_if_any(grn)
        print("PROBE| function returned")
        rets = frappe.get_all("Purchase Receipt",
            filters={"return_against": GRN, "is_return": 1},
            fields=["name","docstatus","custom_grn_group_id"])
        log.append("RETURNS=%s" % rets)
        for r in rets:
            dns = frappe.get_all("Purchase Invoice",
                filters={"return_against": r.name, "is_return": 1},
                fields=["name","docstatus","custom_grn_group_id","bill_no"])
            log.append("DEBIT NOTES for %s = %s" % (r.name, dns))
    except Exception as e:
        import traceback
        log.append("ERR: " + repr(e)[:250])
        log.append("TB: " + traceback.format_exc()[-1000:].replace(chr(10), " || "))
    finally:
        frappe.db.rollback()
        log.append("ROLLED BACK")
    for l in log:
        print("PROBE| " + l)
