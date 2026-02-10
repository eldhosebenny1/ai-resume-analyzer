import os
import json
from datetime import datetime, timedelta
from google import genai
from google.genai import types

# Uses GOOGLE_API_KEY from environment variable
client = genai.Client()

def verify_payment_screenshot(image_content: bytes, expected_receiver_upi: str, expected_amount: float):
    """
    Extracts payment details from a screenshot using Gemini and verifies them.
    """
    
    current_time = datetime.now()
    
    prompt = f"""
    Analyze this payment image (could be a standard screenshot or a "Shared Receipt" image from GPay/Paytm/PhonePe).
    Extract the following details in JSON format:
    - sender_upi: UPI ID or name of the person who paid
    - receiver_upi: UPI ID of the person who received the money (look for "bennyeldho2@okicici" or "bennyeldho2-1@oksbi")
    - amount: The numeric amount paid
    - transaction_date: The date of the transaction (Format: YYYY-MM-DD)
    - transaction_time: The time of the transaction (Format: HH:MM:SS, 24-hour. If time is missing but date is present, guess contextually or return null)
    - transaction_id: Transaction ID or Reference number
    - is_suspicious: Boolean (true if you see obvious signs of Photoshop: mismatched fonts, blurred text boxes, or irregular background artifacts)
    - suspicion_reason: String (why do you think it is fake?)
    
    Current System Time for Reference: {current_time.strftime('%Y-%m-%d %H:%M:%S')}
    
    STRICT RULES:
    1. If you cannot find a piece of information, return null for that field.
    2. Shared receipts (nicely formatted receipt cards) are VALID. Do not mark them as suspicious just because they don't look like a standard phone screen.
    3. Look closely for "Photoshopped" elements: mismatched fonts or blurred regions specifically around the amount/date.
    4. Return ONLY valid JSON.
    5. Be extremely precise with the amount and UPI IDs.
    """

    try:
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=[
                prompt,
                types.Part.from_bytes(data=image_content, mime_type="image/jpeg")
            ],
            config={
                "temperature": 0.0,
                "response_mime_type": "application/json"
            }
        )
        
        details = json.loads(response.text)
        print(f"Extracted details: {details}")
        
        # --- VERIFICATION LOGIC ---

        # 0. Check for Tampering/Suspicion
        if details.get("is_suspicious") is True:
            reason = details.get("suspicion_reason", "Unknown inconsistency detected.")
            return False, f"Screenshot looks suspicious: {reason}", details
        
        # 1. Check Amount
        extracted_amount = details.get("amount")
        if extracted_amount is None:
            return False, "Could not find amount in screenshot.", details
        
        # Convert to float for comparison
        try:
            if isinstance(extracted_amount, str):
                extracted_amount = float(extracted_amount.replace(",", "").replace("₹", "").strip())
        except:
            return False, f"Invalid amount format: {extracted_amount}", details
            
        if abs(float(extracted_amount) - float(expected_amount)) > 0.01:
            return False, f"Amount mismatch. Expected {expected_amount}, found {extracted_amount}.", details
            
        # 2. Check Receiver UPI
        extracted_receiver = details.get("receiver_upi")
        if not extracted_receiver:
            # Some screenshots show the name instead of ID
            pass
        else:
            # Check if any of the expected receivers or common name parts are in the extracted text
            expected_receivers = ["bennyeldho2@okicici", "bennyeldho2-1@oksbi"]
            expected_parts = ["benny", "eldho", "okicici", "oksbi"]
            
            found_match = any(rec.lower() in extracted_receiver.lower() for rec in expected_receivers) or \
                          any(part in extracted_receiver.lower() for part in expected_parts)
            
            if not found_match:
                return False, f"Receiver mismatch. Found {extracted_receiver}.", details

        # 3. Check Date and Time
        extracted_date = details.get("transaction_date") # YYYY-MM-DD
        extracted_time = details.get("transaction_time") # HH:MM:SS
        
        if not extracted_date:
            return False, "Could not find transaction date in the image.", details
            
        server_now = datetime.now()
        today_date = server_now.strftime("%Y-%m-%d")

        # If we have both date and time, we check the window
        if extracted_date and extracted_time:
            try:
                txn_dt_str = f"{extracted_date} {extracted_time}"
                txn_dt = datetime.strptime(txn_dt_str, "%Y-%m-%d %H:%M:%S")
                
                diff_seconds = (server_now - txn_dt).total_seconds()
                diff_minutes = abs(diff_seconds) / 60
                
                # Timezone adjustment (UTC vs IST)
                if 310 < diff_minutes < 350:
                     diff_minutes = abs(diff_minutes - 330)
                
                if diff_minutes > 20: 
                    return False, f"the screenshot is too old.", details
                    
            except Exception as e:
                print(f"Time parsing error: {e}")
                if extracted_date != today_date:
                    return False, f"the date in the screenshot does not match today's date.", details
        else:
            # If time is missing (common in some shared receipts), 
            # we just check if the date is today.
            if extracted_date != today_date:
                return False, f"the date in the screenshot does not match today's date.", details

        return True, "Payment verified successfully!", details

    except Exception as e:
        print(f"Error in verification: {e}")
        return False, f"Verification process failed: {str(e)}", None
