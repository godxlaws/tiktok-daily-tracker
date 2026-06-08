import requests
import os
import json
import time
import base64
from datetime import datetime, timedelta
from urllib.parse import quote
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP
from zoneinfo import ZoneInfo

# ══════════════════════════════════════
# CONFIG
# ══════════════════════════════════════

def require_env(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing GitHub secret: {name}")
    return value

BOT_TOKEN       = require_env("BOT_TOKEN")
CHAT_ID         = require_env("CHAT_ID")
TABCUT_EMAIL    = require_env("TABCUT_EMAIL")
TABCUT_PASSWORD = require_env("TABCUT_PASSWORD")

BASE_URL  = "https://www.tabcut.com"
YESTERDAY = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

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
                "email":       TABCUT_EMAIL,
                "password":    enc_pw,
                "csrfToken":   csrf,
                "callbackUrl": f"{BASE_URL}/workbench",
                "redirect":    "false",
                "json":        "true",
            },
        )
        if r.status_code == 200:
            print("✅ Login สำเร็จ")
            return True
        print(f"❌ Login ล้มเหลว: {r.status_code}")
        return False

    except Exception as e:
        print("Login error:", e)
        return False


# ══════════════════════════════════════
# FETCH
# ══════════════════════════════════════

def fetch_trend(trend_type):
    """ดึงสินค้ากำลังมา (surge 1d หรือ 3d)"""
    payload = {
        "pageNo":          1,
        "pageSize":        24,
        "region":          "TH",
        "itemCategoryId":  "0",
        "trendFilterType": trend_type,
    }
    encoded = quote(json.dumps(payload, separators=(",", ":")))
    url = f"{BASE_URL}/api/trpc/ranking.goods.hotTrendData?input={encoded}"
    try:
        res = session.get(url).json()
        return res["result"]["data"]["result"]["data"]
    except:
        return []


def fetch_top_selling(limit=5):
    """ดึงสินค้าขายดีสุดวันนี้"""
    payload = {
        "pageNo":     1,
        "pageSize":   24,
        "rankType":   1,
        "bizDate":    YESTERDAY,
        "region":     "TH",
        "categoryId": "0",
        "orderType":  "1",
        "sellerType": "",
    }
    encoded = quote(json.dumps(payload, separators=(",", ":")))
    url = f"{BASE_URL}/api/trpc/ranking.goods.rankingData?input={encoded}"
    try:
        res = session.get(url).json()
        items = (
            res.get("result", {}).get("data", {}).get("result", {}).get("data", []) or
            res.get("result", {}).get("data", {}).get("data", []) or
            res.get("result", {}).get("data", [])
        )
        valid = [p for p in items if get_price_from_list(p) > 1]
        print(f"[TOP] valid: {len(valid)}")
        return valid[:limit]
    except Exception as e:
        print(f"[TOP] error: {e}")
        return []


# ══════════════════════════════════════
# HELPERS — TREND API
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
def title(p):   return get(p, "itemTitle", "?")[:50]
def price(p):   return safe_int(get(p, "localPrice"))

def link(p):
    iid = get(p, "itemId")
    return f"https://www.tiktok.com/view/product/{iid}" if iid else ""

def img(p):
    url = get(p, "itemPicUrl")
    return url if url and url != 0 else ""

def safe_text(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ══════════════════════════════════════
# HELPERS — TOP SELLING API
# (field name ต่างจาก trend API)
# ══════════════════════════════════════

def get_price_from_list(p):
    """ดึงราคาจาก priceList ของ rankingData"""
    price_list = p.get("priceList") or []
    if price_list and isinstance(price_list, list):
        try:
            first = price_list[0]
            return safe_int(
                first.get("price") or
                first.get("localPrice") or
                first.get("salePrice") or 0
            )
        except:
            pass
    return safe_int(
        p.get("localPrice") or
        p.get("price") or
        p.get("salePrice") or 0
    )


def get_sold_from_info(p):
    """ดึงยอดขายจาก soldCountInfo ของ rankingData"""
    info = p.get("soldCountInfo") or {}
    if isinstance(info, dict):
        current = info.get("periodCurrent") or {}
        if isinstance(current, dict):
            return safe_int(
                current.get("local") or
                current.get("total") or 0
            )
        return safe_int(info.get("total") or 0)
    return safe_int(p.get("soldCountPeriod") or 0)


def img_top(p):
    """ดึงรูปจาก rankingData"""
    url = p.get("itemPicUrl") or p.get("picUrl") or ""
    return url if url and url != 0 else ""


def link_top(p):
    iid = p.get("itemId", "")
    return f"https://www.tiktok.com/view/product/{iid}" if iid else ""


# ══════════════════════════════════════
# ANALYZE
# ══════════════════════════════════════

def analyze(p):
    s1   = sold_1d(p)
    s3   = sold_3d(p)
    avg3 = s3 / 3 if s3 > 0 else 1
    growth = s1 / avg3
    score  = (s1 * 2) + s3 + (growth * 100)
    return s1, s3, growth, score


# ══════════════════════════════════════
# COLLECT + GROUP
# ══════════════════════════════════════

def collect_and_group():
    y  = fetch_trend(1)
    d3 = fetch_trend(2)

    merged = {}
    for p in y + d3:
        iid = p.get("itemId")
        if iid:
            merged[iid] = p

    viral, stable, peak = [], [], []

    for p in merged.values():
        if price(p) <= 1:
            continue

        s1, s3, growth, score = analyze(p)

        if s1 <= 0 or s3 <= 0:
            continue

        item = {
            "p":      p,
            "s1":     s1,
            "s3":     s3,
            "growth": round(growth, 2),
            "score":  score,
        }

        if growth >= 2.5:
            viral.append(item)
        elif growth < 1.2 and s1 >= 50:
            peak.append(item)
        else:
            stable.append(item)

    viral.sort(key=lambda x: x["growth"], reverse=True)
    stable.sort(key=lambda x: x["score"],  reverse=True)
    peak.sort(key=lambda x: x["s1"],       reverse=True)

    return viral[:3], stable[:4], peak[:3]


# ══════════════════════════════════════
# FORMAT
# ══════════════════════════════════════

def format_trend_item(i, item):
    """Format สำหรับ VIRAL / STABLE / PEAK"""
    p = item["p"]
    text = (
        f"{i}. <b>{safe_text(title(p))}</b>\n"
        f"💰 {price(p)} บาท\n"
        f"📦 1วัน: {item['s1']:,}  |  3วัน: {item['s3']:,}\n"
        f"📈 Growth: x{item['growth']}\n"
    )
    if link(p):
        text += f"\n🛒 <a href=\"{link(p)}\">ดูสินค้าใน TikTok Shop</a>"
    return text


def format_top_item(i, p):
    """Format สำหรับ TOP 5 ขายดี — ใช้ field ของ rankingData"""
    name  = safe_text((p.get("itemName") or "?")[:50])
    pr    = get_price_from_list(p)
    sold  = get_sold_from_info(p)
    comm  = p.get("commissionRate")
    comm_text = f"  💸 {round(float(comm)*100, 1)}%" if comm else ""
    lnk   = link_top(p)

    text = (
        f"{i}. <b>{name}</b>\n"
        f"💰 ฿{pr}  📦 ขายแล้ว {sold:,} ชิ้น{comm_text}\n"
    )
    if lnk:
        text += f"🛒 <a href=\"{lnk}\">ดูสินค้าใน TikTok Shop</a>"
    return text


# ══════════════════════════════════════
# TELEGRAM
# ══════════════════════════════════════

def send(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id":    CHAT_ID,
                "text":       msg,
                "parse_mode": "HTML",
            },
            timeout=15,
        )
    except Exception as e:
        print(f"send error: {e}")


def send_photo(img_url, caption):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
            json={
                "chat_id":    CHAT_ID,
                "photo":      img_url,
                "caption":    caption[:1024],
                "parse_mode": "HTML",
            },
            timeout=15,
        )
        if r.status_code != 200:
            send(caption)
    except Exception as e:
        print(f"send_photo error: {e}")
        send(caption)


def send_item(caption, img_url=""):
    if img_url:
        send_photo(img_url, caption)
    else:
        send(caption)
    time.sleep(1.5)


# ══════════════════════════════════════
# MAIN
# ══════════════════════════════════════

def main():
    if not login():
        send("❌ Login ไม่สำเร็จ")
        return

    viral, stable, peak = collect_and_group()
    top = fetch_top_selling(5)

    now = datetime.now(ZoneInfo("Asia/Bangkok"))

    # ─── Header ───
    send(
        f"📅 {now.strftime('%d/%m/%Y')}  ⏰ {now.strftime('%H:%M')}\n\n"
        f"🔥 <b>TikTok Shop Thailand — Daily Picks</b>"
    )
    time.sleep(1)

    # ─── VIRAL ───
    if viral:
        send("🚀 <b>VIRAL — เพิ่งระเบิด ทำเลยด่วน!</b>")
        for i, item in enumerate(viral, 1):
            send_item(format_trend_item(i, item), img(item["p"]))
    else:
        send("🚀 <b>VIRAL</b>\nไม่มีสินค้า breakout วันนี้")

    # ─── STABLE ───
    if stable:
        send("📈 <b>STABLE — กำลังโต ยังทันทำ</b>")
        for i, item in enumerate(stable, 1):
            send_item(format_trend_item(i, item), img(item["p"]))
    else:
        send("📈 <b>STABLE</b>\nไม่มีสินค้า stable วันนี้")

    # ─── PEAK ───
    if peak:
        send("⚠️ <b>PEAK — ขายดีแต่อิ่มตัวแล้ว</b>")
        for i, item in enumerate(peak, 1):
            send_item(format_trend_item(i, item), img(item["p"]))

    # ─── TOP 5 ขายดีสุด ───
    if top:
        send("🏆 <b>TOP 5 — ขายดีที่สุดวันนี้</b>")
        for i, p in enumerate(top, 1):
            send_item(format_top_item(i, p), img_top(p))
    else:
        send("🏆 <b>TOP 5</b>\nไม่มีข้อมูลวันนี้")

    print("✅ เสร็จแล้ว")


if __name__ == "__main__":
    main()
