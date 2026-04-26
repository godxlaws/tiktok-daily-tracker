import requests
import os
import json
from datetime import datetime, timedelta
from urllib.parse import quote

# ══════════════════════════════════════
# CONFIG
# ══════════════════════════════════════
BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID   = os.environ["CHAT_ID"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120.0.0.0",
    "Referer": "https://www.tabcut.com/",
    "Accept": "application/json",
}

TODAY     = datetime.now().strftime("%Y%m%d")
YESTERDAY = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

# ══════════════════════════════════════
# FETCH FUNCTIONS
# ══════════════════════════════════════

def fetch_trpc(endpoint, input_dict, pages=10):
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
                print(f"  ไม่มีข้อมูลที่ page {page}")
                break
            all_items.extend(items)
        except Exception as e:
            print(f"  Error page {page}: {e}")
            break
    return all_items


def fetch_surge_1d():
    print("ดึง surge_1d...")
    return fetch_trpc("ranking.goods.hotTrendData", {
        "pageSize": 24,
        "region": "TH",
        "itemCategoryId": "0",
        "trendFilterType": 1,
    })


def fetch_surge_3d():
    print("ดึง surge_3d...")
    return fetch_trpc("ranking.goods.hotTrendData", {
        "pageSize": 24,
        "region": "TH",
        "itemCategoryId": "0",
        "trendFilterType": 2,
    })


def fetch_recommended():
    print("ดึง recommended...")
    return fetch_trpc("ranking.goods.recommendGoodsRanking", {
        "pageSize": 24,
        "region": "TH",
        "categoryId": "0",
        "bizDate": YESTERDAY,
        "orderType": "7",
        "rankType": 1,
    })


def fetch_new_products():
    print("ดึง new products...")
    return fetch_trpc("ranking.goods.newGoodsRanking", {
        "pageSize": 24,
        "region": "TH",
        "categoryId": "0",
        "bizDate": YESTERDAY,
        "orderType": "3",
    })


# ══════════════════════════════════════
# HELPERS
# ══════════════════════════════════════

def get_field(product, *keys, default="?"):
    """ลอง field หลายชื่อ รองรับ API ต่างโครงสร้าง"""
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


# ══════════════════════════════════════
# SCORING
# ══════════════════════════════════════

def calculate_score(product, source_count):
    score = 0
    reasons = []

    # 1. ยอดขาย 1 วัน (35 คะแนน)
    sold_1d = int(get_field(product, "soldCount1d", "soldCount", default=0) or 0)
    if sold_1d >= 500:
        score += 35
        reasons.append(f"ขายเมื่อวาน {sold_1d:,} ชิ้น 🔥")
    elif sold_1d >= 200:
        score += 25
        reasons.append(f"ขายเมื่อวาน {sold_1d:,} ชิ้น 📈")
    elif sold_1d >= 50:
        score += 15
        reasons.append(f"ขายเมื่อวาน {sold_1d:,} ชิ้น")
    elif sold_1d > 0:
        score += 5
        reasons.append(f"ขายเมื่อวาน {sold_1d:,} ชิ้น")

    # 2. ความใหม่ (30 คะแนน)
    discover = get_field(product, "discoverTime", "createTime", "onlineTime", default="")
    days = days_since(discover)
    if days <= 3:
        score += 30
        reasons.append("ใหม่มาก! เพิ่งเข้า 3 วัน 🆕")
    elif days <= 7:
        score += 20
        reasons.append(f"ใหม่ {days} วัน")
    elif days <= 14:
        score += 10
        reasons.append(f"เข้ามา {days} วัน")

    # 3. ติดหลาย API (20 คะแนน)
    if source_count >= 3:
        score += 20
        reasons.append("ติดสัญญาณ 3 แหล่ง ✅")
    elif source_count == 2:
        score += 12
        reasons.append("ติดสัญญาณ 2 แหล่ง")
    else:
        score += 5

    # 4. ราคา (15 คะแนน)
    price = float(get_field(product, "localPrice", "price", "salePrice", default=0) or 0)
    if 50 <= price <= 500:
        score += 15
        reasons.append(f"ราคา ฿{price:.0f} ขายง่าย 💰")
    elif price < 50 and price > 0:
        score += 8
        reasons.append(f"ราคา ฿{price:.0f} ถูกมาก")
    elif price > 0:
        reasons.append(f"ราคา ฿{price:.0f}")

    return min(score, 100), reasons


def zone_label(score):
    if score >= 60:
        return "A"
    elif score >= 35:
        return "B"
    else:
        return "C"


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

    # รวมและนับซ้ำ
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

    # คำนวณ score
    scored = []
    for iid, product in item_map.items():
        score, reasons = calculate_score(product, item_count[iid])
        scored.append({
            "product": product,
            "score":   score,
            "reasons": reasons,
            "zone":    zone_label(score),
        })

    # กรองออกถ้าไม่มีชื่อหรือราคา
    scored = [
        x for x in scored
        if get_field(x["product"], "itemTitle", "title", "name", "goodsName") != "?" and
           float(get_field(x["product"], "localPrice", "price", "salePrice", default=0) or 0) > 0
    ]

    scored.sort(key=lambda x: x["score"], reverse=True)

    za = [x for x in scored if x["zone"] == "A"]
    zb = [x for x in scored if x["zone"] == "B"]
    zc = [x for x in scored if x["zone"] == "C"]
    print(f"Zone A: {len(za)}  Zone B: {len(zb)}  Zone C: {len(zc)}")

    return scored


# ══════════════════════════════════════
# FORMAT MESSAGES
# ══════════════════════════════════════

def fmt_product_full(rank, item):
    p       = item["product"]
    score   = item["score"]
    reasons = item["reasons"]
    title   = get_field(p, "itemTitle", "title", "name", "goodsName")[:40]
    price   = float(get_field(p, "localPrice", "price", "salePrice", default=0) or 0)
    total   = int(get_field(p, "soldCountTotal", "totalSold", "soldCount", default=0) or 0)

    lines = [
        f"\n{rank}. <b>{title}</b>",
        f"   💰 ฿{price:.0f}  📦 ยอดรวม {total:,}",
        f"   🎯 Score: {score}/100",
    ]
    for r in reasons[:2]:
        lines.append(f"   • {r}")
    return "\n".join(lines)


def fmt_product_short(rank, item):
    p     = item["product"]
    score = item["score"]
    title = get_field(p, "itemTitle", "title", "name", "goodsName")[:35]
    price = float(get_field(p, "localPrice", "price", "salePrice", default=0) or 0)
    sold  = int(get_field(p, "soldCount1d", "soldCount", "sales", default=0) or 0)
    return f"{rank}. {title}\n   ฿{price:.0f}  เมื่อวาน {sold:,} ชิ้น  [{score}]"


def build_message1(zone_a):
    today_str = datetime.now().strftime("%d/%m/%Y")
    lines = [
        "🟢 <b>ทำเลยวันนี้! Top 5 ปักตะกร้า</b>",
        f"📅 {today_str}",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    if zone_a:
        for i, item in enumerate(zone_a[:5], 1):
            lines.append(fmt_product_full(i, item))
    else:
        lines.append("\n⚠️ ไม่มีสินค้า Zone A วันนี้")

    lines += [
        "\n━━━━━━━━━━━━━━━━━━━━",
        "💡 Score สูง = คู่แข่งน้อย + ตลาดต้องการ",
        "📩 ดูรายการเพิ่มเติมในข้อความถัดไป",
    ]
    return "\n".join(lines)


def build_message2(zone_b, zone_c):
    lines = [
        "📋 <b>รายการสำรอง</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "\n🟡 <b>Zone B — ยังทันถ้ารีบ</b>",
        "<i>(คู่แข่งเริ่มมีบ้างแล้ว)</i>",
    ]

    if zone_b:
        for i, item in enumerate(zone_b[:10], 1):
            lines.append(fmt_product_short(i, item))
    else:
        lines.append("  ไม่มีสินค้าใน Zone นี้วันนี้")

    lines += [
        "\n━━━━━━━━━━━━━━━━━━━━",
        "\n🔴 <b>Zone C — อ้างอิงเท่านั้น</b>",
        "<i>(ขายดีแล้ว แต่คู่แข่งเยอะ)</i>",
    ]

    if zone_c:
        for i, item in enumerate(zone_c[:10], 1):
            lines.append(fmt_product_short(i, item))
    else:
        lines.append("  ไม่มีสินค้าใน Zone นี้วันนี้")

    lines += [
        "\n━━━━━━━━━━━━━━━━━━━━",
        "🔄 อัพเดทอัตโนมัติทุก 09:00 น.",
    ]
    return "\n".join(lines)


# ══════════════════════════════════════
# SEND TELEGRAM
# ══════════════════════════════════════

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    for chunk in [text[i:i+4000] for i in range(0, len(text), 4000)]:
        requests.post(url, json={
            "chat_id":    CHAT_ID,
            "text":       chunk,
            "parse_mode": "HTML",
        }, timeout=10)


# ══════════════════════════════════════
# MAIN
# ══════════════════════════════════════

def main():
    scored = collect_all_products()

    if not scored:
        send_telegram("⚠️ ดึงข้อมูลไม่ได้วันนี้ ลองใหม่พรุ่งนี้")
        return

    zone_a = [x for x in scored if x["zone"] == "A"]
    zone_b = [x for x in scored if x["zone"] == "B"]
    zone_c = [x for x in scored if x["zone"] == "C"]

    send_telegram(build_message1(zone_a))
    send_telegram(build_message2(zone_b, zone_c))
    print("✅ ส่ง Telegram เรียบร้อย")


if __name__ == "__main__":
    main()
