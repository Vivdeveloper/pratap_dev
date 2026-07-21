import frappe


def run():
	ws = frappe.db.get_value("Material Request", "MAT-MR-2026-00222", "workflow_state")
	print("doc.workflow_state =", repr(ws))
	wf = frappe.get_doc("Workflow", "Material Request")
	print("defined states:")
	for st in wf.states:
		match = "  <-- MATCHES doc" if st.state == ws else ""
		print("   %r  allow_edit=%s%s" % (st.state, st.allow_edit, match))
	# Administrator roles include Manufacturing Manager / Stock Manager?
	roles = frappe.get_roles("Administrator")
	print("Administrator has Manufacturing Manager?", "Manufacturing Manager" in roles)
	print("Administrator has Stock Manager?", "Stock Manager" in roles)
