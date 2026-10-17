# Copyright (c) 2026, pratap_dev contributors
# License: MIT

# Consumed Maintenance Items -> Material Issue Stock Entry, for every submittable document in
# SOURCES (Asset Maintenance Log — via hooks; Pratap Downtime Entry — from its controller).
#   * validate: default the Source Warehouse from Pratap Asset Settings, only allowed Item
#     Groups, refresh each row's Available Qty;
#   * before_submit (validate_ready): Source Warehouse required (not a group, right company)
#     and, per settings, the consumed qty may not be more than the available stock;
#   * on_submit (on_ready_create_stock_entry): in Auto mode the Stock Entry (Pratap Asset
#     Settings > Stock Entry Type, default "Material Issue Maintenance") is created —
#     submitted or as a draft. Otherwise (or after that Stock Entry is cancelled) the
#     submitted document shows a Create Stock Entry button.
# Each Stock Entry item row links back to its source and consumed row (item-level fields in
# SOURCES); when the Stock Entry is submitted (or cancelled) every linked source's Stock
# Entry field is set (or cleared).

import frappe
from frappe import _
from frappe.utils import cint, flt, get_link_to_form

SETTINGS = "Pratap Asset Settings"


def _log_company(doc):
	return frappe.db.get_value("Asset Maintenance", doc.get("asset_maintenance"), "company")


# Per source doctype: its own field names, the Stock Entry Detail back-references, the
# company the warehouse must belong to, and the text for the Stock Entry remarks.
SOURCES = {
	"Asset Maintenance Log": frappe._dict(
		items_field="custom_consumed_items",
		warehouse_field="custom_source_warehouse",
		stock_entry_field="custom_stock_entry",
		link_field="custom_asset_maintenance_log",
		link_item_field="custom_asset_maintenance_log_item",
		company=_log_company,
		describe=lambda doc: doc.get("item_name") or doc.get("asset_name"),
	),
	"Pratap Downtime Entry": frappe._dict(
		items_field="consumed_items",
		warehouse_field="source_warehouse",
		stock_entry_field="stock_entry",
		link_field="custom_pratap_downtime_entry",
		link_item_field="custom_pratap_downtime_entry_item",
		company=lambda doc: doc.get("company"),
		describe=lambda doc: doc.get("asset_name") or doc.get("workstation"),
	),
}


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


# ---------------------------------------------------------------- source document events


def validate_consumed_items(doc, method=None):
	"""validate: default Source Warehouse, allowed Item Groups, Available Qty."""
	if doc.docstatus != 0:
		return
	cfg = SOURCES[doc.doctype]
	# Default Source Warehouse on every draft (also logs ERPNext creates, which have no items yet).
	if not doc.get(cfg.warehouse_field):
		doc.set(cfg.warehouse_field, get_settings().default_source_warehouse)
	items = doc.get(cfg.items_field)
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
	warehouse = doc.get(cfg.warehouse_field)
	for row in items:
		row.available_qty = _actual_qty(row.item_code, warehouse) if warehouse else 0


def validate_ready(doc, method=None):
	"""before_submit: Source Warehouse required, not a group, right company, enough stock."""
	cfg = SOURCES[doc.doctype]
	items = doc.get(cfg.items_field)
	if not items:
		return
	warehouse = doc.get(cfg.warehouse_field)
	if not warehouse:
		frappe.throw(
			_("Please select the Source Warehouse for the Consumed Maintenance Items before submitting."),
			title=_("Source Warehouse Required"),
		)
	warehouse_company, is_group = frappe.db.get_value("Warehouse", warehouse, ["company", "is_group"])
	if cint(is_group):
		frappe.throw(_("Source Warehouse {0} is a group warehouse; select a stock warehouse.").format(frappe.bold(warehouse)))
	company = cfg.company(doc)
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

	precision = cint(frappe.db.get_default("float_precision")) or 3
	needed = {}
	for row in items:
		needed[row.item_code] = needed.get(row.item_code, 0) + flt(row.qty)
	short = []
	for item_code, qty in needed.items():
		available = _actual_qty(item_code, warehouse)
		if flt(qty, precision) > flt(available, precision):
			short.append(
				_("{0}: needed {1}, available {2}").format(
					frappe.bold(item_code), flt(qty, precision), flt(available, precision)
				)
			)
	if short:
		frappe.throw(
			_("Not enough stock in {0}:").format(frappe.bold(warehouse)) + "<br>" + "<br>".join(short),
			title=_("Insufficient Stock"),
		)


def on_ready_create_stock_entry(doc, method=None):
	"""on_submit: create the Stock Entry in Auto mode."""
	cfg = SOURCES[doc.doctype]
	if not doc.get(cfg.items_field):
		return
	settings = get_settings()
	if settings.stock_entry_creation != "Auto" or _open_stock_entry(doc.doctype, doc.name):
		return
	# System action on the source's submit: the user need not hold Stock Entry rights.
	se = _build_stock_entry(doc, settings)
	se.flags.ignore_permissions = True
	se.insert()
	if settings.submit_auto_stock_entry:
		se.submit()
		# Keep the in-memory document (returned to the form) in step with the db link.
		doc.set(cfg.stock_entry_field, se.name)
	frappe.msgprint(
		_("Stock Entry {0} created for the consumed items.").format(get_link_to_form("Stock Entry", se.name)),
		alert=True,
		indicator="green",
	)


# ---------------------------------------------------------------- whitelisted (forms)


@frappe.whitelist()
def get_stock_entry_state(doctype, name):
	"""What the form needs for its button: settings mode + any open Stock Entry."""
	_check_source(doctype)
	frappe.has_permission(doctype, "read", name, throw=True)
	return {
		"mode": get_settings().stock_entry_creation,
		"stock_entry": _open_stock_entry(doctype, name),
	}


@frappe.whitelist()
def make_stock_entry(doctype, name):
	"""Create a draft Stock Entry for a submitted source and return its name."""
	cfg = _check_source(doctype)
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	if doc.docstatus != 1:
		frappe.throw(_("Submit {0} {1} before creating its Stock Entry.").format(_(doctype), name))
	if not doc.get(cfg.items_field):
		frappe.throw(_("There are no Consumed Maintenance Items on {0}.").format(name))
	# Serialise concurrent clicks/users on the same source before the "already exists" check.
	frappe.db.get_value(doctype, name, "name", for_update=True)
	existing = _open_stock_entry(doctype, name)
	if existing:
		frappe.throw(
			_("Stock Entry {0} already exists for {1}.").format(get_link_to_form("Stock Entry", existing), name)
		)
	se = _build_stock_entry(doc, get_settings())
	se.insert()
	return se.name


@frappe.whitelist()
def get_consumed_item_settings(doctype):
	"""For the forms: allowed Item Groups (with sub-groups; [] = every stock item) and the
	default Source Warehouse — read here so users without access to the settings get them."""
	_check_source(doctype)
	frappe.has_permission(doctype, "read", throw=True)
	return {
		"item_groups": get_allowed_item_groups(),
		"default_source_warehouse": get_settings().default_source_warehouse,
	}


@frappe.whitelist()
def get_available_qty(doctype, warehouse, items):
	"""Available stock per item code in `warehouse` (for the Available Qty column)."""
	_check_source(doctype)
	frappe.has_permission(doctype, "read", throw=True)
	items = frappe.parse_json(items) or []
	return {item: _actual_qty(item, warehouse) for item in set(items) if item}


# ---------------------------------------------------------------- Stock Entry


def stock_entry_on_submit(doc, method=None):
	"""Stock Entry on_submit: record it on the source document(s) of its items."""
	for doctype, name in _linked_sources(doc):
		# update_modified=False: an open source form must still save without a timestamp clash.
		frappe.db.set_value(doctype, name, SOURCES[doctype].stock_entry_field, doc.name, update_modified=False)


def stock_entry_on_cancel(doc, method=None):
	"""Stock Entry on_cancel: clear it from the source document(s) of its items."""
	for doctype, name in _linked_sources(doc):
		field = SOURCES[doctype].stock_entry_field
		if frappe.db.get_value(doctype, name, field) == doc.name:
			frappe.db.set_value(doctype, name, field, None, update_modified=False)


def _linked_sources(stock_entry):
	return {
		(doctype, row.get(cfg.link_field))
		for row in stock_entry.get("items")
		for doctype, cfg in SOURCES.items()
		if row.get(cfg.link_field)
	}


# ---------------------------------------------------------------- helpers


def _check_source(doctype):
	if doctype not in SOURCES:
		frappe.throw(_("Consumed items are not supported for {0}.").format(doctype))
	return SOURCES[doctype]


def _build_stock_entry(source, settings):
	cfg = SOURCES[source.doctype]
	warehouse = source.get(cfg.warehouse_field)
	purpose = frappe.db.get_value("Stock Entry Type", settings.stock_entry_type, "purpose")
	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = settings.stock_entry_type
	se.purpose = purpose or "Material Issue"
	se.company = cfg.company(source) or frappe.db.get_value("Warehouse", warehouse, "company")
	se.from_warehouse = warehouse
	se.remarks = _("Items consumed in {0} {1} ({2})").format(source.doctype, source.name, cfg.describe(source) or "")
	for row in source.get(cfg.items_field):
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
				cfg.link_field: source.name,
				cfg.link_item_field: row.name,
			},
		)
	return se


def _open_stock_entry(doctype, name):
	"""Draft or submitted Stock Entry already made for this source (cancelled ones ignored)."""
	if not name:
		return None
	rows = frappe.get_all(
		"Stock Entry Detail",
		filters={"parenttype": "Stock Entry", SOURCES[doctype].link_field: name, "docstatus": ("<", 2)},
		fields=["parent"],
		order_by="creation desc",
		limit=1,
	)
	return rows[0].parent if rows else None


def _actual_qty(item_code, warehouse):
	if not item_code or not warehouse:
		return 0
	return flt(frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty"))
