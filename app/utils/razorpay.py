import hmac
import hashlib
import razorpay
from app.core.config import settings

# Initialize razorpay client
client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

def create_razorpay_order(amount: float, booking_id: str) -> dict:
    """
    Creates a Razorpay Order for a specific booking.
    Amount must be converted to paise (amount * 100)
    """
    options = {
        "amount": int(round(amount * 100)), # Convert to paise
        "currency": "INR",
        "receipt": f"b_{booking_id[:8]}", # Unique receipt (Must be < 40 chars)
        "notes": {
            "bookingId": booking_id
        }
    }
    try:
        order = client.order.create(data=options)
        return order
    except Exception as e:
        print(f"[Razorpay] Order Creation Failed: {e}")
        raise ValueError("RAZORPAY_ORDER_FAILED")

def verify_razorpay_signature(order_id: str, payment_id: str, signature: str) -> bool:
    """
    Verifies the payment signature sent by the mobile app.
    """
    try:
        # Standard Razorpay Signature Verification
        params = {
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature
        }
        client.utility.verify_payment_signature(params)
        return True
    except Exception as e:
        print(f"[Razorpay] Signature Verification Failed: {e}")
        
        # Manual fallback verify
        msg = f"{order_id}|{payment_id}".encode('utf-8')
        secret = settings.RAZORPAY_KEY_SECRET.encode('utf-8')
        expected = hmac.new(secret, msg, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

def verify_webhook_signature(raw_body: str, signature: str) -> bool:
    """
    Verifies signature of incoming Razorpay Webhooks.
    """
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        print("[Razorpay] Webhook secret missing. Skipping verification (Insecure!)")
        return True
        
    try:
        secret = settings.RAZORPAY_WEBHOOK_SECRET.encode('utf-8')
        msg = raw_body.encode('utf-8')
        expected = hmac.new(secret, msg, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)
    except Exception as e:
        print(f"[Razorpay] Webhook signature verification error: {e}")
        return False
