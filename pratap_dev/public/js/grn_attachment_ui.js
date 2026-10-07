// Polish the custom_grn_attachment (Attach) control on the GRN and Purchase Invoice:
// render "Reload File" / "Clear" as proper, single-line buttons sitting next to the file
// name instead of wrapping onto multiple lines.

frappe.ui.form.on("Purchase Receipt", { refresh: ensure_grn_attachment_style });
frappe.ui.form.on("Purchase Invoice", { refresh: ensure_grn_attachment_style });

function ensure_grn_attachment_style() {
	if (document.getElementById("grn-attachment-style")) {
		return;
	}
	const style = document.createElement("style");
	style.id = "grn-attachment-style";
	style.textContent = `
		[data-fieldname="custom_grn_attachment"] .attached-file {
			flex-wrap: nowrap;
			gap: 8px;
			align-items: center;
		}
		[data-fieldname="custom_grn_attachment"] .attached-file .ellipsis {
			min-width: 0;
		}
		/* the actions wrapper (Reload File / Clear) -> inline, never wrap */
		[data-fieldname="custom_grn_attachment"] .attached-file > div:last-child {
			display: inline-flex;
			gap: 6px;
			flex-shrink: 0;
			white-space: nowrap;
		}
		[data-fieldname="custom_grn_attachment"] .attached-file .btn {
			white-space: nowrap;
			border: 1px solid var(--border-color, #d1d8dd);
			background: var(--fg-color, #fff);
			padding: 2px 10px;
			border-radius: 6px;
			line-height: 1.4;
		}
		[data-fieldname="custom_grn_attachment"] .attached-file .btn:hover {
			background: var(--gray-100, #f4f5f6);
		}
	`;
	document.head.appendChild(style);
}
