import os, hmac, hashlib, logging, asyncio
from fastapi import FastAPI, Request, HTTPException
from decimal import Decimal
from aiogram import Bot

app = FastAPI()
log = logging.getLogger("uvicorn")

# === ENV ===
USD_THRESHOLD = Decimal(os.getenv("USD_THRESHOLD", "100000"))
MORALIS_SECRET = os.getenv("MORALIS_SECRET", "")  # сюда кладём Moralis API Key (новая модель)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

bot = Bot(token=TELEGRAM_BOT_TOKEN) if TELEGRAM_BOT_TOKEN else None

def is_authorized(headers) -> bool:
    # Новая модель Moralis: передаёт глобальный API Key в X-API-Key
    if not MORALIS_SECRET:
        return True  # на время отладки можно пропустить проверку
    api_key = headers.get("x-api-key") or headers.get("X-API-Key")
    if api_key and api_key == MORALIS_SECRET:
        return True
    # На всякий случай поддержим старый вариант:
    sig = headers.get("x-signature") or headers.get("X-Signature")
    if sig and sig == MORALIS_SECRET:
        return True
    return False

@app.get("/")
async def root_ok():
    return {"status": "ok"}

@app.get("/health")
async def health_ok():
    return {"status": "healthy"}

async def send_telegram(text: str):
    if not (bot and TELEGRAM_CHAT_ID):
        return
    try:
        await bot.send_message(TELEGRAM_CHAT_ID, text, parse_mode="HTML")
    except Exception as e:
        log.error(f"Telegram send failed: {e}")

@app.post("/webhook/moralis")
async def webhook(request: Request):
    # 1) Авторизация по ключу (моментальный отказ, если не прошли)
    if not is_authorized(request.headers):
        # Возвращаем 403, НО сначала убедитесь, что MORALIS_SECRET верный.
        raise HTTPException(status_code=403, detail="Unauthorized (check X-API-Key)")

    # 2) Парсинг тела
    try:
        payload = await request.json()
    except Exception:
        # Возвращаем 200, чтобы Moralis счёл доставку успешной (важно для тестов)
        return {"ok": True, "note": "non-json body"}

    events = payload.get("events") or [payload]
    alerts = []
    for ev in events:
        # Moralis пример поля: usdValue (строка). Если нет — считаем 0.
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
                "usd": float(usd_value),
            })

    # 3) Возвращаем 200 как можно раньше (НЕ ждём Telegram)
    #    Отправку в Telegram запускаем в фоне, чтобы не ловить таймауты Moralis.
    if alerts:
        msgs = []
        for a in alerts:
            msgs.append(
                (
                    f"<b>🐋 Whale Alert</b>\n"
                    f"Chain: {a['chain']}\n"
                    f"Tx: <code>{a['tx']}</code>\n"
                    f"From: {a['from']}\n"
                    f"To: {a['to']}\n"
                    f"Value: ${a['usd']:,}"
                )
            )
        # Огонь в фоне:
        for t in msgs:
            asyncio.create_task(send_telegram(t))

    return {"ok": True, "alerts": len(alerts)}
