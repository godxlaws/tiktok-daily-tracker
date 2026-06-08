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
        # กรองออกถ้าไม่มีราคา
        valid = [p for p in items if top_price(p) > 0]
        print(f"[TOP] found {len(items)} → valid {len(valid)}")
        return valid[:limit]
    except Exception as e:
        print(f"[TOP] error: {e}")
        return []


# ══════════════════════════════════════
# HELPERS — TREND API (hotTrendData)
# ══════════════════════════════════════

def get(p, key, default=0):
    return p.get(key, default) or default

def safe_int(x):
    try:
        return int(float(x))
    except:
        return 0

def safe_float(x):
    try:
        return float(x)
    except:
        return 0.0

def sold_1d(p): return safe_int(get(p, "soldCount1d"))
def sold_3d(p): return safe_int(get(p, "soldCount3d"))
def title(p):   return get(p, "itemTitle", "?")[:50]
def price(p):   return safe_int(get(p, "localPrice"))

def link_from_id(item_id):
    return f"https://www.tiktok.com/view/product/{item_id}" if item_id else ""

def link(p):
    return link_from_id(get(p, "itemId"))

def img(p):
    url = get(p, "itemPicUrl")
    return url if url and url != 0 else ""

def safe_text(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ══════════════════════════════════════
# HELPERS — TOP SELLING API (rankingData)
# field ต่างจาก hotTrendData!
# ══════════════════════════════════════

def top_price(p):
    """ราคาจาก priceList[0]["local"] หารด้วย 100 (satang → baht)"""
    price_list = p.get("priceList") or []
    if price_list and isinstance(price_list, list):
        try:
            raw = safe_float(price_list[0].get("local") or 0)
            return raw / 100  # satang → baht
        except:
            pass
    return 0.0


def top_sold(p):
    """ยอดขายในรอบนี้จาก soldCountInfo.periodCurrent"""
    info = p.get("soldCountInfo") or {}
    return safe_int(info.get("periodCurrent") or info.get("total") or 0)


def top_total_sold(p):
    """ยอดขายรวมทั้งหมด"""
    info = p.get("soldCountInfo") or {}
    return safe_int(info.get("total") or 0)


def top_growth(p):
    """growth rate เป็น % เช่น 0.2379 → +23.8%"""
    rate = safe_float(p.get("soldCountGrowthRate") or 0)
    return round(rate * 100, 1)


def top_commission(p):
    """Commission % เช่น 0.15 → 15%"""
    rate = safe_float(p.get("commissionRate") or 0)
    return round(rate * 100, 1) if rate > 0 else None


def top_videos(p):
    """จำนวนคลิปใน 90 วัน"""
    info = p.get("relatedVideoInfo") or {}
    val = info.get("period90d")
    return safe_int(val) if val is not None else None


def top_creators(p):
    """จำนวน Creator ใน 90 วัน"""
    info = p.get("relatedCreatorInfo") or {}
    val = info.get("period90d")
    return safe_int(val) if val is not None else None


def top_img(p):
    url = p.get("itemPicUrl") or ""
    return url if url and url != 0 else ""


def top_link(p):
    return link_from_id(p.get("itemId", ""))


# ══════════════════════════════════════
# ANALYZE — สำหรับ trend items
# ══════════════════════════════════════

def analyze(p):
    s1   = sold_1d(p)
    s3   = sold_3d(p)
    avg3 = s3 / 3 if s3 > 0 else 1
    growth = s1 / avg3
    score  = (s1 * 2) + s3 + (growth * 100)
    return s1, s3, growth, score


# ══════════════════════════════════════
# COLLECT + GROUP — trend items
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
    p = item["p"]
    text = (
        f"{i}. <b>{safe_text(title(p))}</b>\n"
        f"💰 ฿{price(p):,} บาท\n"
        f"📦 1วัน: {item['s1']:,}  |  3วัน: {item['s3']:,}\n"
        f"📈 Growth: x{item['growth']}\n"
    )
    if link(p):
        text += f"\n🛒 <a href=\"{link(p)}\">ดูสินค้าใน TikTok Shop</a>"
    return text


def format_top_item(i, p):
    name     = safe_text((p.get("itemName") or "?")[:45])
    pr       = top_price(p)
    sold     = top_sold(p)
    total    = top_total_sold(p)
    growth   = top_growth(p)
    comm     = top_commission(p)
    videos   = top_videos(p)
    creators = top_creators(p)
    lnk      = top_link(p)
    seller   = safe_text(p.get("sellerName") or "")

    # growth icon
    if growth > 0:
        g_icon = f"📈 +{growth}%"
    elif growth < 0:
        g_icon = f"📉 {growth}%"
    else:
        g_icon = "➡️ ใหม่"

    # commission
    comm_text = f"  💸 {comm}%" if comm else ""

    # videos + creators
    vc_parts = []
    if videos is not None:
        vc_parts.append(f"🎬 {videos} คลิป")
    if creators is not None:
        vc_parts.append(f"👥 {creators} Creator")
    vc_text = "  ".join(vc_parts)

    text = (
        f"{i}. <b>{name}</b>\n"
        f"🏪 {seller}\n"
        f"💰 ฿{pr:,.0f}  📦 ขาย {sold:,} ชิ้น (รวม {total:,})\n"
        f"{g_icon}{comm_text}\n"
    )
    if vc_text:
        text += f"{vc_text}\n"
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
            json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"},
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

    # Header
    send(
        f"📅 {now.strftime('%d/%m/%Y')}  ⏰ {now.strftime('%H:%M')}\n\n"
        f"🔥 <b>TikTok Shop Thailand — Daily Picks</b>"
    )
    time.sleep(1)

    # VIRAL
    if viral:
        send("🚀 <b>VIRAL — เพิ่งระเบิด ทำเลยด่วน!</b>")
        for i, item in enumerate(viral, 1):
            send_item(format_trend_item(i, item), img(item["p"]))
    else:
        send("🚀 <b>VIRAL</b>\nไม่มีสินค้า breakout วันนี้")

    # STABLE
    if stable:
        send("📈 <b>STABLE — กำลังโต ยังทันทำ</b>")
        for i, item in enumerate(stable, 1):
            send_item(format_trend_item(i, item), img(item["p"]))
    else:
        send("📈 <b>STABLE</b>\nไม่มีสินค้า stable วันนี้")

    # PEAK
    if peak:
        send("⚠️ <b>PEAK — ขายดีแต่อิ่มตัวแล้ว</b>")
        for i, item in enumerate(peak, 1):
            send_item(format_trend_item(i, item), img(item["p"]))

    # TOP 5 ขายดีสุด
    if top:
        send("🏆 <b>TOP 5 — ขายดีที่สุดวันนี้</b>")
        for i, p in enumerate(top, 1):
            send_item(format_top_item(i, p), top_img(p))
    else:
        send("🏆 <b>TOP 5</b>\nไม่มีข้อมูลวันนี้")

    print("✅ เสร็จแล้ว")


if __name__ == "__main__":
    main()
