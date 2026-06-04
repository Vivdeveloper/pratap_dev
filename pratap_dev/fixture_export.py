# Copyright (c) 2026, pratap_dev contributors
# License: MIT

import json
import os

import frappe
from frappe import _
from frappe.core.doctype.data_import.data_import import import_doc
from frappe.utils.fixtures import export_json

PRATAP_MODULE = "pratap"
APP_NAME = "pratap_dev"
CUSTOM_FIELD_FIXTURE_FILE = "custom_field.json"


def setup_fixture_import():
	"""Patch fixture import so custom_field.json skips already-created fields."""
	import frappe.utils.fixtures as fixtures_module

	if getattr(fixtures_module, "_pratap_fixture_patched", False):
		return

	_original_import_fixtures = fixtures_module.import_fixtures

	def import_fixtures(app):
		if app != APP_NAME:
			return _original_import_fixtures(app)

		fixtures_path = frappe.get_app_path(app, "fixtures")
		if not os.path.exists(fixtures_path):
			return

		for fname in sorted(os.listdir(fixtures_path)):
			if not fname.endswith(".json") or fname == CUSTOM_FIELD_FIXTURE_FILE:
				continue

			file_path = frappe.get_app_path(app, "fixtures", fname)
			try:
				import_doc(file_path)
			except (ImportError, frappe.DoesNotExistError) as e:
				print(f"Skipping fixture syncing from the file {fname}. Reason: {e}")

		import_pratap_custom_field_fixtures_skip_existing()

	fixtures_module.import_fixtures = import_fixtures
	fixtures_module._pratap_fixture_patched = True


def import_pratap_custom_field_fixtures_skip_existing():
	"""Import fixtures/custom_field.json; skip records that already exist."""
	path = frappe.get_app_path(APP_NAME, "fixtures", CUSTOM_FIELD_FIXTURE_FILE)
	if not os.path.exists(path):
		return

	with open(path) as fixture_file:
		records = json.load(fixture_file)

	if not isinstance(records, list):
		records = [records]

	created = 0
	skipped = 0

	frappe.flags.in_import = True
	try:
		for record in records:
			if _custom_field_exists(record):
				skipped += 1
				continue

			doc = frappe.get_doc(record)
			doc.flags.ignore_validate = True
			doc.flags.ignore_permissions = True
			doc.flags.ignore_mandatory = True
			doc.insert()
			created += 1
	finally:
		frappe.flags.in_import = False

	if created:
		frappe.db.commit()

	if created or skipped:
		print(
			f"Pratap Custom Field fixtures: {created} created, {skipped} skipped (already exist)"
		)


def _custom_field_exists(record):
	name = record.get("name")
	if name and frappe.db.exists("Custom Field", name):
		return True

	dt = record.get("dt")
	fieldname = record.get("fieldname")
	if dt and fieldname and frappe.db.exists("Custom Field", {"dt": dt, "fieldname": fieldname}):
		return True

	return False


def export_custom_field_on_save(doc, method=None):
	"""Auto-export pratap Custom Fields to fixtures/custom_field.json on save."""
	if frappe.flags.in_import or frappe.flags.in_install or frappe.flags.in_migrate:
		return

	if doc.doctype != "Custom Field":
		return

	if (doc.module or "").strip().lower() != PRATAP_MODULE:
		return

	if not frappe.conf.developer_mode:
		return

	try:
		export_pratap_custom_field_fixtures()
	except Exception:
		frappe.log_error(
			title="Pratap auto-export fixtures failed",
			message=frappe.get_traceback(),
		)


def export_pratap_custom_field_fixtures():
	"""Export Custom Field fixtures (same as bench export-fixtures for this app)."""
	if not frappe.conf.developer_mode:
		frappe.throw(_("Only allowed to export fixtures in developer mode"))

	export_json(
		"Custom Field",
		frappe.get_app_path(APP_NAME, "fixtures", CUSTOM_FIELD_FIXTURE_FILE),
		filters=[["module", "=", PRATAP_MODULE]],
		order_by="idx asc, creation asc",
	)
