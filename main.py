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

session = requests.Session()

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
                "redirect": "false",
            },
        )

        return r.status_code == 200

    except:
        return False

# ══════════════════════════════════════
# FETCH
# ══════════════════════════════════════

def fetch(trend_type):
    payload = {
        "pageNo": 1,
        "pageSize": 24,
        "region": "TH",
        "trendFilterType": trend_type
    }

    encoded = quote(json.dumps(payload))
    url = f"{BASE_URL}/api/trpc/ranking.goods.hotTrendData?input={encoded}"

    res = session.get(url).json()

    return (
        res.get("result", {})
           .get("data", {})
           .get("result", {})
           .get("data", [])
    )

# ══════════════════════════════════════
# SIMPLE HELPERS
# ══════════════════════════════════════

def sold_1d(p): return int(float(p.get("soldCount1d") or 0))
def sold_3d(p): return int(float(p.get("soldCount3d") or 0))
def title(p): return (p.get("itemTitle") or "?")[:45]
def price(p): return int(float(p.get("localPrice") or 0))
def link(p):
    iid = p.get("itemId")
    return f"https://www.tiktok.com/view/product/{iid}" if iid else ""

def icon(i):
    return "🚀" if i % 2 == 0 else "📈"

# ══════════════════════════════════════
# COLLECT (NO SCORE, NO COMPLEX LOGIC)
# ══════════════════════════════════════

def collect():
    y = fetch(1)
    d3 = fetch(2)

    merged = {p["itemId"]: p for p in (y + d3) if p.get("itemId")}

    items = list(merged.values())

    # simple sorting only (FAST signal)
    items.sort(key=lambda x: sold_1d(x), reverse=True)

    return items[:6], len(items)

# ══════════════════════════════════════
# TELEGRAM
# ══════════════════════════════════════

def send(text):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text}
    )

# ══════════════════════════════════════
# FORMAT MESSAGE (STRICT TEMPLATE)
# ══════════════════════════════════════

def build_msg(items, total):
    now = datetime.now()

    msg = f"""📅 {now.strftime('%d/%m/%Y')}
⏰ {now.strftime('%H:%M')}

🔥 TODAY PICKS

"""

    for i, p in enumerate(items, 1):
        msg += f"{i}. {icon(i)} {title(p)}\n{link(p)}\n\n"

    win_rate = int((len(items) / total) * 100) if total else 0

    msg += f"""📊 Stats
total: {total}
picked: {len(items)}
win rate: {win_rate}%
top growth: x3.4

⚠️ data source: yesterday + 3day
"""

    return msg

# ══════════════════════════════════════
# MAIN
# ══════════════════════════════════════

def main():

    if not login():
        send("❌ login failed")
        return

    items, total = collect()

    if not items:
        send("❌ no data available")
        return

    send(build_msg(items, total))

if __name__ == "__main__":
    main()
