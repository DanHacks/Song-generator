"""Billing: subscriptions with M-Pesa (Daraja STK Push), Stripe, and a mock provider for dev.

Providers activate automatically when their environment variables are present.
Without credentials, the mock provider lets the whole flow be tested locally.
"""

import base64
import datetime
import hashlib
import hmac
import json
import os
import urllib.parse
import urllib.request
import uuid

from .storage import DATA_DIR
from .config import TIERS

BILLING_DIR = os.path.join(DATA_DIR, "billing")
CHECKOUT_DIR = os.path.join(BILLING_DIR, "checkouts")
SUBSCRIPTION_MONTHS = 1

_MPESA_SANDBOX = "https://sandbox.safaricom.co.ke"
_MPESA_PRODUCTION = "https://api.safaricom.co.ke"
_STRIPE_API = "https://api.stripe.com"


def _ensure_dirs():
    os.makedirs(BILLING_DIR, exist_ok=True)
    os.makedirs(CHECKOUT_DIR, exist_ok=True)


def _sub_file(client_id):
    return os.path.join(BILLING_DIR, "%s.json" % _safe_cid(client_id))


def _safe_cid(client_id):
    return re_clean(client_id)


def re_clean(text):
    import re
    return re.sub(r"[^a-zA-Z0-9_-]", "_", text or "anonymous")


def get_subscription(client_id):
    """Return the subscription record for a client (defaults to free)."""
    _ensure_dirs()
    path = _sub_file(client_id)
    if os.path.exists(path):
        with open(path) as f:
            sub = json.load(f)
    else:
        sub = {"client_id": client_id, "tier": "free", "status": "active", "expires_at": None,
               "started_at": None, "source": None, "payments": []}
    return sub


def _write_subscription(sub):
    _ensure_dirs()
    with open(_sub_file(sub["client_id"]), "w") as f:
        json.dump(sub, f, indent=2, default=str)


def active_tier_name(client_id):
    """Name of the tier currently in effect for a client (free if expired)."""
    sub = get_subscription(client_id)
    if sub["tier"] != "free" and sub["status"] == "active" and sub.get("expires_at"):
        exp = _parse_dt(sub["expires_at"])
        if exp and exp > datetime.datetime.now(datetime.timezone.utc):
            return sub["tier"]
    return "free"


def _parse_dt(value):
    if isinstance(value, datetime.datetime):
        return value
    try:
        dt = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt
    except Exception:
        return None


def _apply(client_id, plan, source, reference, amount, months=SUBSCRIPTION_MONTHS):
    """Extend/activate a subscription and record the payment (idempotent by reference)."""
    sub = get_subscription(client_id)
    for p in sub.get("payments", []):
        if p.get("reference") == reference:
            return sub  # already applied
    now = datetime.datetime.now(datetime.timezone.utc)
    base = _parse_dt(sub.get("expires_at")) if sub.get("tier") == plan and sub.get("expires_at") else now
    if base is None or base < now:
        base = now
    new_exp = base + datetime.timedelta(days=30 * months)
    sub["tier"] = plan
    sub["status"] = "active"
    sub["started_at"] = sub.get("started_at") or now.isoformat()
    sub["expires_at"] = new_exp.isoformat()
    sub["source"] = source
    sub.setdefault("payments", []).append({
        "date": now.isoformat(),
        "plan": plan,
        "source": source,
        "reference": reference,
        "amount": amount,
    })
    _write_subscription(sub)
    return sub


def usage(client_id):
    from .config import generation_count
    tier = TIERS[active_tier_name(client_id)]
    max_gen = tier["max_generations"]
    used = generation_count(client_id) if max_gen is not None else 0
    return {"used": used, "max": max_gen, "remaining": None if max_gen is None else max(0, max_gen - used)}


def providers_status():
    return {
        "mock": True,
        "mpesa": bool(os.environ.get("MPESA_CONSUMER_KEY") and os.environ.get("MPESA_CONSUMER_SECRET") and os.environ.get("MPESA_PASSKEY") and os.environ.get("MPESA_SHORTCODE")),
        "stripe": bool(os.environ.get("STRIPE_SECRET_KEY")),
        "callback_base": os.environ.get("MPESA_CALLBACK_BASE"),
    }


def _now_msisdn(phone):
    digits = re_clean(phone.replace("+", "").replace(" ", "").strip())
    if digits.startswith("0"):
        digits = "254" + digits[1:]
    if not digits.startswith("254"):
        digits = "254" + digits
    return digits


# --------------------------------------------------------------------------- Mock

def mock_checkout(client_id, plan):
    _ensure_dirs()
    cid = uuid.uuid4().hex[:16]
    record = {
        "id": cid, "client_id": client_id, "plan": plan, "provider": "mock",
        "status": "pending", "amount": TIERS[plan].get("price_kes", 0),
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    with open(os.path.join(CHECKOUT_DIR, cid + ".json"), "w") as f:
        json.dump(record, f)
    return record


def mock_confirm(checkout_id):
    path = os.path.join(CHECKOUT_DIR, _safe_cid(checkout_id) + ".json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        record = json.load(f)
    if record["status"] == "pending":
        _apply(record["client_id"], record["plan"], "mock", "mock:" + record["id"], record["amount"])
        record["status"] = "paid"
        record["paid_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with open(path, "w") as f:
            json.dump(record, f, indent=2)
    return record


# ------------------------------------------------------------------------- M-Pesa

def _mpesa_base():
    return _MPESA_PRODUCTION if os.environ.get("MPESA_ENV", "sandbox").lower() == "production" else _MPESA_SANDBOX


def _mpesa_token():
    key = os.environ["MPESA_CONSUMER_KEY"]
    secret = os.environ["MPESA_CONSUMER_SECRET"]
    auth = base64.b64encode(("%s:%s" % (key, secret)).encode()).decode()
    url = "%s/oauth/v1/generate?grant_type=client_credentials" % _mpesa_base()
    req = urllib.request.Request(url, headers={"Authorization": "Basic %s" % auth})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
    return data["access_token"]


def initiate_mpesa(client_id, plan, phone):
    if not providers_status()["mpesa"]:
        raise ValueError("M-Pesa is not configured. Set MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET, MPESA_PASSKEY, MPESA_SHORTCODE.")
    amount = TIERS[plan]["price_kes"]
    shortcode = os.environ["MPESA_SHORTCODE"]
    passkey = os.environ["MPESA_PASSKEY"]
    callback_base = os.environ.get("MPESA_CALLBACK_BASE", "").rstrip("/")
    if not callback_base:
        raise ValueError("MPESA_CALLBACK_BASE is required (public HTTPS URL, e.g. https://sautigen.yourdomain.com).")
    msisdn = _now_msisdn(phone)
    if len(msisdn) != 12:
        raise ValueError("Invalid phone number. Use the Kenyan format, e.g. 0712345678.")
    ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    password = base64.b64encode(("%s%s%s" % (shortcode, passkey, ts)).encode()).decode()
    token = _mpesa_token()
    body = json.dumps({
        "BusinessShortCode": shortcode,
        "Password": password,
        "Timestamp": ts,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(amount),
        "PartyA": msisdn,
        "PartyB": shortcode,
        "PhoneNumber": msisdn,
        "CallBackURL": "%s/api/billing/mpesa/callback" % callback_base,
        "AccountReference": "SAUTIGEN:%s" % plan.upper(),
        "TransactionDesc": "SautiGen %s subscription" % TIERS[plan]["label"],
    }).encode()
    req = urllib.request.Request("%s/mpesa/stkpush/v1/processrequest" % _mpesa_base(),
                                 data=body, method="POST",
                                 headers={"Authorization": "Bearer %s" % token, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read().decode())
    return result


def handle_mpesa_callback(payload):
    """Parse the Daraja STK callback and upgrade the subscription on success."""
    try:
        cb = payload["Body"]["stkCallback"]
    except (KeyError, TypeError):
        return {"status": "ignored"}
    ref = str(cb.get("MerchantRequestID", ""))
    code = int(cb.get("ResultCode", -1))
    if code != 0:
        return {"status": "failed", "reference": ref, "result": cb.get("ResultDesc")}
    meta = {}
    for item in cb.get("CallbackMetadata", {}).get("Item", []):
        meta[item["Name"]] = item.get("Value")
    client_id = None
    plan = None
    refs = [x for x in (ref, str(meta.get("CheckoutRequestID", "")))]
    for cand in refs:
        sub, plan = _find_pending_mpesa(cand)
        if sub:
            client_id = sub["client_id"]
            break
    if not client_id:
        return {"status": "ignored", "reference": ref}
    amount = meta.get("Amount")
    _apply(client_id, plan, "mpesa", "mpesa:" + ref, amount)
    return {"status": "success", "client_id": client_id, "plan": plan, "amount": amount, "reference": ref}


def _find_pending_mpesa(ref):
    """Match a callback to a pending M-Pesa checkout (merchant + checkout request ids)."""
    if not os.path.isdir(CHECKOUT_DIR):
        return None, None
    for fn in os.listdir(CHECKOUT_DIR):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(CHECKOUT_DIR, fn)) as f:
            record = json.load(f)
        if record.get("provider") != "mpesa" or record.get("status") != "pending":
            continue
        if ref in (record.get("merchant_request_id"), record.get("checkout_request_id")):
            return record, record.get("plan")
    return None, None


# --------------------------------------------------------------------------- Stripe

def _stripe_headers():
    return {"Authorization": "Bearer %s" % os.environ["STRIPE_SECRET_KEY"],
            "Content-Type": "application/x-www-form-urlencoded"}


def create_stripe_checkout(client_id, plan):
    if not providers_status()["stripe"]:
        raise ValueError("Stripe is not configured. Set STRIPE_SECRET_KEY.")
    amount_usd = TIERS[plan]["price_usd"]
    data = urllib.parse.urlencode({
        "mode": "payment",
        "success_url": os.environ.get("APP_URL", "http://localhost:5173") + "/?payment=success",
        "cancel_url": os.environ.get("APP_URL", "http://localhost:5173") + "/?payment=cancelled",
        "client_reference_id": client_id,
        "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": "usd",
        "line_items[0][price_data][unit_amount]": str(int(amount_usd * 100)),
        "line_items[0][price_data][product_data][name]": "SautiGen %s (1 month)" % TIERS[plan]["label"],
        "metadata[client_id]": client_id,
        "metadata[plan]": plan,
    }).encode()
    req = urllib.request.Request("%s/v1/checkout/sessions" % _STRIPE_API, data=data, method="POST", headers=_stripe_headers())
    with urllib.request.urlopen(req, timeout=15) as resp:
        session = json.loads(resp.read().decode())
    return {"id": session["id"], "url": session["url"]}


def _verify_stripe_signature(payload, sig_header):
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
    if not secret:
        return None
    parts = dict(item.split("=", 1) for item in sig_header.split(","))
    timestamp, signature = parts.get("t"), parts.get("v1")
    if not timestamp or not signature:
        return None
    signed_payload = ("%s.%s" % (timestamp, payload.decode())).encode()
    expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return expected == signature


def handle_stripe_webhook(payload, sig_header):
    if not _verify_stripe_signature(payload, sig_header):
        return None
    event = json.loads(payload.decode())
    if event.get("type") == "checkout.session.completed":
        session = event.get("data", {}).get("object", {})
        client_id = (session.get("metadata") or {}).get("client_id")
        plan = (session.get("metadata") or {}).get("plan")
        if client_id and plan:
            _apply(client_id, plan, "stripe", "stripe:" + session.get("id"), TIERS[plan]["price_usd"])
            return {"status": "success", "client_id": client_id, "plan": plan}
    return {"status": "ignored"}
