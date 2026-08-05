"""Freeze the original BOM item on each Work Order required item.

`custom_bom_item` records what the BOM originally called for. It is set once
(when empty) to the row's item_code, and is never overwritten afterwards — so
when an operator swaps `item_code` via "Alternate Item", `custom_bom_item`
still shows the original recipe item.

Forward-only: existing rows are populated the next time their Work Order is
saved; there is no historical backfill here (that would be a one-time patch).
"""


def set_bom_item(doc, method=None):
	for row in doc.get("required_items") or []:
		if not row.get("custom_bom_item"):
			# original_item is set by ERPNext when an alternate is chosen; prefer it
			# so a row already swapped still records the true BOM item, not the substitute.
			row.custom_bom_item = row.get("original_item") or row.item_code
