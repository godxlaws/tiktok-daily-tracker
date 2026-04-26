import requests
import os
import json
import time
from datetime import datetime, timedelta
from urllib.parse import quote

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID   = os.environ["CHAT_ID"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120.0.0.0",
    "Referer": "https://www.tabcut.com/",
    "Accept": "application/json",
}

TODAY     = datetime.now().strftime("%Y%m%d")
YESTERDAY = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

ZONE_A_COUNT = 5
ZONE_B_COUNT = 10  # ลดจาก 15 → 10

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
# FETCH
# ══════════════════════════════════════

def fetch_trpc(endpoint, input_dict, pages=20):
    all_items = []
    for page in range(1, pages + 1):
        input_dict["pageNo"] = page
        encoded = quote(json.dumps(input_dict, ensure_ascii=False))
        url = f"https://www.tabcut.com/api/trpc/{endpoint}?input={encoded}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                print(f"  HTTP {r.status_code} at page {page}")
                break
            data = r.json()
            items = (
                data.get("result", {})
                    .get("data", {})
                    .get("result", {})
                    .get("data", [])
            )
            if not items:
                print(f"  หมดข้อมูลที่ page {page}")
                break
            all_items.extend(items)
            time.sleep(0.3)
        except Exception as e:
            print(f"  Error page {page}: {e}")
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

def get_field(product, *keys, default="?"):
    for key in keys:
        val = product.get(key)
        if val is not None and val != "":
            return val
    return default

def days_since(discover_time_str):
    try:
        dt = datetime.fromisoformat(str(discover_time_str).replace("Z", ""))
        return (datetime.now() - dt).days
    except:
        return 999

def get_category(product):
    cat_id = str(get_field(product, "categoryId", default=""))
    return CATEGORY_MAP.get(cat_id, "🛍 อื่นๆ")

def get_velocity(product):
    sold_1d    = int(get_field(product, "soldCount1d", default=0) or 0)
    sold_total = int(get_field(product, "soldCountTotal", default=0) or 0)
    if sold_total > 0 and sold_1d > 0:
        return round((sold_1d / sold_total) * 100, 1)
    return 0.0

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


# ══════════════════════════════════════
# SCORING (รวมสูงสุด 100)
# ยอดขายเมื่อวาน  30
# ความใหม่         25
# Velocity         20
# ติดหลาย API    15
# ราคา             10
# ══════════════════════════════════════

def calculate_score(product, source_count):
    score = 0
    reasons = []

    sold_1d = int(get_field(product, "soldCount1d", "soldCount", default=0) or 0)
    if sold_1d >= 500:
        score += 30
        reasons.append(f"ขายเมื่อวาน {sold_1d:,} ชิ้น 🔥")
    elif sold_1d >= 200:
        score += 22
        reasons.append(f"ขายเมื่อวาน {sold_1d:,} ชิ้น 📈")
    elif sold_1d >= 50:
        score += 13
        reasons.append(f"ขายเมื่อวาน {sold_1d:,} ชิ้น")
    elif sold_1d > 0:
        score += 5
        reasons.append(f"ขายเมื่อวาน {sold_1d:,} ชิ้น")

    discover = get_field(product, "discoverTime", "createTime", "onlineTime", default="")
    days = days_since(discover)
    if days <= 3:
        score += 25
        reasons.append("ใหม่มาก! เพิ่งเข้า 3 วัน 🆕")
    elif days <= 7:
        score += 18
        reasons.append(f"ใหม่ {days} วัน")
    elif days <= 14:
        score += 10
        reasons.append(f"เข้ามา {days} วัน")
    elif days <= 30:
        score += 4
        reasons.append(f"เข้ามา {days} วัน")

    velocity = get_velocity(product)
    if velocity >= 50:
        score += 20
        reasons.append(f"Velocity {velocity}% ⚡ เพิ่งระเบิดตัว!")
    elif velocity >= 20:
        score += 14
        reasons.append(f"Velocity {velocity}% กำลังพุ่ง")
    elif velocity >= 10:
        score += 8
        reasons.append(f"Velocity {velocity}%")
    elif velocity > 0:
        score += 3
        reasons.append(f"Velocity {velocity}%")

    if source_count >= 3:
        score += 15
        reasons.append("ติดสัญญาณ 3+ แหล่ง ✅")
    elif source_count == 2:
        score += 9
        reasons.append("ติดสัญญาณ 2 แหล่ง")
    else:
        score += 3

    price = float(get_field(product, "localPrice", "price", "salePrice", default=0) or 0)
    if 50 <= price <= 500:
        score += 10
        reasons.append(f"ราคา ฿{price:.0f} ขายง่าย 💰")
    elif 0 < price < 50:
        score += 6
        reasons.append(f"ราคา ฿{price:.0f} ถูกมาก")
    elif price > 500:
        score += 3
        reasons.append(f"ราคา ฿{price:.0f} สูงหน่อย")

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

    item_map   = {}
    item_count = {}
    for source_name, items in sources.items():
        for item in items:
            iid = item.get("itemId")
            if not iid:
                continue
            if iid not in item_map:
                item_map[iid]   = item
                item_count[iid] = 0
            item_count[iid] += 1

    print(f"รวม unique: {len(item_map)} ตัว")

    scored = []
    for iid, product in item_map.items():
        score, reasons = calculate_score(product, item_count[iid])
        scored.append({
            "product":  product,
            "score":    score,
            "reasons":  reasons,
            "velocity": get_velocity(product),
            "category": get_category(product),
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
    zone_a = scored[:ZONE_A_COUNT]
    zone_b = scored[ZONE_A_COUNT:ZONE_A_COUNT + ZONE_B_COUNT]
    print(f"Zone A: {len(zone_a)}  Zone B: {len(zone_b)}")
    return zone_a, zone_b


# ══════════════════════════════════════
# FORMAT
# ══════════════════════════════════════

def fmt_product_full(rank, item):
    p       = item["product"]
    score   = item["score"]
    reasons = item["reasons"]
    cat     = item["category"]
    v       = item["velocity"]
    title   = get_field(p, "itemTitle", "title", "name", "goodsName")[:40]
    price   = float(get_field(p, "localPrice", "price", "salePrice", default=0) or 0)
    total   = int(get_field(p, "soldCountTotal", "totalSold", "soldCount", default=0) or 0)
    sold_1d = int(get_field(p, "soldCount1d", default=0) or 0)

    lines = [
        f"\n{rank}. <b>{title}</b>",
        f"   {cat}",
        f"   💰 ฿{price:.0f}  📦 รวม {total:,}  เมื่อวาน {sold_1d:,}",
        f"   ⚡ {vel_bar(v)} {v}%",
        f"   🎯 Score: {score}/100",
    ]
    for r in reasons[:2]:
        lines.append(f"   • {r}")
    return "\n".join(lines)


def fmt_product_short(rank, item):
    p       = item["product"]
    score   = item["score"]
    cat     = item["category"]
    v       = item["velocity"]
    title   = get_field(p, "itemTitle", "title", "name", "goodsName")[:30]
    price   = float(get_field(p, "localPrice", "price", "salePrice", default=0) or 0)
    sold_1d = int(get_field(p, "soldCount1d", "soldCount", default=0) or 0)
    return (
        f"{rank}. {title}\n"
        f"   {cat}  ฿{price:.0f}  เมื่อวาน {sold_1d:,}  "
        f"{vel_icon(v)}{v}%  [{score}]"
    )


# ══════════════════════════════════════
# BUILD MESSAGES
# ══════════════════════════════════════

def build_message1(zone_a):
    today_str = datetime.now().strftime("%d/%m/%Y")
    lines = [
        "🟢 <b>ทำเลยวันนี้! Top 5 ปักตะกร้า</b>",
        f"📅 {today_str}",
        "━━━━━━━━━━━━━━━━━━━━",
        "<i>⚡Velocity = % ขายเมื่อวาน/ยอดรวม | สูง=เพิ่งระเบิด!</i>",
    ]
    if zone_a:
        for i, item in enumerate(zone_a, 1):
            lines.append(fmt_product_full(i, item))
    else:
        lines.append("\n⚠️ ไม่มีสินค้าวันนี้")
    lines += [
        "\n━━━━━━━━━━━━━━━━━━━━",
        "📩 รายการสำรองในข้อความถัดไป",
    ]
    return "\n".join(lines)


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
        "⚡ 🔴≥50%  🟠≥30%  🟡≥20%  🟢≥10%  ⚫<10%",
        "🔄 อัพเดทอัตโนมัติทุก 09:00 น.",
    ]
    return "\n".join(lines)


# ══════════════════════════════════════
# SEND TELEGRAM
# ══════════════════════════════════════

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    # ตัดเป็น chunk ≤ 3500 ตัวอักษร (เผื่อ margin)
    chunks = [text[i:i+3500] for i in range(0, len(text), 3500)]
    for idx, chunk in enumerate(chunks):
        r = requests.post(url, json={
            "chat_id":    CHAT_ID,
            "text":       chunk,
            "parse_mode": "HTML",
        }, timeout=15)
        print(f"  chunk {idx+1}/{len(chunks)}: status {r.status_code}")
        if r.status_code != 200:
            print(f"  Error: {r.text}")
        time.sleep(1)


# ══════════════════════════════════════
# MAIN
# ══════════════════════════════════════

def main():
    scored = collect_all_products()

    if not scored:
        send_telegram("⚠️ ดึงข้อมูลไม่ได้วันนี้ ลองใหม่พรุ่งนี้")
        return

    zone_a, zone_b = split_zones(scored)

    print("ส่ง message 1 (Zone A)...")
    send_telegram(build_message1(zone_a))

    time.sleep(3)

    print("ส่ง message 2 (Zone B)...")
    send_telegram(build_message2(zone_b))

    print("✅ เสร็จแล้ว")


if __name__ == "__main__":
    main()
