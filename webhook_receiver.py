import os, hmac, hashlib
from fastapi import FastAPI, Request, Header, HTTPException
import aiohttp
from decimal import Decimal

app = FastAPI()

MORALIS_SECRET = os.getenv("MORALIS_SECRET","")
USD_THRESHOLD = Decimal(os.getenv("USD_THRESHOLD","100000"))
TELEGRAM_URL = "http://telegram_bot:9001/send"

def verify_signature(body: bytes, signature: str|None):
    if not MORALIS_SECRET:
        return True
    if not signature:
        return False
    mac = hmac.new(MORALIS_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, signature)

@app.post("/webhook/moralis")
async def webhook(request: Request, x_signature: str|None = Header(None)):
    body = await request.body()
    if not verify_signature(body, x_signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    payload = await request.json()
    events = payload.get("events") or [payload]
    alerts = []
    for ev in events:
        usd_value = Decimal(ev.get("usdValue", "0"))
        if usd_value >= USD_THRESHOLD:
            alerts.append({
                "chain": ev.get("chain", "unknown"),
                "tx": ev.get("txHash", ""),
                "from": ev.get("fromAddress", ""),
                "to": ev.get("toAddress", ""),
                "usd": float(usd_value)
            })
    if alerts:
        async with aiohttp.ClientSession() as s:
            await s.post(TELEGRAM_URL, json={"alerts": alerts})
    return {"ok": True}
