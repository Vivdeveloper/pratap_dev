# import frappe

# def po_calculation_by_weight(doc, method):

#     total_doc_amount = 0

#     for item in doc.items:
#         try:
#             custom_rate = float(item.custom_rate_in_kg or 0)
#             weight_per_unit = float(item.custom_filling_capacity or 0)
#             qty = float(item.qty or 0)
#             normal_rate = float(item.rate or 0)
#             apply_weight_calc = item.custom_calculate_based_on_weight or 0
#         except Exception:
#             continue

#         # ============================================
#         # 🟢 APPLY ONLY IF ITEM CHECKBOX IS ENABLED
#         # ============================================
#         if apply_weight_calc:

#             # ==============================
#             # CASE 1 → Custom rate entered
#             # ==============================
#             if custom_rate > 0:

#                 if weight_per_unit > 0:
#                     final_rate = round(custom_rate * weight_per_unit, 2)
#                 else:
#                     final_rate = round(custom_rate, 2)

#                 final_amount = round(final_rate * qty, 2)

#                 # 🔥 Update all rate fields
#                 item.rate = final_rate
#                 item.net_rate = final_rate
#                 item.base_rate = final_rate
#                 item.base_net_rate = final_rate
#                 item.amount = final_amount
#                 item.net_amount = final_amount
#                 item.base_amount = final_amount
#                 item.base_net_amount = final_amount
#                 item.taxable_value = final_amount

#                 total_doc_amount += final_amount

#             # ==============================
#             # CASE 2 → Checkbox ON but rate 0
#             # ==============================
#             else:
#                 normal_amount = round(normal_rate * qty, 2)
#                 total_doc_amount += normal_amount

#         # ============================================
#         # 🟡 CHECKBOX NOT ENABLED → NORMAL ERP RATE
#         # ============================================
#         else:
#             normal_amount = round(normal_rate * qty, 2)
#             total_doc_amount += normal_amount

#     # ============================================
#     # 🔵 UPDATE DOCUMENT TOTALS
#     # ============================================
#     doc.total = total_doc_amount
#     doc.net_total = total_doc_amount
#     doc.base_total = total_doc_amount
#     doc.base_net_total = total_doc_amount


# # def enquiry_calculation_by_weight(doc, method):

# #     total_doc_amount = 0

# #     for item in doc.custom_opportunity_table:
# #         try:
# #             custom_rate = float(item.custom_rate_in_kg or 0)
# #             weight_per_unit = float(item.custom_filling_capacity or 0)
# #             qty = float(item.qty or 0)
# #             normal_rate = float(item.rate or 0)
# #             apply_weight_calc = item.custom_calculate_based_on_weight or 0
# #         except Exception:
# #             continue

# #         # ============================================
# #         # 🟢 APPLY ONLY IF ITEM CHECKBOX IS ENABLED
# #         # ============================================
# #         if apply_weight_calc:

# #             # ==============================
# #             # CASE 1 → Custom rate entered
# #             # ==============================
# #             if custom_rate > 0:

# #                 if weight_per_unit > 0:
# #                     final_rate = round(custom_rate * weight_per_unit, 2)
# #                 else:
# #                     final_rate = round(custom_rate, 2)

# #                 final_amount = round(final_rate * qty, 2)

# #                 # 🔥 Update all rate fields
# #                 item.rate = final_rate
# #                 item.net_rate = final_rate
# #                 item.base_rate = final_rate
# #                 item.base_net_rate = final_rate
# #                 item.amount = final_amount
# #                 item.net_amount = final_amount
# #                 item.base_amount = final_amount
# #                 item.base_net_amount = final_amount
# #                 item.taxable_value = final_amount

# #                 total_doc_amount += final_amount

# #             # ==============================
# #             # CASE 2 → Checkbox ON but rate 0
# #             # ==============================
# #             else:
# #                 normal_amount = round(normal_rate * qty, 2)
# #                 total_doc_amount += normal_amount

# #         # ============================================
# #         # 🟡 CHECKBOX NOT ENABLED → NORMAL ERP RATE
# #         # ============================================
# #         else:
# #             normal_amount = round(normal_rate * qty, 2)
# #             item.rate = normal_rate
# #             item.net_rate = normal_rate
# #             item.base_rate = normal_rate
# #             item.base_net_rate = normal_rate

# #             item.amount = normal_amount
# #             item.net_amount = normal_amount
# #             item.base_amount = normal_amount
# #             item.base_net_amount = normal_amount

# #             item.taxable_value = normal_amount
# #             total_doc_amount += normal_amount

# #     # ============================================
# #     # 🔵 UPDATE DOCUMENT TOTALS
# #     # ============================================
# #     doc.total = total_doc_amount
# #     doc.net_total = total_doc_amount
# #     doc.base_total = total_doc_amount
# #     doc.base_net_total = total_doc_amount


# def enquiry_calculation_by_weight(doc, method):

#     total_doc_amount = 0

#     for item in doc.custom_opportunity_table:

#         try:
#             custom_rate = float(item.custom_rate_in_kg or 0)
#             weight_per_unit = float(item.custom_filling_capacity or 0)
#             qty = float(item.qty or 0)
#             normal_rate = float(item.rate or 0)
#             apply_weight_calc = item.custom_calculate_based_on_weight or 0
#         except Exception:
#             continue

#         # ============================================
#         # 🟢 CHECKBOX ENABLED
#         # ============================================
#         if apply_weight_calc:

#             # Snapshot list price: Frappe often defaults custom_previous_rate to 0 — treat 0 as "not set" when we still have a line rate
#             prev_list = float(item.custom_previous_rate or 0)
#             if normal_rate > 0 and prev_list == 0:
#                 item.custom_previous_rate = normal_rate

#             stored_kg = float(item.custom_previous_rate_in_kg or 0)
#             kg_for_calc = 0.0
#             if custom_rate > 0:
#                 # Item-price / client scripts often copy list rate into custom_rate_in_kg when re-checking weight calc.
#                 # Require kg field ~= list price AND far from stored kg so we do not steal real user edits.
#                 polluted_kg = (
#                     stored_kg > 0
#                     and abs(custom_rate - normal_rate) < 0.01
#                     and abs(custom_rate - stored_kg) > max(0.01, abs(stored_kg) * 2)
#                 )
#                 if polluted_kg:
#                     kg_for_calc = stored_kg
#                     item.custom_rate_in_kg = stored_kg
#                 else:
#                     kg_for_calc = custom_rate
#             else:
#                 kg_for_calc = stored_kg

#             if kg_for_calc > 0:
#                 item.custom_previous_rate_in_kg = kg_for_calc
#                 if weight_per_unit > 0:
#                     final_rate = round(kg_for_calc * weight_per_unit, 2)
#                 else:
#                     final_rate = round(kg_for_calc, 2)
#             else:
#                 final_rate = normal_rate

#             final_amount = round(final_rate * qty, 2)

#             # 🔥 Apply calculated rate
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

#         # ============================================
#         # 🟡 CHECKBOX DISABLED
#         # ============================================
#         else:

#             # ✅ RESTORE PREVIOUS NORMAL RATE
#             restored_rate = float(item.custom_previous_rate or normal_rate)

#             normal_amount = round(restored_rate * qty, 2)

#             item.rate = restored_rate
#             item.net_rate = restored_rate
#             item.base_rate = restored_rate
#             item.base_net_rate = restored_rate

#             item.amount = normal_amount
#             item.net_amount = normal_amount
#             item.base_amount = normal_amount
#             item.base_net_amount = normal_amount
#             item.taxable_value = normal_amount

#             total_doc_amount += normal_amount

#     # ============================================
#     # 🔵 UPDATE TOTALS
#     # ============================================
#     doc.total = total_doc_amount
#     doc.net_total = total_doc_amount
#     doc.base_total = total_doc_amount
#     doc.base_net_total = total_doc_amount


# def product_table_calculation_by_weight(doc, method):

#     total_doc_amount = 0

#     for item in doc.sample_crm_item:
#         try:
#             custom_rate = float(item.custom_rate_in_kg or 0)
#             weight_per_unit = float(item.custom_filling_capacity or 0)
#             qty = float(item.qty or 0)
#             normal_rate = float(item.rate or 0)
#             apply_weight_calc = item.custom_calculate_based_on_weight or 0
#         except Exception:
#             continue

#         # ============================================
#         # 🟢 APPLY ONLY IF ITEM CHECKBOX IS ENABLED
#         # ============================================
#         if apply_weight_calc:

#             # ==============================
#             # CASE 1 → Custom rate entered
#             # ==============================
#             if custom_rate > 0:

#                 if weight_per_unit > 0:
#                     final_rate = round(custom_rate * weight_per_unit, 2)
#                 else:
#                     final_rate = round(custom_rate, 2)

#                 final_amount = round(final_rate * qty, 2)

#                 # 🔥 Update all rate fields
#                 item.rate = final_rate
#                 item.net_rate = final_rate
#                 item.base_rate = final_rate
#                 item.base_net_rate = final_rate
#                 item.amount = final_amount
#                 item.net_amount = final_amount
#                 item.base_amount = final_amount
#                 item.base_net_amount = final_amount
#                 item.taxable_value = final_amount

#                 total_doc_amount += final_amount

#             # ==============================
#             # CASE 2 → Checkbox ON but rate 0
#             # ==============================
#             else:
#                 normal_amount = round(normal_rate * qty, 2)
#                 total_doc_amount += normal_amount

#         # ============================================
#         # 🟡 CHECKBOX NOT ENABLED → NORMAL ERP RATE
#         # ============================================
#         else:
#             normal_amount = round(normal_rate * qty, 2)
#             item.rate = normal_rate
#             item.net_rate = normal_rate
#             item.base_rate = normal_rate
#             item.base_net_rate = normal_rate

#             item.amount = normal_amount
#             item.net_amount = normal_amount
#             item.base_amount = normal_amount
#             item.base_net_amount = normal_amount

#             item.taxable_value = normal_amount
#             total_doc_amount += normal_amount

#     # ============================================
#     # 🔵 UPDATE DOCUMENT TOTALS
#     # ============================================
#     doc.total = total_doc_amount
#     doc.net_total = total_doc_amount
#     doc.base_total = total_doc_amount
#     doc.base_net_total = total_doc_amount



# def product_table_cal_by_weight(doc, method):

#     total_doc_amount = 0

#     for item in doc.proudct_trial_crm:
#         try:
#             custom_rate = float(item.custom_rate_in_kg or 0)
#             weight_per_unit = float(item.custom_filling_capacity or 0)
#             qty = float(item.qty or 0)
#             normal_rate = float(item.rate or 0)
#             apply_weight_calc = item.custom_calculate_based_on_weight or 0
#         except Exception:
#             continue

#         # ============================================
#         # 🟢 APPLY ONLY IF ITEM CHECKBOX IS ENABLED
#         # ============================================
#         if apply_weight_calc:

#             # ==============================
#             # CASE 1 → Custom rate entered
#             # ==============================
#             if custom_rate > 0:

#                 if weight_per_unit > 0:
#                     final_rate = round(custom_rate * weight_per_unit, 2)
#                 else:
#                     final_rate = round(custom_rate, 2)

#                 final_amount = round(final_rate * qty, 2)

#                 # 🔥 Update all rate fields
#                 item.rate = final_rate
#                 item.net_rate = final_rate
#                 item.base_rate = final_rate
#                 item.base_net_rate = final_rate
#                 item.amount = final_amount
#                 item.net_amount = final_amount
#                 item.base_amount = final_amount
#                 item.base_net_amount = final_amount
#                 item.taxable_value = final_amount

#                 total_doc_amount += final_amount

#             # ==============================
#             # CASE 2 → Checkbox ON but rate 0
#             # ==============================
#             else:
#                 normal_amount = round(normal_rate * qty, 2)
#                 total_doc_amount += normal_amount

#         # ============================================
#         # 🟡 CHECKBOX NOT ENABLED → NORMAL ERP RATE
#         # ============================================
#         else:
#             normal_amount = round(normal_rate * qty, 2)
#             item.rate = normal_rate
#             item.net_rate = normal_rate
#             item.base_rate = normal_rate
#             item.base_net_rate = normal_rate

#             item.amount = normal_amount
#             item.net_amount = normal_amount
#             item.base_amount = normal_amount
#             item.base_net_amount = normal_amount

#             item.taxable_value = normal_amount
#             total_doc_amount += normal_amount

#     # ============================================
#     # 🔵 UPDATE DOCUMENT TOTALS
#     # ============================================
#     doc.total = total_doc_amount
#     doc.net_total = total_doc_amount
#     doc.base_total = total_doc_amount
#     doc.base_net_total = total_doc_amount


# def complain_table_cal_by_weight(doc, method):

#     total_doc_amount = 0

#     for item in doc.complaint_crm_item:
#         try:
#             custom_rate = float(item.custom_rate_in_kg or 0)
#             weight_per_unit = float(item.custom_filling_capacity or 0)
#             qty = float(item.qty or 0)
#             normal_rate = float(item.rate or 0)
#             apply_weight_calc = item.custom_calculate_based_on_weight or 0
#         except Exception:
#             continue

#         # ============================================
#         # 🟢 APPLY ONLY IF ITEM CHECKBOX IS ENABLED
#         # ============================================
#         if apply_weight_calc:

#             # ==============================
#             # CASE 1 → Custom rate entered
#             # ==============================
#             if custom_rate > 0:

#                 if weight_per_unit > 0:
#                     final_rate = round(custom_rate * weight_per_unit, 2)
#                 else:
#                     final_rate = round(custom_rate, 2)

#                 final_amount = round(final_rate * qty, 2)

#                 # 🔥 Update all rate fields
#                 item.rate = final_rate
#                 item.net_rate = final_rate
#                 item.base_rate = final_rate
#                 item.base_net_rate = final_rate
#                 item.amount = final_amount
#                 item.net_amount = final_amount
#                 item.base_amount = final_amount
#                 item.base_net_amount = final_amount
#                 item.taxable_value = final_amount

#                 total_doc_amount += final_amount

#             # ==============================
#             # CASE 2 → Checkbox ON but rate 0
#             # ==============================
#             else:
#                 normal_amount = round(normal_rate * qty, 2)
#                 total_doc_amount += normal_amount

#         # ============================================
#         # 🟡 CHECKBOX NOT ENABLED → NORMAL ERP RATE
#         # ============================================
#         else:
#             normal_amount = round(normal_rate * qty, 2)
#             item.rate = normal_rate
#             item.net_rate = normal_rate
#             item.base_rate = normal_rate
#             item.base_net_rate = normal_rate

#             item.amount = normal_amount
#             item.net_amount = normal_amount
#             item.base_amount = normal_amount
#             item.base_net_amount = normal_amount

#             item.taxable_value = normal_amount
#             total_doc_amount += normal_amount

#     # ============================================
#     # 🔵 UPDATE DOCUMENT TOTALS
#     # ============================================
#     doc.total = total_doc_amount
#     doc.net_total = total_doc_amount
#     doc.base_total = total_doc_amount
#     doc.base_net_total = total_doc_amount
    

# def tsa_table_cal_by_weight(doc, method):

#     total_doc_amount = 0

#     for item in doc.product_table:
#         try:
#             custom_rate = float(item.custom_rate_in_kg or 0)
#             weight_per_unit = float(item.custom_filling_capacity or 0)
#             qty = float(item.qty or 0)
#             normal_rate = float(item.rate or 0)
#             apply_weight_calc = item.custom_calculate_based_on_weight or 0
#         except Exception:
#             continue

#         # ============================================
#         # 🟢 APPLY ONLY IF ITEM CHECKBOX IS ENABLED
#         # ============================================
#         if apply_weight_calc:

#             # ==============================
#             # CASE 1 → Custom rate entered
#             # ==============================
#             if custom_rate > 0:

#                 if weight_per_unit > 0:
#                     final_rate = round(custom_rate * weight_per_unit, 2)
#                 else:
#                     final_rate = round(custom_rate, 2)

#                 final_amount = round(final_rate * qty, 2)

#                 # 🔥 Update all rate fields
#                 item.rate = final_rate
#                 item.net_rate = final_rate
#                 item.base_rate = final_rate
#                 item.base_net_rate = final_rate
#                 item.amount = final_amount
#                 item.net_amount = final_amount
#                 item.base_amount = final_amount
#                 item.base_net_amount = final_amount
#                 item.taxable_value = final_amount

#                 total_doc_amount += final_amount

#             # ==============================
#             # CASE 2 → Checkbox ON but rate 0
#             # ==============================
#             else:
#                 normal_amount = round(normal_rate * qty, 2)
#                 total_doc_amount += normal_amount

#         # ============================================
#         # 🟡 CHECKBOX NOT ENABLED → NORMAL ERP RATE
#         # ============================================
#         else:
#             normal_amount = round(normal_rate * qty, 2)
#             item.rate = normal_rate
#             item.net_rate = normal_rate
#             item.base_rate = normal_rate
#             item.base_net_rate = normal_rate

#             item.amount = normal_amount
#             item.net_amount = normal_amount
#             item.base_amount = normal_amount
#             item.base_net_amount = normal_amount

#             item.taxable_value = normal_amount
#             total_doc_amount += normal_amount

#     # ============================================
#     # 🔵 UPDATE DOCUMENT TOTALS
#     # ============================================
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

            # Snapshot list rate once (treat 0 as "not set")
            prev_list = float(item.custom_custom_previous_rate or 0)
            if normal_rate > 0 and prev_list == 0:
                item.custom_custom_previous_rate = normal_rate

            stored_kg = float(item.custom_custom_previous_rate_in_kg or 0)

            if custom_rate > 0:
                # If UI copies list-rate into custom_rate_in_kg on re-check,
                # use stored kg for calculation.
                polluted_kg = (
                    stored_kg > 0
                    and abs(custom_rate - normal_rate) < 0.01
                    and abs(custom_rate - stored_kg) > max(0.01, abs(stored_kg) * 2)
                )
                if polluted_kg:
                    kg_for_calc = stored_kg
                    item.custom_rate_in_kg = stored_kg
                else:
                    kg_for_calc = custom_rate
            else:
                kg_for_calc = stored_kg

            if kg_for_calc > 0:
                item.custom_custom_previous_rate_in_kg = kg_for_calc
                if weight_per_unit > 0:
                    final_rate = round(kg_for_calc * weight_per_unit, 2)
                else:
                    final_rate = round(kg_for_calc, 2)
            else:
                final_rate = normal_rate

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

        # ============================================
        # 🟡 CHECKBOX NOT ENABLED → RESTORE PREVIOUS NORMAL RATE
        # ============================================
        else:
            restored_rate = float(item.custom_custom_previous_rate or 0)
            if not restored_rate:
                restored_rate = normal_rate

            normal_amount = round(restored_rate * qty, 2)

            item.rate = restored_rate
            item.net_rate = restored_rate
            item.base_rate = restored_rate
            item.base_net_rate = restored_rate

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
        # 🟢 CHECKBOX ENABLED
        # ============================================
        if apply_weight_calc:

            # Snapshot list price: Frappe often defaults custom_previous_rate to 0 — treat 0 as "not set" when we still have a line rate
            prev_list = float(item.custom_previous_rate or 0)
            if normal_rate > 0 and prev_list == 0:
                item.custom_previous_rate = normal_rate

            stored_kg = float(item.custom_previous_rate_in_kg or 0)
            kg_for_calc = 0.0
            if custom_rate > 0:
                # Item-price / client scripts often copy list rate into custom_rate_in_kg when re-checking weight calc.
                # Require kg field ~= list price AND far from stored kg so we do not steal real user edits.
                polluted_kg = (
                    stored_kg > 0
                    and abs(custom_rate - normal_rate) < 0.01
                    and abs(custom_rate - stored_kg) > max(0.01, abs(stored_kg) * 2)
                )
                if polluted_kg:
                    kg_for_calc = stored_kg
                    item.custom_rate_in_kg = stored_kg
                else:
                    kg_for_calc = custom_rate
            else:
                kg_for_calc = stored_kg

            if kg_for_calc > 0:
                item.custom_previous_rate_in_kg = kg_for_calc
                if weight_per_unit > 0:
                    final_rate = round(kg_for_calc * weight_per_unit, 2)
                else:
                    final_rate = round(kg_for_calc, 2)
            else:
                final_rate = normal_rate

            final_amount = round(final_rate * qty, 2)

            # 🔥 Apply calculated rate
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

        # ============================================
        # 🟡 CHECKBOX DISABLED
        # ============================================
        else:

            # ✅ RESTORE PREVIOUS NORMAL RATE
            restored_rate = float(item.custom_previous_rate or normal_rate)

            normal_amount = round(restored_rate * qty, 2)

            item.rate = restored_rate
            item.net_rate = restored_rate
            item.base_rate = restored_rate
            item.base_net_rate = restored_rate

            item.amount = normal_amount
            item.net_amount = normal_amount
            item.base_amount = normal_amount
            item.base_net_amount = normal_amount
            item.taxable_value = normal_amount

            total_doc_amount += normal_amount

    # ============================================
    # 🔵 UPDATE TOTALS
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

            prev_list = float(item.custom_previous_rate or 0)
            if normal_rate > 0 and prev_list == 0:
                item.custom_previous_rate = normal_rate

            stored_kg = float(item.custom_previous_rate_in_kg or 0)

            if custom_rate > 0:
                polluted_kg = (
                    stored_kg > 0
                    and abs(custom_rate - normal_rate) < 0.01
                    and abs(custom_rate - stored_kg) > max(0.01, abs(stored_kg) * 2)
                )
                if polluted_kg:
                    kg_for_calc = stored_kg
                    item.custom_rate_in_kg = stored_kg
                else:
                    kg_for_calc = custom_rate
            else:
                kg_for_calc = stored_kg

            if kg_for_calc > 0:
                item.custom_previous_rate_in_kg = kg_for_calc
                if weight_per_unit > 0:
                    final_rate = round(kg_for_calc * weight_per_unit, 2)
                else:
                    final_rate = round(kg_for_calc, 2)
            else:
                final_rate = normal_rate

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

        # ============================================
        # 🟡 CHECKBOX NOT ENABLED → NORMAL ERP RATE
        # ============================================
        else:
            restored_rate = float(item.custom_previous_rate or 0)
            if not restored_rate:
                restored_rate = normal_rate

            normal_amount = round(restored_rate * qty, 2)

            item.rate = restored_rate
            item.net_rate = restored_rate
            item.base_rate = restored_rate
            item.base_net_rate = restored_rate

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

            prev_list = float(item.custom_previous_rate or 0)
            if normal_rate > 0 and prev_list == 0:
                item.custom_previous_rate = normal_rate

            stored_kg = float(item.custom_previous_rate_in_kg or 0)

            if custom_rate > 0:
                polluted_kg = (
                    stored_kg > 0
                    and abs(custom_rate - normal_rate) < 0.01
                    and abs(custom_rate - stored_kg) > max(0.01, abs(stored_kg) * 2)
                )
                if polluted_kg:
                    kg_for_calc = stored_kg
                    item.custom_rate_in_kg = stored_kg
                else:
                    kg_for_calc = custom_rate
            else:
                kg_for_calc = stored_kg

            if kg_for_calc > 0:
                item.custom_previous_rate_in_kg = kg_for_calc
                if weight_per_unit > 0:
                    final_rate = round(kg_for_calc * weight_per_unit, 2)
                else:
                    final_rate = round(kg_for_calc, 2)
            else:
                final_rate = normal_rate

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

        # ============================================
        # 🟡 CHECKBOX NOT ENABLED → NORMAL ERP RATE
        # ============================================
        else:
            restored_rate = float(item.custom_previous_rate or 0)
            if not restored_rate:
                restored_rate = normal_rate

            normal_amount = round(restored_rate * qty, 2)

            item.rate = restored_rate
            item.net_rate = restored_rate
            item.base_rate = restored_rate
            item.base_net_rate = restored_rate

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

            prev_list = float(item.custom_previous_rate or 0)
            if normal_rate > 0 and prev_list == 0:
                item.custom_previous_rate = normal_rate

            stored_kg = float(item.custom_previous_rate_in_kg or 0)

            if custom_rate > 0:
                polluted_kg = (
                    stored_kg > 0
                    and abs(custom_rate - normal_rate) < 0.01
                    and abs(custom_rate - stored_kg) > max(0.01, abs(stored_kg) * 2)
                )
                if polluted_kg:
                    kg_for_calc = stored_kg
                    item.custom_rate_in_kg = stored_kg
                else:
                    kg_for_calc = custom_rate
            else:
                kg_for_calc = stored_kg

            if kg_for_calc > 0:
                item.custom_previous_rate_in_kg = kg_for_calc
                if weight_per_unit > 0:
                    final_rate = round(kg_for_calc * weight_per_unit, 2)
                else:
                    final_rate = round(kg_for_calc, 2)
            else:
                final_rate = normal_rate

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

        # ============================================
        # 🟡 CHECKBOX NOT ENABLED → NORMAL ERP RATE
        # ============================================
        else:
            restored_rate = float(item.custom_previous_rate or 0)
            if not restored_rate:
                restored_rate = normal_rate

            normal_amount = round(restored_rate * qty, 2)

            item.rate = restored_rate
            item.net_rate = restored_rate
            item.base_rate = restored_rate
            item.base_net_rate = restored_rate

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

            prev_list = float(item.custom_previous_rate or 0)
            if normal_rate > 0 and prev_list == 0:
                item.custom_previous_rate = normal_rate

            stored_kg = float(item.custom_previous_rate_in_kg or 0)

            if custom_rate > 0:
                polluted_kg = (
                    stored_kg > 0
                    and abs(custom_rate - normal_rate) < 0.01
                    and abs(custom_rate - stored_kg) > max(0.01, abs(stored_kg) * 2)
                )
                if polluted_kg:
                    kg_for_calc = stored_kg
                    item.custom_rate_in_kg = stored_kg
                else:
                    kg_for_calc = custom_rate
            else:
                kg_for_calc = stored_kg

            if kg_for_calc > 0:
                item.custom_previous_rate_in_kg = kg_for_calc
                if weight_per_unit > 0:
                    final_rate = round(kg_for_calc * weight_per_unit, 2)
                else:
                    final_rate = round(kg_for_calc, 2)
            else:
                final_rate = normal_rate

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

        # ============================================
        # 🟡 CHECKBOX NOT ENABLED → NORMAL ERP RATE
        # ============================================
        else:
            restored_rate = float(item.custom_previous_rate or 0)
            if not restored_rate:
                restored_rate = normal_rate

            normal_amount = round(restored_rate * qty, 2)

            item.rate = restored_rate
            item.net_rate = restored_rate
            item.base_rate = restored_rate
            item.base_net_rate = restored_rate

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
