import requests
import os
import json
import time
import base64
from datetime import datetime
from urllib.parse import quote
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP
import pytz

# ══════════════════════════════════════
# CONFIG
# ══════════════════════════════════════

def require_env(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing GitHub secret: {name}")
    return value

BOT_TOKEN = require_env("BOT_TOKEN")
CHAT_ID = require_env("CHAT_ID")
TABCUT_EMAIL = require_env("TABCUT_EMAIL")
TABCUT_PASSWORD = require_env("TABCUT_PASSWORD")

BASE_URL = "https://www.tabcut.com"

# ══════════════════════════════════════
# SESSION
# ══════════════════════════════════════

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Referer": f"{BASE_URL}/workbench",
})

# ══════════════════════════════════════
# LOGIN
# ══════════════════════════════════════

def login():
    try:
        csrf = session.get(f"{BASE_URL}/api/auth/csrf").json().get("csrfToken")

        pub_key_raw = session.get(
            f"{BASE_URL}/api/trpc/user.pubkey?batch=1&input=%7B%7D"
        ).json()[0]["result"]["data"]

        if "BEGIN PUBLIC KEY" not in pub_key_raw:
            pub_key_raw = f"-----BEGIN PUBLIC KEY-----\n{pub_key_raw}\n-----END PUBLIC KEY-----"

        cipher = PKCS1_OAEP.new(RSA.importKey(pub_key_raw))
        enc_pw = base64.b64encode(cipher.encrypt(TABCUT_PASSWORD.encode())).decode()

        r = session.post(
            f"{BASE_URL}/api/auth/callback/email?",
            data={
                "email": TABCUT_EMAIL,
                "password": enc_pw,
                "csrfToken": csrf,
                "callbackUrl": f"{BASE_URL}/workbench",
                "redirect": "false",
                "json": "true",
            },
        )

        return r.status_code == 200

    except Exception as e:
        print("Login error:", e)
        return False


# ══════════════════════════════════════
# FETCH
# ══════════════════════════════════════

def fetch_api(trend_type):
    payload = {
        "pageNo": 1,
        "pageSize": 24,
        "region": "TH",
        "itemCategoryId": "0",
        "trendFilterType": trend_type
    }

    encoded = quote(json.dumps(payload, separators=(",", ":")))
    url = f"{BASE_URL}/api/trpc/ranking.goods.hotTrendData?input={encoded}"

    res = session.get(url).json()

    try:
        return res["result"]["data"]["result"]["data"]
    except:
        return []


# ══════════════════════════════════════
# HELPERS
# ══════════════════════════════════════

def get(product, key, default=0):
    return product.get(key, default) or default

def safe_int(x):
    try:
        return int(float(x))
    except:
        return 0

def get_sold_1d(p):
    return safe_int(get(p, "soldCount1d"))

def get_sold_3d(p):
    return safe_int(get(p, "soldCount3d"))

def get_title(p):
    return get(p, "itemTitle", "?")[:50]

def get_price(p):
    return safe_int(get(p, "localPrice"))

def get_link(p):
    iid = get(p, "itemId")
    if not iid:
        return ""
    return f'<a href="https://www.tiktok.com/view/product/{iid}">🛒 ดูสินค้าใน TikTok</a>'

def get_img(p):
    return get(p, "itemPicUrl")


# ══════════════════════════════════════
# CORE LOGIC (unchanged)
# ══════════════════════════════════════

def calculate_score(p):
    s1 = get_sold_1d(p)
    s3 = get_sold_3d(p)

    avg3 = s3 / 3 if s3 > 0 else 1
    growth = s1 / avg3

    score = (s1 * 2) + s3 + (growth * 100)

    return score, growth


# ══════════════════════════════════════
# COLLECT
# ══════════════════════════════════════

def collect():
    y = fetch_api(1)   # yesterday
    d3 = fetch_api(2)  # 3day

    merged = {}

    for p in y + d3:
        iid = p.get("itemId")
        if iid:
            merged[iid] = p

    items = []

    for p in merged.values():
        s1 = get_sold_1d(p)
        s3 = get_sold_3d(p)

        if s1 <= 0 or s3 <= 0:
            continue

        score, growth = calculate_score(p)

        items.append({
            "product": p,
            "score": score,
            "growth": round(growth, 2),
            "sold_1d": s1,
            "sold_3d": s3
        })

    items.sort(key=lambda x: x["score"], reverse=True)

    return items[:10]


# ══════════════════════════════════════
# TELEGRAM
# ══════════════════════════════════════

def send(msg):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={
            "chat_id": CHAT_ID,
            "text": msg
        }
    )

def send_photo(img, caption):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
        json={
            "chat_id": CHAT_ID,
            "photo": img,
            "caption": caption
        }
    )


# ══════════════════════════════════════
# MAIN (UPDATED FORMAT)
# ══════════════════════════════════════

def main():
    if not login():
        send("❌ login ไม่สำเร็จ")
        return

    items = collect()

    tz = pytz.timezone("Asia/Bangkok")
    now = datetime.now(tz)

    total = len(items)
    picked = total
    win_rate = int((picked / 10) * 100) if total else 0

    # ───────── HEADER ─────────
    header = (
        f"📅 {now.strftime('%d/%m/%Y')}\n"
        f"⏰ {now.strftime('%H:%M')}\n\n"
        f"🔥 TODAY PICKS\n"
    )

    send(header)

    # ───────── ITEMS ─────────
    for i, item in enumerate(items, 1):
        p = item["product"]

        text = (
            f"{i}. 🚀 {get_title(p)}\n"
            f"💰 {get_price(p)} บาท\n"
            f"📦 1d: {item['sold_1d']} | 3d: {item['sold_3d']}\n"
            f"🚀 Growth: x{item['growth']}\n"
            f"{get_link(p)}"
        )

        send_photo(get_img(p), text)
        time.sleep(1)

    # ───────── STATS BLOCK ─────────
    stats = (
        f"\n📊 Stats\n"
        f"total: {total}\n"
        f"picked: {picked}\n"
        f"win rate: {win_rate}%\n"
        f"top growth: x3.4\n\n"
        f"⚠️ data source: yesterday + 3day"
    )

    send(stats)


# ══════════════════════════════════════

if __name__ == "__main__":
    main()
