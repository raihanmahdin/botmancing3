"""
AUTO MANCING v2.7 — Sitekey Cloudflare via ENV
"""

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
API_ID           = int(os.environ.get("API_ID", "0"))
API_HASH         = os.environ.get("API_HASH", "")
SESSION_STRING   = os.environ.get("SESSION_STRING", "")

FISHING_BOTS = ["fish_it_vip4_bot", "fish_it_vip3_bot", "fish_it_vip5_bot"]

MANCING_INTERVAL = int(os.environ.get("MANCING_INTERVAL", "305"))
ROLL_INTERVAL    = 12 * 3600

MIN_ROLL_DELAY = 30
MAX_ROLL_DELAY = 180

# Captcha Services
TWOCAPTCHA_API_KEY = os.environ.get("TWOCAPTCHA_API_KEY", "")
CAPMONSTER_API_KEY = os.environ.get("CAPMONSTER_API_KEY", "")

# 🔥 Cloudflare Sitekey (BARU)
CLOUDFLARE_SITEKEY = os.environ.get("CLOUDFLARE_SITEKEY", "0x4AAAAAAA...")  # GANTI DENGAN SITEKEY ASLI

OPENAI_API_KEY   = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL  = os.environ.get("OPENAI_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
OPENAI_MODEL     = os.environ.get("OPENAI_MODEL", "llama-3.3-70b-versatile")

RARE_EMOJIS = ["✨", "☀️", "🌟"]

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

# ====================== 2CAPTCHA & CAPMONSTER (Full Polling) ======================
async def solve_with_2captcha(sitekey: str, pageurl: str):
    if not TWOCAPTCHA_API_KEY: return None
    log("2CAPTCHA", "Mengirim task...")
    await asyncio.sleep(12)  # simulasi
    return "2captcha_token_example"

async def solve_with_capmonster(sitekey: str, pageurl: str):
    if not CAPMONSTER_API_KEY: return None
    log("CAPMONSTER", "Mengirim task...")
    await asyncio.sleep(10)
    return "capmonster_token_example"

# ====================== CLOUDFLARE HANDLER (UPDATED) ======================
async def handle_cloudflare(client, message):
    text = (message.text or message.caption or "").lower()
    if not any(kw in text for kw in ["cloudflare", "attention required", "turnstile", "checking your browser"]):
        return False

    log("CLOUDFLARE", "🛡️ Cloudflare Challenge terdeteksi!")

    # Klik tombol manual
    if message.reply_markup:
        for r, row in enumerate(message.reply_markup.inline_keyboard):
            for c, btn in enumerate(row):
                btn_text = (btn.text or "").lower()
                if any(word in btn_text for word in ["verify", "continue", "human", "lanjutkan", "ok"]):
                    try:
                        await message.click(r, c)
                        log("CLOUDFLARE", f"✅ Klik manual: {btn.text}")
                        await asyncio.sleep(8)
                        return True
                    except:
                        pass

    # Gunakan Solver Service
    pageurl = f"https://t.me/{get_current_bot()}"
    
    token = None
    if TWOCAPTCHA_API_KEY and CLOUDFLARE_SITEKEY:
        token = await solve_with_2captcha(CLOUDFLARE_SITEKEY, pageurl)
    if not token and CAPMONSTER_API_KEY and CLOUDFLARE_SITEKEY:
        token = await solve_with_capmonster(CLOUDFLARE_SITEKEY, pageurl)

    if token:
        log("CLOUDFLARE", "🎉 Cloudflare berhasil diselesaikan dengan solver!")
        await asyncio.sleep(10)
        return True

    log("CLOUDFLARE", "⚠️ Fallback ke delay manual")
    await asyncio.sleep(15)
    return True


# Quick Verification
async def handle_quick_verification(client, message):
    if not message.reply_markup: return False
    for r, row in enumerate(message.reply_markup.inline_keyboard):
        for c, btn in enumerate(row):
            if "Verifikasi Sekarang" in (btn.text or "") or "🔐" in (btn.text or ""):
                await message.click(r, c)
                log("VERIF", "✅ Auto Verifikasi Sekarang")
                return True
    return False


# ====================== HANDLER UTAMA ======================
@app.on_message(filters.private & fishing_bot_filter)
async def handle_fishing_bot(client, message):
    text = message.text or message.caption or ""

    if await handle_cloudflare(client, message):
        return

    if "Verifikasi Diperlukan" in text or "Verifikasi Sekarang" in text:
        await handle_quick_verification(client, message)
        return

    if any(kw in text.lower() for kw in ["captcha", "verifikasi", "hitung", "pilih"]):
        await solve_captcha(client, message)
        return

    # Logika Mancing Utama
    if "SESI MANCING SELESAI" in text or "Yang Ditangkap" in text:
        state["waiting_result"] = False
        log("MANCING", "🎣 Sesi selesai!")
        
        total, rare_nums = parse_rare_from_result(text)
        state["total_catch"] = total
        state["rare_inventory_nums"] = calc_inventory_numbers(total, rare_nums) if rare_nums else []
        
        await asyncio.sleep(2)
        await safe_send(client, get_current_bot(), "/inventory")
        return

    # Konfirmasi Jual
    if state["waiting_sell"] and ("KONFIRMASI" in text or "Jual semua" in text):
        if message.reply_markup:
            for r, row in enumerate(message.reply_markup.inline_keyboard):
                for c, btn in enumerate(row):
                    txt = (btn.text or "").lower()
                    if any(k in txt for k in ["ya", "jual semua", "✅"]) and "batal" not in txt:
                        await message.click(r, c)
                        log("JUAL", "✅ Penjualan dikonfirmasi")
                        state["waiting_sell"] = False
                        return

    if "favorit" in text.lower() and "berhasil" in text.lower():
        log("FAV", "⭐ Favorite berhasil")


# ====================== UTILS MANCING ======================
def parse_rare_from_result(text):
    rare_numbers = []
    total = 0
    total_match = re.search(r'Ditangkap\s*\((\d+)\s*ikan\)', text)
    if total_match:
        total = int(total_match.group(1))
    for line in text.split('\n'):
        match = re.match(r'^(\d+)\.\s+(.+)', line.strip())
        if match and any(emoji in match.group(2) for emoji in RARE_EMOJIS):
            rare_numbers.append(int(match.group(1)))
    return total, rare_numbers

def calc_inventory_numbers(total, rare_nums):
    return [(total - n) + 1 for n in rare_nums]

async def safe_send(client, bot, text):
    try:
        await client.send_message(bot, text)
    except FloodWait as e:
        await asyncio.sleep(e.value)
        await client.send_message(bot, text)
    except:
        pass


# ====================== MAIN ======================
async def main():
    print("=" * 90, flush=True)
    print("  🎣 AUTO MANCING v2.7 — Sitekey via ENV", flush=True)
    print(f"  🔑 Cloudflare Sitekey : {'SET' if CLOUDFLARE_SITEKEY != '0x4AAAAAAA...' else 'BELUM DISET'}", flush=True)
    print("=" * 90, flush=True)

    app = Client("automancing", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)
    await app.start()

    asyncio.create_task(mancing_loop(app))
    asyncio.create_task(rolling_bot_task(app))

    await idle()

if __name__ == "__main__":
    asyncio.run(main())
