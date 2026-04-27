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
BOT_TOKEN       = os.environ["BOT_TOKEN"]
CHAT_ID         = os.environ["CHAT_ID"]
TABCUT_EMAIL    = os.environ["TABCUT_EMAIL"]
TABCUT_PASSWORD = os.environ["TABCUT_PASSWORD"]

BASE_URL  = "https://www.tabcut.com"
YESTERDAY = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

ZONE_A_COUNT = 5
ZONE_B_COUNT = 10

CATEGORY_MAP = {
    "2":  "💄 บิวตี้",
    "6":  "👗 แฟชั่น",
    "9":  "🍜 อาหาร",
    "12": "🏠 บ้านและสวน",
    "13": "🏥 สุขภาพ",
    "15": "📱 อิเล็กทรอนิกส์",
    "20": "👶 แม่และเด็ก",
    "21": "⚽ กีฬา",
    "27": "🚗 ยานยนต์",
    "28": "👗 เสื้อผ้าผู้หญิง",
    "29": "👔 เสื้อผ้าผู้ชาย",
}

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
            f"{BASE_URL}/api/trpc/user.pubkey?batch=1&input=%7B%7D", timeout=15
        ).json()[0]["result"]["data"]

        if "BEGIN PUBLIC KEY" not in pub_key_raw:
            pub_key_raw = f"-----BEGIN PUBLIC KEY-----\n{pub_key_raw}\n-----END PUBLIC KEY-----"
        cipher = PKCS1_OAEP.new(RSA.importKey(pub_key_raw))
        enc_pw = base64.b64encode(cipher.encrypt(TABCUT_PASSWORD.encode())).decode()

        r = session.post(f"{BASE_URL}/api/auth/callback/email?", data={
            "email": TABCUT_EMAIL, "password": enc_pw,
            "csrfToken": csrf, "callbackUrl": f"{BASE_URL}/workbench",
            "redirect": "false", "json": "true",
        }, timeout=15)

        if r.status_code == 200:
            print("✅ Login สำเร็จ!")
            return True
        print(f"❌ Login ล้มเหลว: {r.status_code}")
        return False
    except Exception as e:
        print(f"❌ Login Error: {e}")
        return False


# ══════════════════════════════════════
# FETCH — Smart Page Detection
# ══════════════════════════════════════

def fetch_trpc(endpoint, input_dict, max_pages=20):
    all_items, seen_ids, empty_count = [], set(), 0
    for page in range(1, max_pages + 1):
        input_dict["pageNo"] = page
        encoded = quote(json.dumps(input_dict, separators=(",", ":")))
        url = f"{BASE_URL}/api/trpc/{endpoint}?input={encoded}"
        try:
            res = session.get(url, timeout=15)
            if res.status_code != 200:
                print(f"  HTTP {res.status_code} หน้า {page}")
                break
            data  = res.json()
            items = (
                data.get("result", {})
                    .get("data", {})
                    .get("result", {})
                    .get("data", [])
            )
            if not items:
                empty_count += 1
                if empty_count >= 2:
                    print(f"  หยุดที่หน้า {page} — ไม่มีข้อมูลเพิ่ม")
                    break
                continue
            new_items = [i for i in items if i.get("itemId") not in seen_ids]
            if not new_items:
                print(f"  หน้า {page}: ซ้ำทั้งหมด หยุด")
                break
            for i in new_items:
                seen_ids.add(i.get("itemId"))
            all_items.extend(new_items)
            print(f"  หน้า {page}: +{len(new_items)} (รวม {len(all_items)})")
            empty_count = 0
            time.sleep(0.3)
        except Exception as e:
            print(f"  Error หน้า {page}: {e}")
            break
    return all_items


def fetch_surge_1d():
    print("ดึง surge_1d...")
    return fetch_trpc("ranking.goods.hotTrendData", {
        "pageSize": 24, "region": "TH",
        "itemCategoryId": "0", "trendFilterType": 1,
    })

def fetch_surge_3d():
    print("ดึง surge_3d...")
    return fetch_trpc("ranking.goods.hotTrendData", {
        "pageSize": 24, "region": "TH",
        "itemCategoryId": "0", "trendFilterType": 2,
    })

def fetch_recommended():
    print("ดึง recommended...")
    return fetch_trpc("ranking.goods.recommendGoodsRanking", {
        "pageSize": 24, "region": "TH",
        "categoryId": "0", "bizDate": YESTERDAY,
        "orderType": "7", "rankType": 1,
    })

def fetch_new_products():
    print("ดึง new products...")
    return fetch_trpc("ranking.goods.newGoodsRanking", {
        "pageSize": 24, "region": "TH",
        "categoryId": "0", "bizDate": YESTERDAY,
        "orderType": "3",
    })


# ══════════════════════════════════════
# HELPERS
# ══════════════════════════════════════

def esc(text):
    return str(text).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def get_field(product, *keys, default="?"):
    for key in keys:
        val = product.get(key)
        if val is not None and val != "":
            return val
    return default

def days_since(s):
    try:
        dt = datetime.fromisoformat(str(s).replace("Z",""))
        return (datetime.now() - dt).days
    except:
        return 999

def get_category(product):
    return CATEGORY_MAP.get(str(get_field(product, "categoryId", default="")), "🛍 อื่นๆ")

def get_velocity(product):
    s1 = int(get_field(product, "soldCount1d", default=0) or 0)
    st = int(get_field(product, "soldCountTotal", default=0) or 0)
    return round((s1/st)*100, 1) if st > 0 and s1 > 0 else 0.0

def get_trend(product):
    """
    เทรนด์ยอดขาย เทียบ 1d vs 3d vs 7d
    ขึ้น = ยอด 1d สูงกว่าค่าเฉลี่ย 7d
    """
    s1 = int(get_field(product, "soldCount1d", default=0) or 0)
    s3 = int(get_field(product, "soldCount3d", default=0) or 0)
    s7 = int(get_field(product, "soldCount7d", default=0) or 0)

    if s1 == 0:
        return "➡️", s1, s3, s7

    avg7 = s7 / 7 if s7 > 0 else 0
    avg3 = s3 / 3 if s3 > 0 else 0

    if avg7 > 0 and s1 >= avg7 * 1.5:
        icon = "🚀"   # พุ่งมาก
    elif avg7 > 0 and s1 >= avg7 * 1.1:
        icon = "📈"   # ขึ้น
    elif avg7 > 0 and s1 <= avg7 * 0.7:
        icon = "📉"   # ลง
    else:
        icon = "➡️"   # ทรงตัว

    return icon, s1, s3, s7

def get_commission(product):
    """Commission rate เป็น %"""
    rate = get_field(product, "commissionRate", default=None)
    if rate is not None and rate != "?":
        try:
            return round(float(rate) * 100, 1)
        except:
            pass
    return None

def get_creator_count(product):
    """จำนวน Creator ที่ขายสินค้านี้"""
    info = product.get("relatedCreatorInfo")
    if isinstance(info, dict):
        return info.get("total", None)
    return None

def get_rmb_price(product):
    """ราคาหยวน — ใช้เทียบต้นทุนจีน"""
    price = get_field(product, "rmbPrice", default=None)
    if price and price != "?":
        try:
            return float(price)
        except:
            pass
    return None

def vel_icon(v):
    if v >= 50: return "🔴"
    if v >= 30: return "🟠"
    if v >= 20: return "🟡"
    if v >= 10: return "🟢"
    return "⚫"

def vel_bar(v):
    if v >= 50: return "🔴🔴🔴🔴🔴"
    if v >= 30: return "🟠🟠🟠🟠⚫"
    if v >= 20: return "🟡🟡🟡⚫⚫"
    if v >= 10: return "🟢🟢⚫⚫⚫"
    return "⚫⚫⚫⚫⚫"

def get_shop_link(product):
    iid = get_field(product, "itemId", default="")
    return f"https://www.tiktok.com/view/product/{iid}" if iid != "?" else ""

def get_image_url(product):
    return get_field(product, "itemPicUrl", "picUrl", "imageUrl", default="")


# ══════════════════════════════════════
# SCORING
# ยอดขายเมื่อวาน  30
# ความใหม่         25
# Velocity         20
# ติดหลาย API    15
# ราคา             10
# ══════════════════════════════════════

def calculate_score(product, source_count):
    score, reasons = 0, []

    sold_1d = int(get_field(product, "soldCount1d", "soldCount", default=0) or 0)
    if sold_1d >= 500:   score += 30; reasons.append(f"ขายเมื่อวาน {sold_1d:,} ชิ้น 🔥")
    elif sold_1d >= 200: score += 22; reasons.append(f"ขายเมื่อวาน {sold_1d:,} ชิ้น 📈")
    elif sold_1d >= 50:  score += 13; reasons.append(f"ขายเมื่อวาน {sold_1d:,} ชิ้น")
    elif sold_1d > 0:    score += 5;  reasons.append(f"ขายเมื่อวาน {sold_1d:,} ชิ้น")

    discover = get_field(product, "discoverTime", "createTime", "onlineTime", default="")
    days = days_since(discover)
    if days <= 3:    score += 25; reasons.append("ใหม่มาก! เพิ่งเข้า 3 วัน 🆕")
    elif days <= 7:  score += 18; reasons.append(f"ใหม่ {days} วัน")
    elif days <= 14: score += 10; reasons.append(f"เข้ามา {days} วัน")
    elif days <= 30: score += 4;  reasons.append(f"เข้ามา {days} วัน")

    v = get_velocity(product)
    if v >= 50:   score += 20; reasons.append(f"Velocity {v}% เพิ่งระเบิดตัว!")
    elif v >= 20: score += 14; reasons.append(f"Velocity {v}% กำลังพุ่ง")
    elif v >= 10: score += 8;  reasons.append(f"Velocity {v}%")
    elif v > 0:   score += 3;  reasons.append(f"Velocity {v}%")

    if source_count >= 3:   score += 15; reasons.append("ติดสัญญาณ 3+ แหล่ง")
    elif source_count == 2: score += 9;  reasons.append("ติดสัญญาณ 2 แหล่ง")
    else:                   score += 3

    price = float(get_field(product, "localPrice", "price", "salePrice", default=0) or 0)
    if 50 <= price <= 500: score += 10; reasons.append(f"ราคา {price:.0f} บาท ขายง่าย")
    elif 0 < price < 50:  score += 6;  reasons.append(f"ราคา {price:.0f} บาท ถูกมาก")
    elif price > 500:      score += 3;  reasons.append(f"ราคา {price:.0f} บาท สูงหน่อย")

    return min(score, 100), reasons


# ══════════════════════════════════════
# COLLECT + RANK
# ══════════════════════════════════════

def collect_all_products():
    print("กำลังดึงข้อมูล...")
    sources = {
        "surge_1d":    fetch_surge_1d(),
        "surge_3d":    fetch_surge_3d(),
        "recommended": fetch_recommended(),
        "new":         fetch_new_products(),
    }
    for name, items in sources.items():
        print(f"{name}: {len(items)} ตัว")

    item_map, item_count = {}, {}
    for source_name, items in sources.items():
        for item in items:
            iid = item.get("itemId")
            if not iid: continue
            if iid not in item_map:
                item_map[iid]   = item
                item_count[iid] = 0
            item_count[iid] += 1

    print(f"รวม unique: {len(item_map)} ตัว")

    scored = []
    for iid, product in item_map.items():
        score, reasons = calculate_score(product, item_count[iid])
        trend_icon, s1, s3, s7 = get_trend(product)
        scored.append({
            "product":       product,
            "score":         score,
            "reasons":       reasons,
            "velocity":      get_velocity(product),
            "category":      get_category(product),
            "image_url":     get_image_url(product),
            "shop_link":     get_shop_link(product),
            "commission":    get_commission(product),
            "creator_count": get_creator_count(product),
            "rmb_price":     get_rmb_price(product),
            "trend_icon":    trend_icon,
            "sold_1d":       s1,
            "sold_3d":       s3,
            "sold_7d":       s7,
        })

    scored = [
        x for x in scored
        if get_field(x["product"], "itemTitle", "title", "name", "goodsName") != "?" and
           float(get_field(x["product"], "localPrice", "price", "salePrice", default=0) or 0) > 0
    ]
    scored.sort(key=lambda x: x["score"], reverse=True)
    print(f"ผ่านกรอง: {len(scored)} ตัว")
    return scored


def split_zones(scored):
    za = scored[:ZONE_A_COUNT]
    zb = scored[ZONE_A_COUNT:ZONE_A_COUNT + ZONE_B_COUNT]
    print(f"Zone A: {len(za)}  Zone B: {len(zb)}")
    return za, zb


# ══════════════════════════════════════
# FORMAT
# ══════════════════════════════════════

def fmt_zone_a_header(today_str):
    return (
        "🟢 <b>ทำเลยวันนี้! Top 5 ปักตะกร้า</b>\n"
        f"📅 {today_str}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Velocity = % ขายเมื่อวาน/ยอดรวม | สูง=เพิ่งระเบิด!</i>"
    )

def fmt_photo_caption(rank, item):
    p            = item["product"]
    score        = item["score"]
    reasons      = item["reasons"]
    cat          = item["category"]
    v            = item["velocity"]
    link         = item["shop_link"]
    commission   = item["commission"]
    creator_cnt  = item["creator_count"]
    rmb          = item["rmb_price"]
    trend_icon   = item["trend_icon"]
    s1           = item["sold_1d"]
    s3           = item["sold_3d"]
    s7           = item["sold_7d"]
    title        = esc(get_field(p, "itemTitle", "title", "name", "goodsName")[:45])
    price        = float(get_field(p, "localPrice", "price", "salePrice", default=0) or 0)
    total        = int(get_field(p, "soldCountTotal", "totalSold", "soldCount", default=0) or 0)

    lines = [
        f"{rank}. <b>{title}</b>",
        f"{cat}",
        f"💰 ฿{price:.0f}  📦 รวม {total:,}",
    ]

    # เทรนด์ 1d/3d/7d
    trend_line = f"📊 {trend_icon} 1วัน:{s1:,}"
    if s3 > 0: trend_line += f"  3วัน:{s3:,}"
    if s7 > 0: trend_line += f"  7วัน:{s7:,}"
    lines.append(trend_line)

    lines.append(f"⚡ {vel_bar(v)} {v}%")
    lines.append(f"🎯 Score: {score}/100")

    # Commission
    if commission is not None:
        lines.append(f"💸 Commission: {commission}%")

    # Creator Count
    if creator_cnt is not None:
        if creator_cnt <= 5:
            lines.append(f"👥 Creator: {creator_cnt} คน 🟢 คู่แข่งน้อย!")
        elif creator_cnt <= 20:
            lines.append(f"👥 Creator: {creator_cnt} คน 🟡 เริ่มมีคู่แข่ง")
        else:
            lines.append(f"👥 Creator: {creator_cnt} คน 🔴 คู่แข่งเยอะแล้ว")

    # ราคาหยวน
    if rmb is not None:
        lines.append(f"🇨🇳 ราคาจีน: ¥{rmb:.2f}")

    for r in reasons[:2]:
        lines.append(f"• {esc(r)}")

    if link:
        lines.append(f"\n🛒 <a href=\"{link}\">ดูสินค้าใน TikTok Shop</a>")

    return "\n".join(lines)


def fmt_product_short(rank, item):
    p           = item["product"]
    score       = item["score"]
    cat         = item["category"]
    v           = item["velocity"]
    link        = item["shop_link"]
    commission  = item["commission"]
    creator_cnt = item["creator_count"]
    trend_icon  = item["trend_icon"]
    title       = esc(get_field(p, "itemTitle", "title", "name", "goodsName")[:28])
    price       = float(get_field(p, "localPrice", "price", "salePrice", default=0) or 0)
    sold_1d     = int(get_field(p, "soldCount1d", "soldCount", default=0) or 0)

    comm_text    = f"  💸{commission}%" if commission is not None else ""
    creator_text = f"  👥{creator_cnt}" if creator_cnt is not None else ""
    link_text    = f"\n   🛒 <a href=\"{link}\">TikTok Shop</a>" if link else ""

    return (
        f"\n{rank}. {title}\n"
        f"   {cat}  ฿{price:.0f}  {trend_icon}{sold_1d:,}  "
        f"{vel_icon(v)}{v}%{comm_text}{creator_text}  [{score}]"
        f"{link_text}"
    )


def build_message2(zone_b):
    lines = [
        "🟡 <b>Zone B — ยังทันถ้ารีบ (อันดับ 6-15)</b>",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    if zone_b:
        for i, item in enumerate(zone_b, 1):
            lines.append(fmt_product_short(i, item))
    else:
        lines.append("ไม่มีสินค้าวันนี้")
    lines += [
        "\n━━━━━━━━━━━━━━━━━━━━",
        "🔴>=50%  🟠>=30%  🟡>=20%  🟢>=10%  ⚫<10%",
        "💸=Commission  👥=จำนวน Creator",
        "🔄 อัพเดทอัตโนมัติทุก 09:00 น.",
    ]
    return "\n".join(lines)


# ══════════════════════════════════════
# SEND TELEGRAM
# ══════════════════════════════════════

def html_to_plain(text):
    text = re.sub(r'<a href="([^"]+)">([^<]+)</a>', r'\2: \1', text)
    return re.sub(r'<[^>]+>', '', text)

def send_message(text):
    url    = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    chunks = [text[i:i+3500] for i in range(0, len(text), 3500)]
    for idx, chunk in enumerate(chunks):
        try:
            r = requests.post(url, json={
                "chat_id": CHAT_ID, "text": chunk, "parse_mode": "HTML",
            }, timeout=15)
            print(f"  msg {idx+1}: {r.status_code}")
            if r.status_code != 200:
                r2 = requests.post(url, json={
                    "chat_id": CHAT_ID, "text": html_to_plain(chunk),
                }, timeout=15)
                print(f"  plain: {r2.status_code}")
        except Exception as e:
            print(f"  Exception: {e}")
        time.sleep(1)

def send_photo(image_url, caption):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    try:
        r = requests.post(url, json={
            "chat_id": CHAT_ID, "photo": image_url,
            "caption": caption[:1024], "parse_mode": "HTML",
        }, timeout=15)
        print(f"  photo: {r.status_code}")
        if r.status_code != 200:
            send_message(caption)
    except Exception as e:
        print(f"  Photo error: {e}")
        send_message(caption)


# ══════════════════════════════════════
# MAIN
# ══════════════════════════════════════

def main():
    login()

    scored = collect_all_products()
    if not scored:
        send_message("⚠️ ดึงข้อมูลไม่ได้วันนี้ ลองใหม่พรุ่งนี้")
        return

    zone_a, zone_b = split_zones(scored)
    today_str = datetime.now().strftime("%d/%m/%Y")

    print("ส่ง Zone A header...")
    send_message(fmt_zone_a_header(today_str))
    time.sleep(2)

    for i, item in enumerate(zone_a, 1):
        print(f"ส่ง Zone A อันดับ {i}...")
        img = item["image_url"]
        cap = fmt_photo_caption(i, item)
        if img and img != "?":
            send_photo(img, cap)
        else:
            send_message(cap)
        time.sleep(2)

    print("ส่ง Zone B...")
    time.sleep(2)
    send_message(build_message2(zone_b))
    print("✅ เสร็จแล้ว")


if __name__ == "__main__":
    main()
