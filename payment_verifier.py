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
    Analyze this payment screenshot (Google Pay, Paytm, PhonePe, etc.) and extract the following details in JSON format:
    - sender_upi: UPI ID or name of the person who paid
    - receiver_upi: UPI ID of the person who received the money
    - amount: The numeric amount paid
    - transaction_date: The date of the transaction (Format: YYYY-MM-DD)
    - transaction_time: The time of the transaction (Format: HH:MM:SS, 24-hour)
    - transaction_id: Transaction ID or Reference number
    - is_suspicious: Boolean (true if you see signs of editing, font mismatches, or UI inconsistencies)
    - suspicion_reason: String (why do you think it is fake?)
    
    Current System Time for Reference: {current_time.strftime('%Y-%m-%d %H:%M:%S')}
    
    STRICT RULES:
    1. If you cannot find a piece of information, return null for that field.
    2. Look closely for "Photoshopped" elements: mismatched fonts, blurred regions around text, or irregular colors.
    3. Return ONLY valid JSON.
    4. Be extremely precise with the amount and UPI IDs.
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
        
        if not extracted_date or not extracted_time:
            return False, "Could not find date or time in screenshot.", details
            
        try:
            txn_dt_str = f"{extracted_date} {extracted_time}"
            txn_dt = datetime.strptime(txn_dt_str, "%Y-%m-%d %H:%M:%S")
            
            # Calculate diff in minutes
            # We assume the screenshot time is in the same timezone as the user (IST usually)
            # For simplicity, if the date matches today and time is within 20 mins, we allow it.
            # This accounts for server time vs user time differences up to 5.5 hours if server is UTC.
            
            server_now = datetime.now()
            
            # diff_seconds is (Server Time - Transaction Time)
            # Since Render is UTC and Txn is IST, Server is 5.5h BEHIND.
            # So diff_seconds will be around -19800 (-330 mins).
            diff_seconds = (server_now - txn_dt).total_seconds()
            diff_minutes = abs(diff_seconds) / 60
            
            # If the gap is around 5.5 hours (330 mins), it's likely a UTC vs IST mismatch.
            # We check if the gap is between 310 and 350 minutes.
            if 310 < diff_minutes < 350:
                 diff_minutes = abs(diff_minutes - 330) # Adjust for the 5.5h offset
            
            if diff_minutes > 20: # Giving 20 mins buffer
                return False, f"Transaction time is too old. Found {extracted_time}, Gap: {diff_minutes:.1f} mins.", details
                
        except Exception as e:
            print(f"Time parsing error: {e}")
            # Date fallback
            today_date = server_now.strftime("%Y-%m-%d")
            if extracted_date != today_date:
                return False, f"Date mismatch. Today is {today_date}, found {extracted_date}.", details

        return True, "Payment verified successfully!", details

    except Exception as e:
        print(f"Error in verification: {e}")
        return False, f"Verification process failed: {str(e)}", None
