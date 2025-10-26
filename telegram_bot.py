import os, json
from aiohttp import web
from aiogram import Bot

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")

async def send_alerts(request):
    data = await request.json()
    alerts = data.get("alerts", [])
    for a in alerts:
        text = (
            f"<b>🐋 Whale Alert</b>\n"
            f"Chain: {a.get('chain')}\n"
            f"Tx: <code>{a.get('tx')}</code>\n"
            f"From: {a.get('from')}\n"
            f"To: {a.get('to')}\n"
            f"Value: ${a.get('usd'):,}"
        )
        await bot.send_message(CHAT_ID, text)
    return web.json_response({"sent": len(alerts)})

app = web.Application()
app.router.add_post("/send", send_alerts)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=9001)
