"""
AUTO MANCING v3.0 — PYROFORK + LOCAL CAPTCHA + OPENAI/GROQ AI + 2CAPTCHA/CAPSOLVER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Flow:
1. Kirim /mancing → tunggu sesi selesai
2. Kalau ada captcha:
   a. Coba logika lokal dulu (math, hitung emoji, pola, pilih ikan)
   b. Kalau captcha berupa GAMBAR dan CAPTCHA_PROVIDER di-set → kirim ke 2Captcha/CapSolver
   c. Kalau masih gagal → tanya AI (OpenAI/Groq)
3. Hasil mancing → scan ikan rare → /favorite → /jual semua
4. Ulangi

ENV VARIABLES (Railway):
  API_ID           = API ID telegram lo
  API_HASH         = API HASH telegram lo
  SESSION_STRING   = Session string lo
  FISHING_BOT      = username bot mancing (default: fish_it_vip4_bot)
  MANCING_INTERVAL = jeda antar sesi dalam detik (default: 305)
  OPENAI_API_KEY   = API key OpenAI/Groq
  OPENAI_BASE_URL  = Base URL API (default: OpenAI. Buat Groq: https://api.groq.com/openai/v1)
  OPENAI_MODEL     = Model (default: llama-3.3-70b-versatile)
  CAPTCHA_PROVIDER = "2captcha" atau "capsolver" (kosongkan untuk nonaktifkan)
  CAPTCHA_API_KEY  = API key dari 2captcha.com atau capsolver.com
"""

import os
import re
import time
import base64
import asyncio
import json
import urllib.request
import urllib.parse
from pyrogram import Client, filters, idle
from pyrogram.errors import FloodWait
from pyrogram.handlers import MessageHandler

# ━━━ CONFIG ━━━
API_ID           = int(os.environ.get("API_ID", "0"))
API_HASH         = os.environ.get("API_HASH", "")
SESSION_STRING   = os.environ.get("SESSION_STRING", "")
FISHING_BOT      = os.environ.get("FISHING_BOT", "fish_it_vip4_bot").lstrip("@")
MANCING_INTERVAL = int(os.environ.get("MANCING_INTERVAL", "305"))

# AI config (OpenAI-compatible: OpenAI official, Groq, DeepSeek, OpenRouter, dll)
OPENAI_API_KEY   = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL  = os.environ.get("OPENAI_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
OPENAI_MODEL     = os.environ.get("OPENAI_MODEL", "llama-3.3-70b-versatile")

# 2Captcha / CapSolver config (untuk captcha berupa GAMBAR)
CAPTCHA_PROVIDER = os.environ.get("CAPTCHA_PROVIDER", "").lower().strip()   # "2captcha" / "capsolver" / "" (off)
CAPTCHA_API_KEY  = os.environ.get("CAPTCHA_API_KEY", "")

# Emoji ikan rare yang mau di-favorite
RARE_EMOJIS = ["✨", "☀️", "🌟", "🟤"]

# Keyword captcha
CAPTCHA_KEYWORDS = ["verifikasi", "captcha", "robot", "buktikan", "pilih", "berapa", "hitung"]

# Keyword konfirmasi jual
CONFIRM_KEYWORDS = ["ya, jual semua", "ya,jual semua", "jual semua", "✅"]
CANCEL_KEYWORDS  = ["batal", "cancel", "❌"]

# ━━━ STATE ━━━
state = {
    "total_catch": 0,
    "rare_inventory_nums": [],
    "waiting_result": False,
    "scanning_pages": False,
    "waiting_sell": False,
    "inv_pages_scanned": 0,
    "inv_message_id": None,   # message_id inventory terbaru untuk klik Next
}

# ━━━ UTILS ━━━
def log(step, msg):
    print(f"[{time.strftime('%H:%M:%S')}] [{step}] {msg}", flush=True)


def is_captcha(text, message):
    """Deteksi apakah pesan ini captcha (button-based ATAU image-based)."""
    text = (text or "").lower()
    keywords = ["captcha", "verifikasi", "pilih", "hitung", "berapa"]
    has_keyword = any(k in text for k in keywords)
    has_buttons = bool(message.reply_markup and hasattr(message.reply_markup, "inline_keyboard"))
    has_photo   = bool(message.photo)
    return has_keyword and (has_buttons or has_photo)


async def ask_ai(soal, pilihan):
    """Tanya AI (OpenAI/Groq) untuk jawab captcha, retry kalau kena 429."""
    if not OPENAI_API_KEY:
        return None

    url = f"{OPENAI_BASE_URL}/chat/completions"
    prompt = (
        f"Kamu adalah solver captcha. Jawab dengan HANYA teks tombol yang benar, tidak ada kata lain.\n"
        f"Soal: {soal}\n"
        f"Pilihan tombol: {', '.join(pilihan)}\n"
        f"Jawab dengan salah satu teks tombol di atas yang paling tepat:"
    )
    payload = json.dumps({
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": "You output exactly one matching button text from the list. No explanation, no quotes."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 50,
    }).encode()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}",
    }

    for attempt in range(3):  # retry 3x
        try:
            req = urllib.request.Request(url, data=payload, headers=headers)
            loop = asyncio.get_event_loop()
            def do_request():
                with urllib.request.urlopen(req, timeout=20) as resp:
                    return json.loads(resp.read())
            data = await loop.run_in_executor(None, do_request)
            answer = data["choices"][0]["message"]["content"].strip()
            answer = answer.strip('"').strip("'").strip()
            log("CAPTCHA", f"🤖 AI jawab: '{answer}'")
            return answer
        except Exception as e:
            err = str(e)
            log("CAPTCHA", f"❌ AI error (attempt {attempt+1}): {err}")
            if ("429" in err or "rate" in err.lower()) and attempt < 2:
                await asyncio.sleep(5)
                continue
            if attempt < 2:
                await asyncio.sleep(2)
                continue
            break
    return None


# ━━━ 2CAPTCHA / CAPSOLVER (IMAGE CAPTCHA) ━━━
def _http_post(url, data, headers=None, is_json=False):
    payload = json.dumps(data).encode() if is_json else urllib.parse.urlencode(data).encode()
    hdrs = headers or ({"Content-Type": "application/json"} if is_json else {})
    req = urllib.request.Request(url, data=payload, headers=hdrs)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _http_get(url):
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read())


async def solve_image_captcha_2captcha(image_b64):
    """Solve captcha gambar pakai 2Captcha.com (https://2captcha.com)."""
    if not CAPTCHA_API_KEY:
        return None
    loop = asyncio.get_event_loop()
    try:
        submit = await loop.run_in_executor(None, lambda: _http_post(
            "https://2captcha.com/in.php",
            {"key": CAPTCHA_API_KEY, "method": "base64", "body": image_b64, "json": 1}
        ))
        if submit.get("status") != 1:
            log("CAPTCHA", f"❌ 2Captcha submit gagal: {submit}")
            return None
        cap_id = submit["request"]

        for _ in range(24):  # max ~2 menit polling
            await asyncio.sleep(5)
            result = await loop.run_in_executor(None, lambda: _http_get(
                f"https://2captcha.com/res.php?key={CAPTCHA_API_KEY}&action=get&id={cap_id}&json=1"
            ))
            if result.get("status") == 1:
                answer = result["request"]
                log("CAPTCHA", f"🔎 2Captcha jawab: '{answer}'")
                return answer
            if result.get("request") != "CAPCHA_NOT_READY":
                log("CAPTCHA", f"❌ 2Captcha error: {result}")
                return None
        log("CAPTCHA", "⌛ 2Captcha timeout")
        return None
    except Exception as e:
        log("CAPTCHA", f"❌ 2Captcha exception: {e}")
        return None


async def solve_image_captcha_capsolver(image_b64):
    """Solve captcha gambar pakai CapSolver.com (https://capsolver.com)."""
    if not CAPTCHA_API_KEY:
        return None
    loop = asyncio.get_event_loop()
    try:
        create = await loop.run_in_executor(None, lambda: _http_post(
            "https://api.capsolver.com/createTask",
            {"clientKey": CAPTCHA_API_KEY, "task": {"type": "ImageToTextTask", "body": image_b64}},
            is_json=True
        ))
        if create.get("errorId"):
            log("CAPTCHA", f"❌ CapSolver createTask gagal: {create}")
            return None
        task_id = create["taskId"]

        for _ in range(24):
            await asyncio.sleep(5)
            result = await loop.run_in_executor(None, lambda: _http_post(
                "https://api.capsolver.com/getTaskResult",
                {"clientKey": CAPTCHA_API_KEY, "taskId": task_id},
                is_json=True
            ))
            if result.get("status") == "ready":
                answer = result["solution"]["text"]
                log("CAPTCHA", f"🔎 CapSolver jawab: '{answer}'")
                return answer
            if result.get("status") == "failed" or result.get("errorId"):
                log("CAPTCHA", f"❌ CapSolver error: {result}")
                return None
        log("CAPTCHA", "⌛ CapSolver timeout")
        return None
    except Exception as e:
        log("CAPTCHA", f"❌ CapSolver exception: {e}")
        return None


async def solve_image_captcha(client, message):
    """Download foto captcha dari pesan, kirim ke provider aktif, balikin teks jawaban."""
    if not CAPTCHA_PROVIDER or not CAPTCHA_API_KEY:
        return None
    if not message.photo:
        return None
    try:
        raw_bytes = await client.download_media(message, in_memory=True)
        image_b64 = base64.b64encode(raw_bytes.getvalue()).decode()
    except Exception as e:
        log("CAPTCHA", f"❌ Gagal download foto captcha: {e}")
        return None

    if CAPTCHA_PROVIDER == "2captcha":
        return await solve_image_captcha_2captcha(image_b64)
    elif CAPTCHA_PROVIDER == "capsolver":
        return await solve_image_captcha_capsolver(image_b64)
    else:
        log("CAPTCHA", f"⚠️ CAPTCHA_PROVIDER '{CAPTCHA_PROVIDER}' tidak dikenal (pakai '2captcha' atau 'capsolver')")
        return None


async def solve_captcha(client, message):
    """Jawab captcha: logika lokal → image captcha (2Captcha/CapSolver) → AI fallback."""
    raw  = (message.text or message.caption or "")
    text = raw.lower()
    log("CAPTCHA", f"🔐 Captcha detected: {text[:200]}...")

    buttons = []
    if message.reply_markup and hasattr(message.reply_markup, "inline_keyboard"):
        buttons = [
            (r, c, btn.text.strip())
            for r, row in enumerate(message.reply_markup.inline_keyboard)
            for c, btn in enumerate(row)
            if btn.text
        ]
    btn_labels = [b[2] for b in buttons]

    # ── 1. HITUNG EMOJI ──────────────────────────────────────
    if "hitung" in text:
        FISH_ALL = ["🐟","🦑","🐙","🪼","🦐","🦞","🦀","🐡","🐠","🐬","🐳","🐋","🦈","🦭","🐊"]
        for fish in FISH_ALL:
            count = raw.count(fish)
            if count > 0:
                for r, c, b in buttons:
                    if b.strip() == str(count):
                        await message.click(r, c)
                        log("CAPTCHA", f"🔢 Hitung '{fish}' = {count} → klik '{b}'")
                        return True

    # ── 2. MATEMATIKA ─────────────────────────────────────────
    match = re.search(r'(\d+)\s*([\+\-\*x\/])\s*(\d+)', text)
    if match:
        a, op, b = int(match.group(1)), match.group(2), int(match.group(3))
        if   op == "+":          res = a + b
        elif op == "-":          res = a - b
        elif op in ["x", "*"]:   res = a * b
        elif op == "/":          res = int(a / b) if b != 0 else None
        else:                    res = None
        if res is not None:
            for r, c, btxt in buttons:
                if str(res) == btxt:
                    await message.click(r, c)
                    log("CAPTCHA", f"➕ Math {a}{op}{b} = {res} → klik '{btxt}'")
                    return True

    # ── 3. LANJUTKAN POLA ─────────────────────────────────────
    if "pola" in text:
        nums = [int(n) for n in re.findall(r'\d+', text)]
        if len(nums) >= 3:
            diffs = [nums[i+1] - nums[i] for i in range(len(nums)-1)]
            if len(set(diffs)) == 1:
                answer = nums[-1] + diffs[0]
                for r, c, btxt in buttons:
                    if btxt.strip() == str(answer):
                        await message.click(r, c)
                        log("CAPTCHA", f"🔢 Pola aritmatika +{diffs[0]}: jawaban={answer} → klik '{btxt}'")
                        return True
            if all(nums[i] != 0 for i in range(len(nums)-1)):
                ratios = [nums[i+1] / nums[i] for i in range(len(nums)-1)]
                if len(set(ratios)) == 1:
                    answer = int(nums[-1] * ratios[0])
                    for r, c, btxt in buttons:
                        if btxt.strip() == str(answer):
                            await message.click(r, c)
                            log("CAPTCHA", f"🔢 Pola geometri x{ratios[0]}: jawaban={answer} → klik '{btxt}'")
                            return True

    # ── 4. PILIH IKAN ─────────────────────────────────────────
    FISH_EMOJIS = ["🐟","🦑","🐙","🪼","🦐","🦞","🦀","🐡","🐠","🐬","🐳","🐋","🦈","🦭","🐊"]
    if "ikan" in text:
        for r, c, b in buttons:
            if any(fish in b for fish in FISH_EMOJIS):
                await message.click(r, c)
                log("CAPTCHA", f"🐟 Pilih ikan → klik '{b}'")
                return True

    # ── 5. IMAGE CAPTCHA (2Captcha / CapSolver) ───────────────
    if message.photo and CAPTCHA_PROVIDER:
        log("CAPTCHA", f"🖼️ Captcha gambar terdeteksi, kirim ke {CAPTCHA_PROVIDER}...")
        img_answer = await solve_image_captcha(client, message)
        if img_answer:
            if buttons:
                for r, c, b in buttons:
                    if b.strip().lower() == img_answer.strip().lower():
                        await message.click(r, c)
                        log("CAPTCHA", f"🖼️ {CAPTCHA_PROVIDER} exact → klik '{b}'")
                        return True
                for r, c, b in buttons:
                    if img_answer.lower() in b.lower() or b.lower() in img_answer.lower():
                        await message.click(r, c)
                        log("CAPTCHA", f"🖼️ {CAPTCHA_PROVIDER} partial → klik '{b}'")
                        return True
            else:
                # Captcha teks-gambar tanpa tombol (misal: ketik ulang teks) → balas via chat
                await safe_send(client, FISHING_BOT, img_answer.strip())
                log("CAPTCHA", f"🖼️ {CAPTCHA_PROVIDER} jawab via reply: '{img_answer}'")
                return True

    # ── 6. AI FALLBACK (OpenAI/Groq) ──────────────────────────
    log("CAPTCHA", "🤖 Logika lokal & image captcha gagal, tanya AI...")
    ai_answer = await ask_ai(raw, btn_labels)
    if ai_answer:
        for r, c, b in buttons:
            if b.strip().lower() == ai_answer.lower():
                await message.click(r, c)
                log("CAPTCHA", f"🤖 AI exact → klik '{b}'")
                return True
        for r, c, b in buttons:
            if ai_answer.lower() in b.lower() or b.lower() in ai_answer.lower():
                await message.click(r, c)
                log("CAPTCHA", f"🤖 AI partial → klik '{b}'")
                return True

    log("CAPTCHA", f"❌ Semua metode gagal. Tombol: {btn_labels}")
    return False



def parse_rare_from_result(text):
    """Parse hasil mancing, cari nomor urut ikan rare."""
    rare_numbers = []
    total = 0

    total_match = re.search(r'Ditangkap\s*\((\d+)\s*ikan\)', text)
    if total_match:
        total = int(total_match.group(1))

    for line in text.split('\n'):
        line = line.strip()
        match = re.match(r'^(\d+)\.\s+(.+)', line)
        if not match:
            continue
        number = int(match.group(1))
        content = match.group(2)
        for emoji in RARE_EMOJIS:
            if emoji in content:
                rare_numbers.append(number)
                log("PARSE", f"🎯 Rare #{number}: {content[:40]}")
                break

    return total, rare_numbers


def calc_inventory_numbers(total_catch, rare_result_nums):
    """Hitung nomor inventory: inv = (total - urutan) + 1"""
    return [(total_catch - n) + 1 for n in rare_result_nums]


def parse_rare_from_inventory(text):
    """
    Scan halaman inventory, cari nomor slot ikan rare.
    Format inventory:
      N. [emoji] Nama Ikan
         L X.Xkg • 🌕 Y Coins • [rarity_tag]
    Rare = tag sub-baris mengandung: artefak, myth, legend
    """
    RARE_TAGS = ["artefak", "myth", "legend"]
    rare_slots = []
    lines = text.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        item_match = re.match(r'^(\d+)\.\s+(.+)', line)
        if item_match:
            number = int(item_match.group(1))
            name   = item_match.group(2)
            sub    = lines[i + 1].strip() if i + 1 < len(lines) else ""
            if any(tag in sub.lower() for tag in RARE_TAGS):
                rare_slots.append(number)
                log("INV-SCAN", f"🎯 Rare slot #{number}: {name} | {sub[:40]}")
        i += 1
    return rare_slots


async def click_next(client, msg):
    """Klik tombol Next di inventory. Fetch ulang message supaya tidak stale."""
    try:
        fresh = await client.get_messages(msg.chat.id, msg.id)
        target = fresh if fresh and fresh.reply_markup else msg
    except:
        target = msg

    if not target.reply_markup or not hasattr(target.reply_markup, 'inline_keyboard'):
        log("INV", "⚠️ Tidak ada reply_markup")
        return False

    all_btns = [(r, c, btn.text) for r, row in enumerate(target.reply_markup.inline_keyboard) for c, btn in enumerate(row) if btn.text]
    log("INV", f"🔘 Tombol: {[b[2] for b in all_btns]}")

    NEXT_KEYWORDS = ["next", "selanjutnya", "berikutnya", "➡", "▶", ">>", "›", "»", "→"]
    for r, c, label in all_btns:
        if any(k in label.lower() for k in NEXT_KEYWORDS):
            try:
                await target.click(r, c)
                log("INV", f"➡️ Klik next: '{label}'")
                return True
            except FloodWait as e:
                await asyncio.sleep(e.value)
                try:
                    await target.click(r, c)
                    return True
                except:
                    return False
            except Exception as e:
                log("INV", f"❌ Gagal klik '{label}': {e}")
                return False

    log("INV", f"⚠️ Tombol next tidak ditemukan dari: {[b[2] for b in all_btns]}")
    return False


def find_confirm_button(msg):
    if not msg.reply_markup or not hasattr(msg.reply_markup, 'inline_keyboard'):
        return None
    for r, row in enumerate(msg.reply_markup.inline_keyboard):
        for c, btn in enumerate(row):
            txt = (btn.text or "").lower().strip()
            if any(cancel in txt for cancel in CANCEL_KEYWORDS):
                continue
            if any(kw.lower() in txt for kw in CONFIRM_KEYWORDS):
                return r, c, btn.text
    return None


async def safe_send(client, bot, text):
    try:
        await client.send_message(bot, text)
        log("SEND", f"📤 {text[:60]}")
    except FloodWait as e:
        log("SEND", f"⏳ FloodWait {e.value}s...")
        await asyncio.sleep(e.value)
        await client.send_message(bot, text)
    except Exception as e:
        log("SEND", f"❌ Gagal kirim: {e}")


async def instant_click(msg, r, c):
    try:
        await msg.click(r, c)
        return True
    except FloodWait as e:
        await asyncio.sleep(e.value)
        try:
            await msg.click(r, c)
            return True
        except:
            return False
    except:
        return False


async def proceed_to_favorite_and_sell(client):
    """Kirim /favorite lalu /jual semua."""
    if state["rare_inventory_nums"]:
        numbers_str = " ".join(str(n) for n in state["rare_inventory_nums"])
        log("FAV", f"⭐ Kirim /favorite {numbers_str}")
        await safe_send(client, FISHING_BOT, f"/favorite {numbers_str}")
        await asyncio.sleep(2)
    else:
        log("FAV", "📭 Tidak ada rare di halaman 1-2, skip favorite")

    await safe_send(client, FISHING_BOT, "/jual semua")
    state["waiting_sell"] = True


# ━━━ CLIENT ━━━
app = Client("automancing", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)


# ━━━ HANDLER ━━━
def is_fishing_bot(_, __, msg):
    if not msg.from_user:
        return False
    if msg.from_user.username:
        return msg.from_user.username.lower() == FISHING_BOT.lower()
    return False

fishing_bot_filter = filters.create(is_fishing_bot)


@app.on_message(filters.private & fishing_bot_filter)
async def handle_fishing_bot(client, message):
    text = message.text or message.caption or ""

    # ━━ Captcha ━━
    if is_captcha(text, message):
        await solve_captcha(client, message)
        return

    # ━━ Hasil mancing selesai ━━
    if "SESI MANCING SELESAI" in text or "Yang Ditangkap" in text:
        state["waiting_result"] = False
        log("MANCING", "🎣 Sesi selesai! Parsing...")

        total, rare_nums = parse_rare_from_result(text)
        state["total_catch"] = total

        if rare_nums:
            inv_nums = calc_inventory_numbers(total, rare_nums)
            state["rare_inventory_nums"] = inv_nums
            log("MANCING", f"⭐ Urutan: {rare_nums} → Inventory: {inv_nums}")
        else:
            state["rare_inventory_nums"] = []
            log("MANCING", "📭 Tidak ada ikan rare")

        await asyncio.sleep(2)
        state["scanning_pages"] = True
        state["inv_pages_scanned"] = 0
        await safe_send(client, FISHING_BOT, "/inventory")
        return

    # ━━ Buka inventory halaman per halaman (max 2 halaman, untuk "jalan" aja) ━━
    if state["scanning_pages"] and "Slot terisi" in text:
        page_match = re.search(r'Halaman[:\s]+(\d+)/(\d+)', text)
        current_page = int(page_match.group(1)) if page_match else 1
        total_pages  = int(page_match.group(2)) if page_match else 1

        log("INV", f"📄 Halaman {current_page}/{total_pages}")
        state["inv_pages_scanned"] = current_page

        if current_page == 1 and total_pages >= 2:
            await asyncio.sleep(1)
            clicked = await click_next(client, message)
            if clicked:
                log("INV", "➡️ Next → halaman 2")
            else:
                log("INV", "⚠️ Gagal klik Next, langsung favorite+jual")
                state["scanning_pages"] = False
                await proceed_to_favorite_and_sell(client)
        else:
            log("INV", f"✅ Inventory selesai dibuka. Rare dari mancing: {state['rare_inventory_nums']}")
            state["scanning_pages"] = False
            await proceed_to_favorite_and_sell(client)
        return

    # ━━ Konfirmasi jual ━━
    if state["waiting_sell"] and ("KONFIRMASI PENJUALAN" in text or "Jual semua ikan" in text):
        result = find_confirm_button(message)
        if result:
            r, c, label = result
            success = await instant_click(message, r, c)
            if success:
                log("JUAL", f"✅ TERJUAL! '{label}'")
                state["waiting_sell"] = False
        return

    # ━━ Favorite berhasil ━━
    if "favorit" in text.lower() and "berhasil" in text.lower():
        log("FAV", "⭐ Favorite berhasil!")
        return


# ━━━ LOOP MANCING ━━━
async def mancing_loop(client):
    while True:
        log("LOOP", "🎣 Mulai mancing...")
        state["waiting_result"] = True
        await safe_send(client, FISHING_BOT, "/mancing")
        await asyncio.sleep(MANCING_INTERVAL + 60)
        log("LOOP", "🔄 Sesi berikutnya...")


# ━━━ STARTUP ━━━
async def main():
    missing = []
    if not API_ID: missing.append("API_ID")
    if not API_HASH: missing.append("API_HASH")
    if not SESSION_STRING: missing.append("SESSION_STRING")
    if missing:
        print(f"❌ Missing: {', '.join(missing)}", flush=True)
        return

    print("=" * 50, flush=True)
    print("  🎣 AUTO MANCING v3.0 (Pyrofork + AI + 2Captcha/CapSolver)", flush=True)
    print(f"  🤖 Bot: @{FISHING_BOT}", flush=True)
    print(f"  ⏳ Interval: {MANCING_INTERVAL}s", flush=True)
    print(f"  ⭐ Rare: {' '.join(RARE_EMOJIS)}", flush=True)
    print(f"  🧠 AI: {'ON (' + OPENAI_MODEL + ')' if OPENAI_API_KEY else 'OFF'}", flush=True)
    print(f"  🌐 AI URL: {OPENAI_BASE_URL}", flush=True)
    print(f"  🖼️ Image Captcha: {'ON (' + CAPTCHA_PROVIDER + ')' if (CAPTCHA_PROVIDER and CAPTCHA_API_KEY) else 'OFF'}", flush=True)
    print("=" * 50, flush=True)

    await app.start()

    try:
        bot = await app.get_users(FISHING_BOT)
        log("INIT", f"✅ Bot: @{bot.username} (ID: {bot.id})")
    except Exception as e:
        log("INIT", f"⚠️ Bot: {e}")

    log("INIT", "━" * 40)
    log("INIT", "🟢 AUTO MANCING ACTIVE!")
    log("INIT", "   🔐 Local captcha solver siap!")
    if CAPTCHA_PROVIDER and CAPTCHA_API_KEY:
        log("INIT", f"   🖼️ Image captcha solver siap ({CAPTCHA_PROVIDER})!")
    log("INIT", "   🤖 AI fallback siap!")
    log("INIT", "   Tinggal ditinggal tidur 😴")
    log("INIT", "━" * 40)

    asyncio.create_task(mancing_loop(app))

    await idle()
    await app.stop()


if __name__ == "__main__":
    app.run(main())
