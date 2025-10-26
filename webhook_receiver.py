import os, hmac, hashlib, logging
from fastapi import FastAPI, Request, Header, HTTPException
from decimal import Decimal
from aiogram import Bot
import asyncio

app = FastAPI()
log = logging.getLogger("uvicorn")

# === Env ===
MORALIS_SECRET = os.getenv("MORALIS_SECRET", "")
USD_THRESHOLD = Decimal(os.getenv("USD_THRESHOLD", "100000"))
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

bot = Bot(token=TELEGRAM_BOT_TOKEN) if TELEGRAM_BOT_TOKEN else None

def verify_signature(body: bytes, signature: str | None) -> bool:
    # Если секрет не задан — пропускаем проверку (для первичной отладки)
    if not MORALIS_SECRET:
        return True
    if not signature:
        return False
    mac = hmac.new(MORALIS_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, signature)

@app.get("/")
async def root_ok():
    return {"status": "ok"}

@app.get("/health")
async def health_ok():
    return {"status": "healthy"}

@app.post("/webhook/moralis")
async def webhook(request: Request, x_signature: str | None = Header(None)):
    # 1) Проверка подписи
    body = await request.body()
    if not verify_signature(body, x_signature):
        # Возвращаем 403 (Moralis расценит как не-200). Для первичной отладки лучше оставить MORALIS_SECRET пустым.
        raise HTTPException(status_code=403, detail="Invalid signature")

    # 2) Парсим JSON от Moralis
    try:
        payload = await request.json()
    except Exception:
        # Если пришло не-JSON, вернём 200, чтобы Moralis не падал из-за формата
        return {"ok": True, "note": "non-json body"}

    events = payload.get("events") or [payload]
    alerts = []
    for ev in events:
        # Moralis часто присылает usdValue (string). Если нет — считаем 0
        try:
            usd_value = Decimal(str(ev.get("usdValue", "0")))
        except Exception:
            usd_value = Decimal(0)

        if usd_value >= USD_THRESHOLD:
            alerts.append({
                "chain": ev.get("chain", "unknown"),
                "tx": ev.get("txHash", ""),
                "from": ev.get("fromAddress", ""),
                "to": ev.get("toAddress", ""),
                "usd": float(usd_value)
            })

    # 3) Безопасно отправляем сообщения в Telegram (если токен/чат задан)
    if bot and TELEGRAM_CHAT_ID and alerts:
        for a in alerts:
            text = (
                f"<b>🐋 Whale Alert</b>\n"
                f"Chain: {a['chain']}\n"
                f"Tx: <code>{a['tx']}</code>\n"
                f"From: {a['from']}\n"
                f"To: {a['to']}\n"
                f"Value: ${a['usd']:,}"
            )
            try:
                await bot.send_message(TELEGRAM_CHAT_ID, text, parse_mode="HTML")
            except Exception as e:
                # Логируем, но НЕ роняем обработку — вернём 200 Moralis во что бы то ни стало
                log.error(f"Telegram send failed: {e}")

    # 4) Всегда возвращаем 200 ОК для Moralis
    return {"ok": True, "alerts": len(alerts)}
