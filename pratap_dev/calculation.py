# import frappe

# def po_calculation_by_weight(doc, method):

#     # 🔒 Run only when checkbox ON
#     if not doc.custom_calculate_based_on_weight:
#         return

#     total_doc_amount = 0

#     for item in doc.items:
#         try:
#             custom_rate = float(item.custom_rate_in_kg or 0)
#             weight_per_unit = float(item.custom_filling_capacity or 0)
#             qty = float(item.qty or 0)
#             normal_rate = float(item.rate or 0)
#         except Exception:
#             continue

#         # ==============================
#         # 🟢 CASE 1 → Custom rate entered
#         # ==============================
#         if custom_rate > 0:

#             if weight_per_unit > 0:
#                 final_rate = round(custom_rate * weight_per_unit, 2)
#             else:
#                 final_rate = round(custom_rate, 2)

#             final_amount = round(final_rate * qty, 2)

#             # 🔥 Update all fields
#             item.rate = final_rate
#             item.net_rate = final_rate
#             item.base_rate = final_rate
#             item.base_net_rate = final_rate

#             item.amount = final_amount
#             item.net_amount = final_amount
#             item.base_amount = final_amount
#             item.base_net_amount = final_amount
#             item.taxable_value = final_amount

#             total_doc_amount += final_amount

#         # ==============================
#         # 🟡 CASE 2 → Custom rate = 0
#         # 👉 Use normal ERPNext behaviour
#         # ==============================
#         else:
#             normal_amount = round(normal_rate * qty, 2)
#             total_doc_amount += normal_amount

#     # ✅ Update doc totals
#     doc.total = total_doc_amount
#     doc.net_total = total_doc_amount
#     doc.base_total = total_doc_amount
#     doc.base_net_total = total_doc_amount




import frappe

def po_calculation_by_weight(doc, method):

    total_doc_amount = 0

    for item in doc.items:
        try:
            custom_rate = float(item.custom_rate_in_kg or 0)
            weight_per_unit = float(item.custom_filling_capacity or 0)
            qty = float(item.qty or 0)
            normal_rate = float(item.rate or 0)
            apply_weight_calc = item.custom_calculate_based_on_weight or 0
        except Exception:
            continue

        # ============================================
        # 🟢 APPLY ONLY IF ITEM CHECKBOX IS ENABLED
        # ============================================
        if apply_weight_calc:

            # ==============================
            # CASE 1 → Custom rate entered
            # ==============================
            if custom_rate > 0:

                if weight_per_unit > 0:
                    final_rate = round(custom_rate * weight_per_unit, 2)
                else:
                    final_rate = round(custom_rate, 2)

                final_amount = round(final_rate * qty, 2)

                # 🔥 Update all rate fields
                item.rate = final_rate
                item.net_rate = final_rate
                item.base_rate = final_rate
                item.base_net_rate = final_rate
                item.amount = final_amount
                item.net_amount = final_amount
                item.base_amount = final_amount
                item.base_net_amount = final_amount
                item.taxable_value = final_amount

                total_doc_amount += final_amount

            # ==============================
            # CASE 2 → Checkbox ON but rate 0
            # ==============================
            else:
                normal_amount = round(normal_rate * qty, 2)
                total_doc_amount += normal_amount

        # ============================================
        # 🟡 CHECKBOX NOT ENABLED → NORMAL ERP RATE
        # ============================================
        else:
            normal_amount = round(normal_rate * qty, 2)
            total_doc_amount += normal_amount

    # ============================================
    # 🔵 UPDATE DOCUMENT TOTALS
    # ============================================
    doc.total = total_doc_amount
    doc.net_total = total_doc_amount
    doc.base_total = total_doc_amount
    doc.base_net_total = total_doc_amount


def enquiry_calculation_by_weight(doc, method):

    total_doc_amount = 0

    for item in doc.custom_opportunity_table:
        try:
            custom_rate = float(item.custom_rate_in_kg or 0)
            weight_per_unit = float(item.custom_filling_capacity or 0)
            qty = float(item.qty or 0)
            normal_rate = float(item.rate or 0)
            apply_weight_calc = item.custom_calculate_based_on_weight or 0
        except Exception:
            continue

        # ============================================
        # 🟢 APPLY ONLY IF ITEM CHECKBOX IS ENABLED
        # ============================================
        if apply_weight_calc:

            # ==============================
            # CASE 1 → Custom rate entered
            # ==============================
            if custom_rate > 0:

                if weight_per_unit > 0:
                    final_rate = round(custom_rate * weight_per_unit, 2)
                else:
                    final_rate = round(custom_rate, 2)

                final_amount = round(final_rate * qty, 2)

                # 🔥 Update all rate fields
                item.rate = final_rate
                item.net_rate = final_rate
                item.base_rate = final_rate
                item.base_net_rate = final_rate
                item.amount = final_amount
                item.net_amount = final_amount
                item.base_amount = final_amount
                item.base_net_amount = final_amount
                item.taxable_value = final_amount

                total_doc_amount += final_amount

            # ==============================
            # CASE 2 → Checkbox ON but rate 0
            # ==============================
            else:
                normal_amount = round(normal_rate * qty, 2)
                total_doc_amount += normal_amount

        # ============================================
        # 🟡 CHECKBOX NOT ENABLED → NORMAL ERP RATE
        # ============================================
        else:
            normal_amount = round(normal_rate * qty, 2)
            item.rate = normal_rate
            item.net_rate = normal_rate
            item.base_rate = normal_rate
            item.base_net_rate = normal_rate

            item.amount = normal_amount
            item.net_amount = normal_amount
            item.base_amount = normal_amount
            item.base_net_amount = normal_amount

            item.taxable_value = normal_amount
            total_doc_amount += normal_amount

    # ============================================
    # 🔵 UPDATE DOCUMENT TOTALS
    # ============================================
    doc.total = total_doc_amount
    doc.net_total = total_doc_amount
    doc.base_total = total_doc_amount
    doc.base_net_total = total_doc_amount


def product_table_calculation_by_weight(doc, method):

    total_doc_amount = 0

    for item in doc.sample_crm_item:
        try:
            custom_rate = float(item.custom_rate_in_kg or 0)
            weight_per_unit = float(item.custom_filling_capacity or 0)
            qty = float(item.qty or 0)
            normal_rate = float(item.rate or 0)
            apply_weight_calc = item.custom_calculate_based_on_weight or 0
        except Exception:
            continue

        # ============================================
        # 🟢 APPLY ONLY IF ITEM CHECKBOX IS ENABLED
        # ============================================
        if apply_weight_calc:

            # ==============================
            # CASE 1 → Custom rate entered
            # ==============================
            if custom_rate > 0:

                if weight_per_unit > 0:
                    final_rate = round(custom_rate * weight_per_unit, 2)
                else:
                    final_rate = round(custom_rate, 2)

                final_amount = round(final_rate * qty, 2)

                # 🔥 Update all rate fields
                item.rate = final_rate
                item.net_rate = final_rate
                item.base_rate = final_rate
                item.base_net_rate = final_rate
                item.amount = final_amount
                item.net_amount = final_amount
                item.base_amount = final_amount
                item.base_net_amount = final_amount
                item.taxable_value = final_amount

                total_doc_amount += final_amount

            # ==============================
            # CASE 2 → Checkbox ON but rate 0
            # ==============================
            else:
                normal_amount = round(normal_rate * qty, 2)
                total_doc_amount += normal_amount

        # ============================================
        # 🟡 CHECKBOX NOT ENABLED → NORMAL ERP RATE
        # ============================================
        else:
            normal_amount = round(normal_rate * qty, 2)
            item.rate = normal_rate
            item.net_rate = normal_rate
            item.base_rate = normal_rate
            item.base_net_rate = normal_rate

            item.amount = normal_amount
            item.net_amount = normal_amount
            item.base_amount = normal_amount
            item.base_net_amount = normal_amount

            item.taxable_value = normal_amount
            total_doc_amount += normal_amount

    # ============================================
    # 🔵 UPDATE DOCUMENT TOTALS
    # ============================================
    doc.total = total_doc_amount
    doc.net_total = total_doc_amount
    doc.base_total = total_doc_amount
    doc.base_net_total = total_doc_amount



def product_table_cal_by_weight(doc, method):

    total_doc_amount = 0

    for item in doc.proudct_trial_crm:
        try:
            custom_rate = float(item.custom_rate_in_kg or 0)
            weight_per_unit = float(item.custom_filling_capacity or 0)
            qty = float(item.qty or 0)
            normal_rate = float(item.rate or 0)
            apply_weight_calc = item.custom_calculate_based_on_weight or 0
        except Exception:
            continue

        # ============================================
        # 🟢 APPLY ONLY IF ITEM CHECKBOX IS ENABLED
        # ============================================
        if apply_weight_calc:

            # ==============================
            # CASE 1 → Custom rate entered
            # ==============================
            if custom_rate > 0:

                if weight_per_unit > 0:
                    final_rate = round(custom_rate * weight_per_unit, 2)
                else:
                    final_rate = round(custom_rate, 2)

                final_amount = round(final_rate * qty, 2)

                # 🔥 Update all rate fields
                item.rate = final_rate
                item.net_rate = final_rate
                item.base_rate = final_rate
                item.base_net_rate = final_rate
                item.amount = final_amount
                item.net_amount = final_amount
                item.base_amount = final_amount
                item.base_net_amount = final_amount
                item.taxable_value = final_amount

                total_doc_amount += final_amount

            # ==============================
            # CASE 2 → Checkbox ON but rate 0
            # ==============================
            else:
                normal_amount = round(normal_rate * qty, 2)
                total_doc_amount += normal_amount

        # ============================================
        # 🟡 CHECKBOX NOT ENABLED → NORMAL ERP RATE
        # ============================================
        else:
            normal_amount = round(normal_rate * qty, 2)
            item.rate = normal_rate
            item.net_rate = normal_rate
            item.base_rate = normal_rate
            item.base_net_rate = normal_rate

            item.amount = normal_amount
            item.net_amount = normal_amount
            item.base_amount = normal_amount
            item.base_net_amount = normal_amount

            item.taxable_value = normal_amount
            total_doc_amount += normal_amount

    # ============================================
    # 🔵 UPDATE DOCUMENT TOTALS
    # ============================================
    doc.total = total_doc_amount
    doc.net_total = total_doc_amount
    doc.base_total = total_doc_amount
    doc.base_net_total = total_doc_amount


def complain_table_cal_by_weight(doc, method):

    total_doc_amount = 0

    for item in doc.complaint_crm_item:
        try:
            custom_rate = float(item.custom_rate_in_kg or 0)
            weight_per_unit = float(item.custom_filling_capacity or 0)
            qty = float(item.qty or 0)
            normal_rate = float(item.rate or 0)
            apply_weight_calc = item.custom_calculate_based_on_weight or 0
        except Exception:
            continue

        # ============================================
        # 🟢 APPLY ONLY IF ITEM CHECKBOX IS ENABLED
        # ============================================
        if apply_weight_calc:

            # ==============================
            # CASE 1 → Custom rate entered
            # ==============================
            if custom_rate > 0:

                if weight_per_unit > 0:
                    final_rate = round(custom_rate * weight_per_unit, 2)
                else:
                    final_rate = round(custom_rate, 2)

                final_amount = round(final_rate * qty, 2)

                # 🔥 Update all rate fields
                item.rate = final_rate
                item.net_rate = final_rate
                item.base_rate = final_rate
                item.base_net_rate = final_rate
                item.amount = final_amount
                item.net_amount = final_amount
                item.base_amount = final_amount
                item.base_net_amount = final_amount
                item.taxable_value = final_amount

                total_doc_amount += final_amount

            # ==============================
            # CASE 2 → Checkbox ON but rate 0
            # ==============================
            else:
                normal_amount = round(normal_rate * qty, 2)
                total_doc_amount += normal_amount

        # ============================================
        # 🟡 CHECKBOX NOT ENABLED → NORMAL ERP RATE
        # ============================================
        else:
            normal_amount = round(normal_rate * qty, 2)
            item.rate = normal_rate
            item.net_rate = normal_rate
            item.base_rate = normal_rate
            item.base_net_rate = normal_rate

            item.amount = normal_amount
            item.net_amount = normal_amount
            item.base_amount = normal_amount
            item.base_net_amount = normal_amount

            item.taxable_value = normal_amount
            total_doc_amount += normal_amount

    # ============================================
    # 🔵 UPDATE DOCUMENT TOTALS
    # ============================================
    doc.total = total_doc_amount
    doc.net_total = total_doc_amount
    doc.base_total = total_doc_amount
    doc.base_net_total = total_doc_amount
    

def tsa_table_cal_by_weight(doc, method):

    total_doc_amount = 0

    for item in doc.product_table:
        try:
            custom_rate = float(item.custom_rate_in_kg or 0)
            weight_per_unit = float(item.custom_filling_capacity or 0)
            qty = float(item.qty or 0)
            normal_rate = float(item.rate or 0)
            apply_weight_calc = item.custom_calculate_based_on_weight or 0
        except Exception:
            continue

        # ============================================
        # 🟢 APPLY ONLY IF ITEM CHECKBOX IS ENABLED
        # ============================================
        if apply_weight_calc:

            # ==============================
            # CASE 1 → Custom rate entered
            # ==============================
            if custom_rate > 0:

                if weight_per_unit > 0:
                    final_rate = round(custom_rate * weight_per_unit, 2)
                else:
                    final_rate = round(custom_rate, 2)

                final_amount = round(final_rate * qty, 2)

                # 🔥 Update all rate fields
                item.rate = final_rate
                item.net_rate = final_rate
                item.base_rate = final_rate
                item.base_net_rate = final_rate
                item.amount = final_amount
                item.net_amount = final_amount
                item.base_amount = final_amount
                item.base_net_amount = final_amount
                item.taxable_value = final_amount

                total_doc_amount += final_amount

            # ==============================
            # CASE 2 → Checkbox ON but rate 0
            # ==============================
            else:
                normal_amount = round(normal_rate * qty, 2)
                total_doc_amount += normal_amount

        # ============================================
        # 🟡 CHECKBOX NOT ENABLED → NORMAL ERP RATE
        # ============================================
        else:
            normal_amount = round(normal_rate * qty, 2)
            item.rate = normal_rate
            item.net_rate = normal_rate
            item.base_rate = normal_rate
            item.base_net_rate = normal_rate

            item.amount = normal_amount
            item.net_amount = normal_amount
            item.base_amount = normal_amount
            item.base_net_amount = normal_amount

            item.taxable_value = normal_amount
            total_doc_amount += normal_amount

    # ============================================
    # 🔵 UPDATE DOCUMENT TOTALS
    # ============================================
    doc.total = total_doc_amount
    doc.net_total = total_doc_amount
    doc.base_total = total_doc_amount
    doc.base_net_total = total_doc_amount






