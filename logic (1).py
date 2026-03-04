import google.generativeai as genai
import os
import json
import re

VOUCHERS = {
    "FUTURE2040": 30,
    "BANGLADESH_AI": 365,
    "TRIAL_BOSS": 7
}

def setup_gemini(api_key):
    if api_key:
        genai.configure(api_key=api_key)
        return True
    return False

def extract_customer_info(ai_response_text):
    data = {"name": "Unknown", "phone": "N/A", "address": "Not Found", "district": "N/A", "qty": 1, "intent": "Query"}
    try:
        phone_match = re.search(r'(01[3-9]\d{8})', ai_response_text)
        if phone_match:
            data["phone"] = phone_match.group(1)
        if "[EXTRACTED_DATA:" in ai_response_text:
            json_str = ai_response_text.split("[EXTRACTED_DATA:")[1].split("]")[0]
            extracted = json.loads(json_str)
            data.update(extracted)
    except Exception as e:
        print(f"Extraction Error: {e}")
    return data

def get_ai_response(user_text, tone, api_key, product_info="General", has_image=False):
    if not api_key:
        return "⚠️ Neural Net Key Missing!"
    try:
        setup_gemini(api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        image_note = "Note: The merchant has uploaded a product image." if has_image else ""
        system_instruction = f"""
        Identity: You are 'Global Manager AI v2.0', the world's most advanced Sales Agent for Bangladeshi businesses.
        Business Context: {product_info}
        {image_note}
        Current Mode: {tone}

        Core Directive:
        1. Sales Psychology: Upsell always. If they want 1, convince them to buy 2.
        2. Personality: Extremely polite. Use স্যার/ম্যাম/ভাই/আপু. Never get angry.
        3. Language: Always respond in standard polite Bengali.
        4. Data Gathering: Collect Name, Full Address, Phone before confirming order.
        5. Be concise — max 3-4 sentences for voice clarity.

        Output Format:
        Answer naturally. Then add:
        [EXTRACTED_DATA: {{"name": "...", "phone": "...", "address": "...", "district": "...", "qty": 1, "intent": "Order/Query/Fake"}}]
        """
        full_prompt = f"{system_instruction}\n\nCustomer says: {user_text}"
        response = model.generate_content(full_prompt)
        return response.text
    except Exception as e:
        return f"System Error: {str(e)}"

def analyze_fake_order(user_text, ai_response_text):
    score = 50
    text = user_text.lower()
    if re.search(r'(01[3-9]\d{8})', text): score += 25
    if len(text) > 15: score += 10
    real_words = ['বিকাশ', 'পেমেন্ট', 'কনফার্ম', 'অর্ডার', 'ঠিকানা', 'পাঠিয়ে দেন', 'ক্যাশ অন', 'দাম কত', 'নিব']
    for word in real_words:
        if word in text: score += 10
    fake_words = ['পরে জানাবো', 'দাম বেশি', 'ফালতু', 'ভুয়া', 'খালি দাম কত', 'এখন না', 'রং নম্বর']
    for word in fake_words:
        if word in text: score -= 20
    score = max(0, min(100, score))
    if score >= 80: return f"VERIFIED_REAL ({score}%)", "🟩"
    elif score >= 50: return f"POTENTIAL_ORDER ({score}%)", "🟨"
    else: return f"FAKE_ALERT ({score}%)", "🟥"
