// pratap_dev override of ERPNext's RFQ supplier portal script.
// Adds Standard Pkg Qty + No of Unit inputs; Qty = pkg x units (read-only).
// Standard Pkg Qty and No of Unit are mandatory before a quotation can be submitted.

window.doc={{ doc.as_json() }};

$(document).ready(function() {
	new rfq();
	doc.supplier = "{{ doc.supplier }}"
	doc.currency = "{{ doc.currency }}"
	doc.number_format = "{{ doc.number_format }}"
	doc.buying_price_list = "{{ doc.buying_price_list }}"
});

rfq = class rfq {
	constructor(){
		this.onfocus_select_all();
		this.change_pkg_units();
		this.change_rate();
		this.terms();
		this.submit_rfq();
		this.navigate_quotations();
	}

	onfocus_select_all(){
		$("input").click(function(){
			$(this).select();
		})
	}

	// Standard Pkg Qty / No of Unit drive Qty = pkg x units (Qty field is read-only).
	change_pkg_units(){
		var me = this;
		$('.rfq-items').on("change", ".rfq-pkg, .rfq-units", function(){
			me.idx = parseFloat($(this).attr('data-idx'));
			me.recalc_row();
		})
	}

	change_rate(){
		var me = this;
		$(".rfq-items").on("change", ".rfq-rate", function(){
			me.idx = parseFloat($(this).attr('data-idx'));
			me.rate = parseFloat(flt($(this).val())) || 0;
			me.recalc_row();
			$(this).val(format_number(me.rate, doc.number_format, 2));
		})
	}

	// Read this row's pkg / units / rate from the DOM, derive Qty, refresh amounts.
	recalc_row(){
		var me = this;
		var pkg = parseFloat(flt($(repl('.rfq-pkg[data-idx=%(idx)s]', {'idx': me.idx})).val())) || 0;
		var units = parseFloat(flt($(repl('.rfq-units[data-idx=%(idx)s]', {'idx': me.idx})).val())) || 0;
		me.pkg = pkg;
		me.units = units;
		me.qty = flt(pkg * units, 3);
		me.rate = parseFloat(flt($(repl('.rfq-rate[data-idx=%(idx)s]', {'idx': me.idx})).val())) || 0;
		me.update_qty_rate();
		$(repl('.rfq-qty[data-idx=%(idx)s]', {'idx': me.idx})).val(format_number(me.qty, doc.number_format, 2));
	}

	terms(){
		$(".terms").on("change", ".terms-feedback", function(){
			doc.terms = $(this).val();
		})
	}

	update_qty_rate(){
		var me = this;
		doc.grand_total = 0.0;
		$.each(doc.items, function(idx, data){
			if(data.idx == me.idx){
				data.qty = me.qty;
				data.rate = me.rate;
				data.custom_packing_qty = me.pkg;
				data.custom_total_qty = me.units;
				data.amount = (me.rate * me.qty) || 0.0;
				$(repl('.rfq-amount[data-idx=%(idx)s]',{'idx': me.idx})).text(format_number(data.amount, doc.number_format, 2));
			}

			doc.grand_total += flt(data.amount);
			$('.tax-grand-total').text(format_number(doc.grand_total, doc.number_format, 2));
		})
	}

	submit_rfq(){
		$('.btn-sm').click(function(){
			// Standard Pkg Qty and No of Unit are mandatory on every item.
			var invalid = [];
			$.each(doc.items, function(idx, data){
				if(!(flt(data.custom_packing_qty) > 0) || !(flt(data.custom_total_qty) > 0)){
					invalid.push(data.item_code);
				}
			});
			if(invalid.length){
				frappe.msgprint(__(
					"Please enter Standard Pkg Qty and No of Unit (both greater than 0) for: {0}",
					[invalid.join(", ")]
				));
				return;
			}

			frappe.freeze();
			frappe.call({
				type: "POST",
				method: "erpnext.buying.doctype.request_for_quotation.request_for_quotation.create_supplier_quotation",
				args: {
					doc: doc
				},
				btn: this,
				callback: function(r){
					frappe.unfreeze();
					if(r.message){
						$('.btn-sm').hide()
						window.location.href = "/supplier-quotations/" + encodeURIComponent(r.message);
					}
				}
			})
		})
	}

	navigate_quotations() {
		$('.quotations').click(function(){
			name = $(this).attr('idx')
			window.location.href = "/quotations/" + encodeURIComponent(name);
		})
	}
}
