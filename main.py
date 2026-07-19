import os
import re
import time
import asyncio
import json
import urllib.request
import urllib.parse
import random
from pyrogram import Client, filters, idle
from pyrogram.errors import FloodWait

# ====================== CONFIG ======================
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")

FISHING_BOTS = ["fish_it_vip4_bot", "fish_it_vip3_bot", "fish_it_vip5_bot"]

MANCING_INTERVAL = int(os.environ.get("MANCING_INTERVAL", "305"))
ROLL_INTERVAL = 12 * 3600

MIN_ROLL_DELAY = 30
MAX_ROLL_DELAY = 180

TWOCAPTCHA_API_KEY = os.environ.get("TWOCAPTCHA_API_KEY", "")
CAPMONSTER_API_KEY = os.environ.get("CAPMONSTER_API_KEY", "")
CLOUDFLARE_SITEKEY = os.environ.get("CLOUDFLARE_SITEKEY", "")

# ====================== STATE ======================
state = {
    "total_catch": 0,
    "rare_inventory_nums": [],
    "waiting_result": False,
    "scanning_pages": False,
    "waiting_sell": False,
    "current_bot_index": 0,
}

current_bot = FISHING_BOTS[0]

def log(step, msg):
    print(f"[{time.strftime('%H:%M:%S')}] [{step}] {msg}", flush=True)

def get_current_bot():
    return current_bot

def switch_bot():
    global current_bot
    state["current_bot_index"] = (state["current_bot_index"] + 1) % len(FISHING_BOTS)
    current_bot = FISHING_BOTS[state["current_bot_index"]]
    log("ROLLING", f"🔄 GANTI BOT → @{current_bot}")
    return current_bot

def is_fishing_bot(_, __, msg):
    return msg.from_user and msg.from_user.username and msg.from_user.username.lower() == get_current_bot().lower()

fishing_bot_filter = filters.create(is_fishing_bot)

# ====================== CLIENT ======================
app = Client(
    "automancing",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING
)

# ====================== HANDLER & FUNGSI LAINNYA ======================
# (Silakan paste seluruh fungsi handle_cloudflare, solve_captcha, mancing logic, dll di sini)

# Contoh handler sederhana dulu untuk test
@app.on_message(filters.private & fishing_bot_filter)
async def handle_fishing_bot(client, message):
    text = message.text or message.caption or ""
    log("BOT", f"Pesan diterima: {text[:100]}...")
    # Tambahkan logic lengkap nanti

async def main():
    await app.start()
    log("INIT", "✅ Bot berhasil dijalankan!")
    asyncio.create_task(mancing_loop(app))
    asyncio.create_task(rolling_bot_task(app))
    await idle()

async def mancing_loop(client):
    while True:
        await safe_send(client, get_current_bot(), "/mancing")
        await asyncio.sleep(MANCING_INTERVAL + 60)

async def rolling_bot_task(client):
    while True:
        await asyncio.sleep(ROLL_INTERVAL)
        delay = random.randint(MIN_ROLL_DELAY, MAX_ROLL_DELAY)
        log("ROLLING", f"Rolling dalam {delay} detik...")
        await asyncio.sleep(delay)
        switch_bot()

async def safe_send(client, bot, text):
    try:
        await client.send_message(bot, text)
    except:
        pass

if __name__ == "__main__":
    asyncio.run(main())
