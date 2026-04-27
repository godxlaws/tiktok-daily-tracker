import requests
import os
import json
import re
import time
import base64
from datetime import datetime, timedelta
from urllib.parse import quote
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP

# ══════════════════════════════════════
# CONFIG
# ══════════════════════════════════════

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
TABCUT_EMAIL = os.environ["TABCUT_EMAIL"]
TABCUT_PASSWORD = os.environ["TABCUT_PASSWORD"]

BASE_URL = "https://www.tabcut.com"

ZONE_A_COUNT = 5
ZONE_B_COUNT = 5

# ใช้ map ให้ตรงกับข้อมูล Tabcut มากขึ้น
CATEGORY_MAP = {
    "2": "💄 บิวตี้",
    "6": "💍 แฟชั่น/เครื่องประดับ",
    "7": "🍜 อาหาร",
    "9": "🍜 อาหาร",
    "12": "🏠 บ้านและของใช้",
    "13": "🏥 สุขภาพ",
    "15": "👶 เด็ก/แฟชั่นเด็ก",
    "17": "👜 กระเป๋า",
    "20": "🐶 สัตว์เลี้ยง",
    "21": "📱 มือถือ/ดิจิทัล",
    "22": "👟 รองเท้า",
    "23": "⚽ กีฬา/เอาท์ดอร์",
    "26": "🧸 ของเล่น/งานอดิเรก",
    "27": "🏍 ยานยนต์/มอเตอร์ไซค์",
    "28": "👗 เสื้อผ้าผู้หญิง",
    "29": "👔 เสื้อผ้าผู้ชาย",
    "10000": "🛍 อื่นๆ",
}

# คำที่ควรระวัง ไม่ได้ห้ามขายเสมอไป แต่ไม่ควรดันขึ้น Zone A ง่ายๆ
RISKY_KEYWORDS = [
    "ลดน้ำหนัก",
    "ผอม",
    "ขาว",
    "รักษา",
    "แก้ปวด",
    "สิวหาย",
    "ฝ้า",
    "กระ",
    "ศีรษะล้าน",
    "ปลูกผม",
    "ยา",
    "อาหารเสริม",
    "fda",
    "ของแท้",
    "casio",
]

# ══════════════════════════════════════
# SESSION
# ══════════════════════════════════════

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/147.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": f"{BASE_URL}/workbench",
})

# ══════════════════════════════════════
# LOGIN
# ══════════════════════════════════════

def login():
    print("กำลัง Login Tabcut...")
    try:
        csrf = session.get(f"{BASE_URL}/api/auth/csrf", timeout=15).json().get("csrfToken")

        pub_key_raw = session.get(
            f"{BASE_URL}/api/trpc/user.pubkey?batch=1&input=%7B%7D",
            timeout=15
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
            timeout=15
        )

        if r.status_code == 200:
            print("✅ Login สำเร็จ!")
            return True

        print(f"❌ Login ล้มเหลว: {r.status_code}")
        print(r.text[:300])
        return False

    except Exception as e:
        print(f"❌ Login Error: {e}")
        return False

# ══════════════════════════════════════
# FETCH
# ══════════════════════════════════════

def fetch_trpc(endpoint, input_dict, max_pages=1):
    """
    ฟรีดูได้หน้าแรกหน้าเดียว จึงตั้ง max_pages=1 เป็น default
    ถ้าวันหลัง account ดูหลายหน้าได้ ค่อยเพิ่ม max_pages
    """
    all_items = []
    seen_ids = set()

    for page in range(1, max_pages + 1):
        input_dict["pageNo"] = page
        encoded = quote(json.dumps(input_dict, separators=(",", ":")))
        url = f"{BASE_URL}/api/trpc/{endpoint}?input={encoded}"

        try:
            res = session.get(url, timeout=15)

            if res.status_code != 200:
                print(f"HTTP {res.status_code} หน้า {page}")
                print(res.text[:300])
                break

            data = res.json()

            items = (
                data.get("result", {})
                    .get("data", {})
                    .get("result", {})
                    .get("data", [])
            )

            if not items:
                print(f"หน้า {page}: ไม่มีข้อมูล")
                break

            new_items = []
            for item in items:
                iid = item.get("itemId")
                if iid and iid not in seen_ids:
                    seen_ids.add(iid)
                    new_items.append(item)

            all_items.extend(new_items)
            print(f"หน้า {page}: +{len(new_items)} ตัว")

            time.sleep(0.3)

        except Exception as e:
            print(f"Error หน้า {page}: {e}")
            break

    return all_items


def fetch_yesterday_surge():
    print("ดึง Yesterday surge list...")
    return fetch_trpc(
        "ranking.goods.hotTrendData",
        {
            "pageSize": 24,
            "region": "TH",
            "itemCategoryId": "0",
            "trendFilterType": 1,
        },
        max_pages=1
    )

# ══════════════════════════════════════
# HELPERS
# ══════════════════════════════════════

def esc(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def get_field(product, *keys, default="?"):
    for key in keys:
        val = product.get(key)
        if val is not None and val != "":
            return val
    return default


def safe_int(value, default=0):
    try:
        if value is None or value == "?":
            return default
        return int(float(value))
    except:
        return default


def safe_float(value, default=0.0):
    try:
        if value is None or value == "?":
            return default
        return float(value)
    except:
        return default


def days_since(s):
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", ""))
        return (datetime.now() - dt).days
    except:
        return 999


def get_category(product):
    cid = str(get_field(product, "categoryId", default=""))
    return CATEGORY_MAP.get(cid, "🛍 อื่นๆ")


def get_title(product, limit=45):
    title = get_field(product, "itemTitle", "title", "name", "goodsName", default="?")
    title = str(title).strip()
    if len(title) > limit:
        title = title[:limit] + "..."
    return title


def get_price(product):
    return safe_float(get_field(product, "localPrice", "price", "salePrice", default=0), 0)


def get_total_sold(product):
    return safe_int(get_field(product, "soldCountTotal", "totalSold", "soldCount", default=0), 0)


def get_sold_1d(product):
    return safe_int(get_field(product, "soldCount1d", default=0), 0)


def get_sold_3d(product):
    return safe_int(get_field(product, "soldCount3d", default=0), 0)


def get_sold_7d(product):
    return safe_int(get_field(product, "soldCount7d", default=0), 0)


def get_velocity(product):
    sold_1d = get_sold_1d(product)
    total = get_total_sold(product)

    if sold_1d > 0 and total > 0:
        return round((sold_1d / total) * 100, 1)

    return 0.0


def get_trend_icon(product):
    sold_1d = get_sold_1d(product)
    sold_7d = get_sold_7d(product)

    if sold_1d <= 0:
        return "➡️"

    avg7 = sold_7d / 7 if sold_7d > 0 else 0

    if avg7 > 0 and sold_1d >= avg7 * 1.5:
        return "🚀"
    if avg7 > 0 and sold_1d >= avg7 * 1.1:
        return "📈"
    if avg7 > 0 and sold_1d <= avg7 * 0.7:
        return "📉"

    # ถ้าไม่มี 7d ใช้ velocity แทน
    v = get_velocity(product)
    if v >= 30:
        return "🚀"
    if v >= 15:
        return "📈"

    return "➡️"


def vel_bar(v):
    if v >= 50:
        return "🔴🔴🔴🔴🔴"
    if v >= 30:
        return "🟠🟠🟠🟠⚫"
    if v >= 20:
        return "🟡🟡🟡⚫⚫"
    if v >= 10:
        return "🟢🟢⚫⚫⚫"
    return "⚫⚫⚫⚫⚫"


def get_shop_link(product):
    iid = get_field(product, "itemId", default="")
    if iid and iid != "?":
        return f"https://www.tiktok.com/view/product/{iid}"
    return ""


def get_image_url(product):
    return get_field(product, "itemPicUrl", "picUrl", "imageUrl", default="")


def get_commission(product):
    rate = get_field(product, "commissionRate", default=None)
    if rate is None or rate == "?":
        return None

    try:
        rate = float(rate)

        # บาง API ส่งมาเป็น 0.15 บางที่อาจส่ง 15
        if rate <= 1:
            return round(rate * 100, 1)
        return round(rate, 1)

    except:
        return None


def get_creator_count(product):
    info = product.get("relatedCreatorInfo")
    if isinstance(info, dict):
        return info.get("total", None)
    return None


def has_risky_keyword(product):
    title = str(get_field(product, "itemTitle", "title", "name", "goodsName", default="")).lower()
    for kw in RISKY_KEYWORDS:
        if kw.lower() in title:
            return True
    return False


def is_valid_product(product):
    title = get_title(product, limit=120)
    price = get_price(product)
    sold_1d = get_sold_1d(product)
    total = get_total_sold(product)

    # ไม่มีชื่อ
    if not title or title == "?":
        return False

    # ราคาเพี้ยนมาก
    if price <= 1:
        return False

    # ไม่มีแรงขายเมื่อวาน
    if sold_1d <= 0:
        return False

    # ยอดรวมไม่มีเลย แปลก
    if total <= 0:
        return False

    return True

# ══════════════════════════════════════
# SCORING
# ══════════════════════════════════════

def calculate_score(product):
    """
    ใช้กับ Yesterday surge อย่างเดียว
    เน้นหาของที่เพิ่งพุ่ง ไม่ใช่ของที่ขายดีมานานแล้ว
    """
    score = 0
    reasons = []

    sold_1d = get_sold_1d(product)
    total = get_total_sold(product)
    price = get_price(product)
    velocity = get_velocity(product)
    days = days_since(get_field(product, "discoverTime", "createTime", "onlineTime", default=""))

    # 1) ยอดขายเมื่อวาน
    if sold_1d >= 1000:
        score += 35
        reasons.append(f"เมื่อวานขาย {sold_1d:,} ชิ้น 🔥")
    elif sold_1d >= 500:
        score += 30
        reasons.append(f"เมื่อวานขาย {sold_1d:,} ชิ้น 🔥")
    elif sold_1d >= 200:
        score += 24
        reasons.append(f"เมื่อวานขาย {sold_1d:,} ชิ้น 📈")
    elif sold_1d >= 100:
        score += 18
        reasons.append(f"เมื่อวานขาย {sold_1d:,} ชิ้น")
    elif sold_1d >= 50:
        score += 12
        reasons.append(f"เมื่อวานขาย {sold_1d:,} ชิ้น")
    else:
        score += 5
        reasons.append(f"เมื่อวานขาย {sold_1d:,} ชิ้น")

    # 2) Velocity = ยอดเมื่อวาน / ยอดรวม
    if velocity >= 50:
        score += 30
        reasons.append(f"Velocity {velocity}% เพิ่งระเบิดมาก")
    elif velocity >= 30:
        score += 25
        reasons.append(f"Velocity {velocity}% พุ่งแรง")
    elif velocity >= 20:
        score += 20
        reasons.append(f"Velocity {velocity}% กำลังมา")
    elif velocity >= 10:
        score += 12
        reasons.append(f"Velocity {velocity}% มีแรงซื้อใหม่")
    elif velocity > 0:
        score += 5
        reasons.append(f"Velocity {velocity}%")

    # 3) ความใหม่
    if days <= 3:
        score += 20
        reasons.append("สินค้าใหม่มาก ไม่เกิน 3 วัน 🆕")
    elif days <= 7:
        score += 16
        reasons.append(f"สินค้าใหม่ {days} วัน")
    elif days <= 14:
        score += 12
        reasons.append(f"เพิ่งเข้า {days} วัน")
    elif days <= 30:
        score += 8
        reasons.append(f"เข้า {days} วัน")
    elif days <= 60:
        score += 4
        reasons.append(f"เข้า {days} วัน")
    else:
        # ของเก่าไม่ใช่แย่ แต่ต้องไม่ให้ขึ้นง่ายเกินไป
        if velocity >= 30:
            score += 5
            reasons.append("สินค้าเก่าแต่กลับมาพุ่งแรง")
        else:
            reasons.append("สินค้าเก่า ต้องเช็คคู่แข่งก่อน")

    # 4) ราคา
    if 50 <= price <= 399:
        score += 10
        reasons.append(f"ราคา ฿{price:.0f} ขายง่าย")
    elif 400 <= price <= 700:
        score += 6
        reasons.append(f"ราคา ฿{price:.0f} ต้องมี demo ชัด")
    elif 10 <= price < 50:
        score += 5
        reasons.append(f"ราคา ฿{price:.0f} ถูกมาก")
    elif price > 700:
        score += 2
        reasons.append(f"ราคา ฿{price:.0f} สูง ต้องเช็คคอม")
    else:
        score -= 10
        reasons.append("ราคาแปลก ต้องระวัง")

    # 5) ลดคะแนนของเสี่ยง
    if has_risky_keyword(product):
        score -= 12
        reasons.append("มีคำเสี่ยง/แบรนด์/เคลม ต้องระวัง")

    return max(0, min(score, 100)), reasons

# ══════════════════════════════════════
# ACTION
# ══════════════════════════════════════

def get_action(item):
    """
    ทุกสินค้าต้องมี Action ของตัวเอง
    """
    p = item["product"]
    score = item["score"]
    v = item["velocity"]
    sold_1d = item["sold_1d"]
    price = get_price(p)
    days = item["days"]
    risky = has_risky_keyword(p)

    if risky:
        return (
            "🟡 เช็คก่อนทำ",
            "มีคำ/หมวดที่เสี่ยง ต้องเช็ค policy, รีวิว, ร้าน และอย่าเคลมแรง"
        )

    if score >= 75 and sold_1d >= 100 and v >= 20 and 30 <= price <= 500:
        return (
            "🟢 ทำคลิปเลย",
            "สัญญาณแรงพอ ยอดเมื่อวานดี ราคาเหมาะ ทำ demo/ปัญหา-ทางแก้วันนี้"
        )

    if v >= 30 and sold_1d >= 50:
        return (
            "🟢 ทำคลิปเลย",
            "Velocity สูง แปลว่ามีแรงซื้อใหม่ เหมาะรีบทำก่อนคู่แข่งเยอะ"
        )

    if sold_1d >= 500 and v < 10:
        return (
            "🟡 เช็คคู่แข่งก่อน",
            "ขายเยอะจริง แต่ยอดรวมสูง อาจเป็นของที่คนทำเยอะแล้ว"
        )

    if days > 180 and v < 20:
        return (
            "🟡 ทำได้ถ้ามีมุมใหม่",
            "สินค้าเก่า ต้องหา angle ใหม่ เช่น เทียบก่อน-หลัง, วิธีใช้, ข้อผิดพลาด"
        )

    if price > 700:
        return (
            "🟡 เช็คคอม/ร้านก่อน",
            "ราคาสูง ต้องดูคอมมิชชัน รีวิว และความน่าเชื่อถือก่อนลงแรง"
        )

    if sold_1d < 100 and v >= 20:
        return (
            "🟡 เช็คก่อนทำ",
            "เปอร์เซ็นต์พุ่งดี แต่ยอดยังไม่มาก เช็คคลิปใน TikTok ก่อน"
        )

    return (
        "🟡 เช็คก่อนทำ",
        "มีสัญญาณดี แต่ควรเช็คจำนวนคลิปคู่แข่งและคอมมิชชันก่อน"
    )

# ══════════════════════════════════════
# COLLECT + RANK
# ══════════════════════════════════════

def collect_products():
    print("กำลังดึงข้อมูล Yesterday surge...")
    items = fetch_yesterday_surge()
    print(f"ดึงได้ทั้งหมด: {len(items)} ตัว")

    scored = []

    for product in items:
        if not is_valid_product(product):
            continue

        score, reasons = calculate_score(product)
        days = days_since(get_field(product, "discoverTime", "createTime", "onlineTime", default=""))

        item = {
            "product": product,
            "score": score,
            "reasons": reasons,
            "velocity": get_velocity(product),
            "category": get_category(product),
            "image_url": get_image_url(product),
            "shop_link": get_shop_link(product),
            "commission": get_commission(product),
            "creator_count": get_creator_count(product),
            "trend_icon": get_trend_icon(product),
            "sold_1d": get_sold_1d(product),
            "sold_3d": get_sold_3d(product),
            "sold_7d": get_sold_7d(product),
            "days": days,
        }

        action_title, action_reason = get_action(item)
        item["action_title"] = action_title
        item["action_reason"] = action_reason

        scored.append(item)

    scored.sort(key=lambda x: x["score"], reverse=True)

    print(f"ผ่านกรอง: {len(scored)} ตัว")
    return scored


def split_zones(scored):
    """
    Zone A = ทำเลยวันนี้
    Zone B = เช็คก่อนทำ แต่ยังน่าสนใจ

    ไม่มี Zone C ใน report
    """
    zone_a = []

    for item in scored:
        if len(zone_a) >= ZONE_A_COUNT:
            break

        p = item["product"]
        price = get_price(p)

        # เงื่อนไข Zone A ต้องค่อนข้างชัด
        if (
            item["score"] >= 65
            and item["sold_1d"] >= 80
            and item["velocity"] >= 10
            and 10 <= price <= 700
            and not has_risky_keyword(p)
        ):
            zone_a.append(item)

    # ถ้าเงื่อนไขเข้มไปจนไม่ครบ ให้เอา top score มาเติม
    used_ids = set(x["product"].get("itemId") for x in zone_a)

    for item in scored:
        if len(zone_a) >= ZONE_A_COUNT:
            break

        iid = item["product"].get("itemId")
        if iid not in used_ids and not has_risky_keyword(item["product"]):
            zone_a.append(item)
            used_ids.add(iid)

    # Zone B เอาตัวที่เหลือที่ยังน่าเช็ค
    zone_b_candidates = []
    for item in scored:
        iid = item["product"].get("itemId")
        if iid in used_ids:
            continue

        if item["score"] >= 45 or item["velocity"] >= 15 or item["sold_1d"] >= 100:
            zone_b_candidates.append(item)

    # เรียง Zone B โดยเน้น velocity ก่อน แล้วค่อย score
    zone_b_candidates.sort(key=lambda x: (x["velocity"], x["score"]), reverse=True)
    zone_b = zone_b_candidates[:ZONE_B_COUNT]

    print(f"Zone A: {len(zone_a)} ตัว")
    print(f"Zone B: {len(zone_b)} ตัว")

    return zone_a, zone_b

# ══════════════════════════════════════
# FORMAT
# ══════════════════════════════════════

def fmt_main_header(today_str):
    return (
        "📌 <b>Daily TikTok Shop Radar</b>\n"
        f"📅 {today_str}\n"
        "ใช้ข้อมูล: Yesterday surge list\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Velocity = ยอดขายเมื่อวาน / ยอดขายรวม</i>"
    )


def fmt_zone_header(zone_name, description):
    return (
        f"{zone_name}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>{description}</i>"
    )


def fmt_photo_caption(rank, item, zone_label):
    p = item["product"]

    title = esc(get_title(p, limit=42))
    cat = item["category"]
    price = get_price(p)
    total = get_total_sold(p)
    score = item["score"]
    reasons = item["reasons"]
    v = item["velocity"]
    link = item["shop_link"]
    commission = item["commission"]
    creator_cnt = item["creator_count"]
    trend_icon = item["trend_icon"]
    sold_1d = item["sold_1d"]
    sold_3d = item["sold_3d"]
    sold_7d = item["sold_7d"]
    days = item["days"]
    action_title = item["action_title"]
    action_reason = item["action_reason"]

    lines = [
        f"{zone_label}",
        f"{rank}. <b>{title}</b>",
        f"{cat}",
        f"💰 ฿{price:.0f}  📦 รวม {total:,}",
    ]

    trend_line = f"📊 {trend_icon} เมื่อวาน:{sold_1d:,}"
    if sold_3d > 0:
        trend_line += f"  3วัน:{sold_3d:,}"
    if sold_7d > 0:
        trend_line += f"  7วัน:{sold_7d:,}"
    lines.append(trend_line)

    lines.append(f"⚡ {vel_bar(v)} {v}%")
    lines.append(f"🎯 Score: {score}/100")

    if days <= 365:
        lines.append(f"🆕 เจอสินค้าเมื่อ {days} วันก่อน")
    else:
        lines.append("🕒 สินค้าเก่า/ไม่รู้วันเข้า")

    if commission is not None:
        lines.append(f"💸 Commission: {commission}%")

    if creator_cnt is not None:
        if creator_cnt <= 5:
            lines.append(f"👥 Creator: {creator_cnt} คน 🟢 คู่แข่งน้อย")
        elif creator_cnt <= 20:
            lines.append(f"👥 Creator: {creator_cnt} คน 🟡 เริ่มมีคู่แข่ง")
        else:
            lines.append(f"👥 Creator: {creator_cnt} คน 🔴 คู่แข่งเยอะ")

    # เหตุผลสั้นๆ เอาแค่ 1-2 บรรทัดพอ ไม่ให้ caption เกิน 1024
    for r in reasons[:2]:
        lines.append(f"• {esc(r)}")

    # สำคัญ: ทุกสินค้ามี Action ของตัวเอง
    lines += [
        "",
        f"🧠 <b>Action: {esc(action_title)}</b>",
        f"• {esc(action_reason)}",
    ]

    if link:
        lines.append(f"\n🛒 <a href=\"{link}\">ดูสินค้าใน TikTok Shop</a>")

    return "\n".join(lines)


def html_to_plain(text):
    text = re.sub(r'<a href="([^"]+)">([^<]+)</a>', r'\2: \1', text)
    return re.sub(r'<[^>]+>', '', text)

# ══════════════════════════════════════
# SEND TELEGRAM
# ══════════════════════════════════════

def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    chunks = [text[i:i+3500] for i in range(0, len(text), 3500)]

    for idx, chunk in enumerate(chunks):
        try:
            r = requests.post(
                url,
                json={
                    "chat_id": CHAT_ID,
                    "text": chunk,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=15
            )

            print(f"msg {idx + 1}: {r.status_code}")

            if r.status_code != 200:
                print(r.text[:300])
                r2 = requests.post(
                    url,
                    json={
                        "chat_id": CHAT_ID,
                        "text": html_to_plain(chunk),
                        "disable_web_page_preview": True,
                    },
                    timeout=15
                )
                print(f"plain: {r2.status_code}")

        except Exception as e:
            print(f"Exception send_message: {e}")

        time.sleep(1)


def send_photo(image_url, caption):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"

    # Telegram photo caption จำกัด 1024 ตัวอักษร
    caption = caption[:1000]

    try:
        r = requests.post(
            url,
            json={
                "chat_id": CHAT_ID,
                "photo": image_url,
                "caption": caption,
                "parse_mode": "HTML",
            },
            timeout=15
        )

        print(f"photo: {r.status_code}")

        if r.status_code != 200:
            print(r.text[:300])
            send_message(caption)

    except Exception as e:
        print(f"Photo error: {e}")
        send_message(caption)

# ══════════════════════════════════════
# MAIN
# ══════════════════════════════════════

def send_zone_items(zone_items, zone_label):
    for i, item in enumerate(zone_items, 1):
        print(f"ส่ง {zone_label} อันดับ {i}...")

        img = item["image_url"]
        cap = fmt_photo_caption(i, item, zone_label)

        if img and img != "?":
            send_photo(img, cap)
        else:
            send_message(cap)

        time.sleep(2)


def main():
    ok = login()

    if not ok:
        send_message("⚠️ Login Tabcut ไม่สำเร็จ วันนี้ดึง report ไม่ได้")
        return

    scored = collect_products()

    if not scored:
        send_message("⚠️ วันนี้ไม่มีสินค้าที่ผ่านเกณฑ์จาก Yesterday surge")
        return

    zone_a, zone_b = split_zones(scored)

    today_str = datetime.now().strftime("%d/%m/%Y")

    print("ส่ง header...")
    send_message(fmt_main_header(today_str))
    time.sleep(2)

    if zone_a:
        print("ส่ง Zone A header...")
        send_message(fmt_zone_header(
            "🟢 <b>Zone A — ทำเลยวันนี้</b>",
            "สินค้าที่สัญญาณแรง เหมาะหยิบไปทำคลิปก่อน"
        ))
        time.sleep(2)

        send_zone_items(zone_a, "🟢 <b>Zone A — ทำเลยวันนี้</b>")
    else:
        send_message("🟢 <b>Zone A — ทำเลยวันนี้</b>\nวันนี้ยังไม่มีตัวที่เข้าเกณฑ์ชัด")

    time.sleep(2)

    if zone_b:
        print("ส่ง Zone B header...")
        send_message(fmt_zone_header(
            "🟡 <b>Zone B — เช็คก่อนทำ</b>",
            "มีสัญญาณดี แต่ควรเช็คคลิปคู่แข่ง/คอมมิชชัน/ร้านก่อนลงแรง"
        ))
        time.sleep(2)

        send_zone_items(zone_b, "🟡 <b>Zone B — เช็คก่อนทำ</b>")
    else:
        send_message("🟡 <b>Zone B — เช็คก่อนทำ</b>\nวันนี้ไม่มีตัวสำรองที่น่าสนใจ")

    print("✅ ส่ง report เสร็จแล้ว")


if __name__ == "__main__":
    main()
