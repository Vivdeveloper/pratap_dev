# Copyright (c) 2026, pratap_dev contributors
# License: MIT

# Asset Maintenance Log — Consumed Maintenance Items -> Material Issue Stock Entry.
#   * validate: default the Source Warehouse from Pratap Asset Settings and refresh each
#     row's Available Qty from the warehouse stock;
#   * before_submit: Source Warehouse is required when items are consumed, it must belong
#     to the Asset Maintenance's company, and (per settings) the consumed qty may not be
#     more than the available stock;
#   * on_submit: in "Auto" mode the Stock Entry (Pratap Asset Settings > Stock Entry Type,
#     default "Material Issue Maintenance") is created — submitted or left as a draft;
#     in "Manual" mode the log form shows a Create Stock Entry button instead.
# Each Stock Entry item row links back to its log (custom_asset_maintenance_log) and the
# consumed row (custom_asset_maintenance_log_item); when the Stock Entry is submitted (or
# cancelled) every linked log's custom_stock_entry is set (or cleared).

import frappe
from frappe import _
from frappe.utils import cint, flt, get_link_to_form

SETTINGS = "Pratap Asset Settings"
ITEMS_FIELD = "custom_consumed_items"
WAREHOUSE_FIELD = "custom_source_warehouse"
# Stock Entry Detail (item-level) back-references
LOG_LINK_FIELD = "custom_asset_maintenance_log"
LOG_ITEM_LINK_FIELD = "custom_asset_maintenance_log_item"


def get_settings():
	"""Pratap Asset Settings with the doctype defaults applied (also before it is ever saved)."""
	settings = frappe.get_cached_doc(SETTINGS)

	def check(value, default=1):
		return cint(default if value is None else value)

	return frappe._dict(
		stock_entry_creation=settings.stock_entry_creation or "Manual",
		submit_auto_stock_entry=check(settings.submit_auto_stock_entry),
		stock_entry_type=settings.stock_entry_type or "Material Issue Maintenance",
		default_source_warehouse=settings.default_source_warehouse,
		validate_available_stock=check(settings.validate_available_stock),
		consumed_item_groups=[row.item_group for row in settings.get("consumed_item_groups") or []],
	)


def get_allowed_item_groups():
	"""Settings > Allowed Item Groups expanded with their sub-groups; [] means no restriction."""
	allowed = set()
	for group in get_settings().consumed_item_groups:
		allowed.add(group)
		allowed.update(frappe.db.get_descendants("Item Group", group) or [])
	return sorted(allowed)


# ---------------------------------------------------------------- Asset Maintenance Log


def validate_consumed_items(doc, method=None):
	"""Asset Maintenance Log validate: allowed item groups, default warehouse, Available Qty."""
	if doc.docstatus != 0:
		return
	# Default Source Warehouse on every draft (also logs ERPNext creates, which have no items yet).
	if not doc.get(WAREHOUSE_FIELD):
		doc.set(WAREHOUSE_FIELD, get_settings().default_source_warehouse)
	items = doc.get(ITEMS_FIELD)
	if not items:
		return
	allowed = get_allowed_item_groups()
	for row in items:
		if not allowed:
			break
		item_group = frappe.get_cached_value("Item", row.item_code, "item_group")
		if item_group not in allowed:
			frappe.throw(
				_("Row #{0}: Item {1} is in Item Group {2}, which is not allowed for Consumed Maintenance Items (see {3}).").format(
					row.idx, frappe.bold(row.item_code), frappe.bold(item_group), SETTINGS
				),
				title=_("Item Not Allowed"),
			)
	warehouse = doc.get(WAREHOUSE_FIELD)
	for row in items:
		row.available_qty = _actual_qty(row.item_code, warehouse) if warehouse else 0


def before_submit_consumed_items(doc, method=None):
	"""Asset Maintenance Log before_submit: warehouse required, company match, enough stock."""
	items = doc.get(ITEMS_FIELD)
	if not items:
		return
	warehouse = doc.get(WAREHOUSE_FIELD)
	if not warehouse:
		frappe.throw(
			_("Please select the Source Warehouse for the Consumed Maintenance Items before submitting."),
			title=_("Source Warehouse Required"),
		)

	company = _log_company(doc)
	warehouse_company = frappe.db.get_value("Warehouse", warehouse, "company")
	if company and warehouse_company != company:
		frappe.throw(
			_("Source Warehouse {0} belongs to {1}, not to {2}.").format(
				frappe.bold(warehouse), warehouse_company, company
			)
		)

	if not get_settings().validate_available_stock or frappe.db.get_single_value(
		"Stock Settings", "allow_negative_stock"
	):
		return

	needed = {}
	for row in items:
		needed[row.item_code] = needed.get(row.item_code, 0) + flt(row.qty)
	short = []
	for item_code, qty in needed.items():
		available = _actual_qty(item_code, warehouse)
		if flt(qty) > flt(available):
			short.append(
				_("{0}: needed {1}, available {2}").format(frappe.bold(item_code), flt(qty), flt(available))
			)
	if short:
		frappe.throw(
			_("Not enough stock in {0}:").format(frappe.bold(warehouse)) + "<br>" + "<br>".join(short),
			title=_("Insufficient Stock"),
		)


def on_submit_consumed_items(doc, method=None):
	"""Asset Maintenance Log on_submit: create the Stock Entry in Auto mode."""
	if not doc.get(ITEMS_FIELD):
		return
	settings = get_settings()
	if settings.stock_entry_creation != "Auto":
		return
	# System action on the log's submit: the technician need not hold Stock Entry rights.
	se = _build_stock_entry(doc, settings)
	se.flags.ignore_permissions = True
	se.insert()
	if settings.submit_auto_stock_entry:
		se.submit()
	frappe.msgprint(
		_("Stock Entry {0} created for the consumed items.").format(get_link_to_form("Stock Entry", se.name)),
		alert=True,
		indicator="green",
	)


# ---------------------------------------------------------------- whitelisted (log form)


@frappe.whitelist()
def get_stock_entry_state(log):
	"""What the log form needs for its button: settings mode + any open Stock Entry."""
	frappe.has_permission("Asset Maintenance Log", "read", log, throw=True)
	return {
		"mode": get_settings().stock_entry_creation,
		"stock_entry": _open_stock_entry(log),
	}


@frappe.whitelist()
def make_stock_entry(log):
	"""Manual mode: create a draft Stock Entry for a submitted log and return its name."""
	doc = frappe.get_doc("Asset Maintenance Log", log)
	doc.check_permission("read")
	if doc.docstatus != 1:
		frappe.throw(_("Submit the Asset Maintenance Log before creating its Stock Entry."))
	if not doc.get(ITEMS_FIELD):
		frappe.throw(_("There are no Consumed Maintenance Items on {0}.").format(log))
	existing = _open_stock_entry(log)
	if existing:
		frappe.throw(
			_("Stock Entry {0} already exists for this log.").format(get_link_to_form("Stock Entry", existing))
		)
	se = _build_stock_entry(doc, get_settings())
	se.insert()
	return se.name


@frappe.whitelist()
def get_consumed_item_settings():
	"""For the log form: allowed Item Groups (with sub-groups; [] = every stock item) and the
	default Source Warehouse — read here so users without access to the settings get them."""
	frappe.has_permission("Asset Maintenance Log", "read", throw=True)
	return {
		"item_groups": get_allowed_item_groups(),
		"default_source_warehouse": get_settings().default_source_warehouse,
	}


@frappe.whitelist()
def get_available_qty(warehouse, items):
	"""Available stock per item code in `warehouse` (for the Available Qty column)."""
	frappe.has_permission("Asset Maintenance Log", "read", throw=True)
	items = frappe.parse_json(items) or []
	return {item: _actual_qty(item, warehouse) for item in set(items) if item}


# ---------------------------------------------------------------- Stock Entry


def stock_entry_on_submit(doc, method=None):
	"""Stock Entry on_submit: record it on the Asset Maintenance Log(s) of its items."""
	for log in _linked_logs(doc):
		frappe.db.set_value("Asset Maintenance Log", log, "custom_stock_entry", doc.name)


def stock_entry_on_cancel(doc, method=None):
	"""Stock Entry on_cancel: clear it from the Asset Maintenance Log(s) of its items."""
	for log in _linked_logs(doc):
		if frappe.db.get_value("Asset Maintenance Log", log, "custom_stock_entry") == doc.name:
			frappe.db.set_value("Asset Maintenance Log", log, "custom_stock_entry", None)


def _linked_logs(stock_entry):
	return {row.get(LOG_LINK_FIELD) for row in stock_entry.get("items") if row.get(LOG_LINK_FIELD)}


# ---------------------------------------------------------------- helpers


def _build_stock_entry(log, settings):
	warehouse = log.get(WAREHOUSE_FIELD)
	purpose = frappe.db.get_value("Stock Entry Type", settings.stock_entry_type, "purpose")
	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = settings.stock_entry_type
	se.purpose = purpose or "Material Issue"
	se.company = _log_company(log)
	se.from_warehouse = warehouse
	se.remarks = _("Items consumed in Asset Maintenance Log {0} ({1})").format(
		log.name, log.item_name or log.asset_name or ""
	)
	for row in log.get(ITEMS_FIELD):
		stock_uom = frappe.get_cached_value("Item", row.item_code, "stock_uom")
		se.append(
			"items",
			{
				"item_code": row.item_code,
				"qty": flt(row.qty),
				"transfer_qty": flt(row.qty),
				"uom": stock_uom,
				"stock_uom": stock_uom,
				"conversion_factor": 1,
				"s_warehouse": warehouse,
				LOG_LINK_FIELD: log.name,
				LOG_ITEM_LINK_FIELD: row.name,
			},
		)
	return se


def _open_stock_entry(log):
	"""Draft or submitted Stock Entry already made for this log (cancelled ones ignored)."""
	rows = frappe.get_all(
		"Stock Entry Detail",
		filters={"parenttype": "Stock Entry", LOG_LINK_FIELD: log, "docstatus": ("<", 2)},
		fields=["parent"],
		order_by="creation desc",
		limit=1,
	)
	return rows[0].parent if rows else None


def _log_company(log):
	return frappe.db.get_value("Asset Maintenance", log.asset_maintenance, "company")


def _actual_qty(item_code, warehouse):
	if not item_code or not warehouse:
		return 0
	return flt(frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty"))
