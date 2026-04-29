import requests
import os
import json
import time
import base64
from datetime import datetime
from urllib.parse import quote
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP

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

def get(p, key, default=0):
    return p.get(key, default) or default

def safe_int(x):
    try:
        return int(float(x))
    except:
        return 0

def sold_1d(p): return safe_int(get(p, "soldCount1d"))
def sold_3d(p): return safe_int(get(p, "soldCount3d"))

def title(p): return get(p, "itemTitle", "?")[:50]
def price(p): return safe_int(get(p, "localPrice"))

def link(p):
    iid = get(p, "itemId")
    return f"https://www.tiktok.com/view/product/{iid}" if iid else ""

def img(p): return get(p, "itemPicUrl")


def safe_text(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ══════════════════════════════════════
# SCORE + MOMENTUM
# ══════════════════════════════════════

def analyze(p):
    s1 = sold_1d(p)
    s3 = sold_3d(p)

    avg3 = s3 / 3 if s3 > 0 else 1
    growth = s1 / avg3
    score = (s1 * 2) + s3 + (growth * 100)

    return s1, s3, growth, score


# ══════════════════════════════════════
# COLLECT + GROUP
# ══════════════════════════════════════

def collect_and_group():
    y = fetch_api(1)
    d3 = fetch_api(2)

    merged = {}

    for p in y + d3:
        iid = p.get("itemId")
        if iid:
            merged[iid] = p

    viral = []
    stable = []
    peak = []

    for p in merged.values():

        s1, s3, growth, score = analyze(p)

        if s1 <= 0 or s3 <= 0:
            continue

        item = {
            "p": p,
            "s1": s1,
            "s3": s3,
            "growth": round(growth, 2),
            "score": score
        }

        # ═════ GROUP RULES ═════

        if growth >= 2.5:
            viral.append(item)

        elif growth < 1.2 and s1 >= 50:
            peak.append(item)

        else:
            stable.append(item)

    # sort ภายในกลุ่ม
    viral.sort(key=lambda x: x["growth"], reverse=True)
    stable.sort(key=lambda x: x["score"], reverse=True)
    peak.sort(key=lambda x: x["s1"], reverse=True)

    return viral[:3], stable[:4], peak[:3]


# ══════════════════════════════════════
# TELEGRAM
# ══════════════════════════════════════

def send(msg):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={
            "chat_id": CHAT_ID,
            "text": msg,
            "parse_mode": "HTML"
        }
    )


def send_photo(img_url, caption):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
        json={
            "chat_id": CHAT_ID,
            "photo": img_url,
            "caption": caption,
            "parse_mode": "HTML"
        }
    )


# ══════════════════════════════════════
# FORMAT ITEM
# ══════════════════════════════════════

def format_item(i, item):
    p = item["p"]

    text = (
        f"{i}. 🚀 {safe_text(title(p))}\n"
        f"💰 {price(p)} บาท\n"
        f"📦 1d: {item['s1']} | 3d: {item['s3']}\n"
        f"📈 Growth: x{item['growth']}\n"
    )

    if link(p):
        text += f"\n🛒 <a href=\"{link(p)}\">ดูสินค้าใน TikTok</a>"

    return text


# ══════════════════════════════════════
# MAIN
# ══════════════════════════════════════

def main():

    if not login():
        send("❌ login ไม่สำเร็จ")
        return

    viral, stable, peak = collect_and_group()

    now = datetime.now()

    # ═════ HEADER ═════
    send(
        f"📅 {now.strftime('%d/%m/%Y')}\n"
        f"⏰ {now.strftime('%H:%M')}\n\n"
        f"🔥 TODAY PICKS (GROUP MODE)"
    )

    # ═════ VIRAL ═════
    if viral:
        send("🚀 VIRAL (Breakout)")
        for i, item in enumerate(viral, 1):
            p = item["p"]
            send_photo(img(p), format_item(i, item))
            time.sleep(1)

    # ═════ STABLE ═════
    if stable:
        send("📈 STABLE (Consistent)")
        for i, item in enumerate(stable, 1):
            p = item["p"]
            send_photo(img(p), format_item(i, item))
            time.sleep(1)

    # ═════ PEAK ═════
    if peak:
        send("⚠️ PEAK (Saturated)")
        for i, item in enumerate(peak, 1):
            p = item["p"]
            send_photo(img(p), format_item(i, item))
            time.sleep(1)


if __name__ == "__main__":
    main()
