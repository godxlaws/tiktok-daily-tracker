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
    """ดึงข้อมูลจาก trpc endpoint หลายหน้า"""
    all_items = []
    for page in range(1, pages + 1):
        input_dict["pageNo"] = page
        encoded = quote(json.dumps(input_dict, ensure_ascii=False))
        url = f"https://www.tabcut.com/api/trpc/{endpoint}?input={encoded}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                break
            data = r.json()
            items = (
                data.get("result", {})
                    .get("data", {})
                    .get("result", {})
                    .get("data", [])
            )
            if not items:
                break
            all_items.extend(items)
        except Exception as e:
            print(f"Error page {page}: {e}")
            break
    return all_items


def fetch_surge_1d():
    """เมื่อวานพุ่ง — สัญญาณดีที่สุด"""
    return fetch_trpc("ranking.goods.hotTrendData", {
        "pageSize": 24,
        "region": "TH",
        "itemCategoryId": "0",
        "trendFilterType": 1,
    })


def fetch_surge_3d():
    """3 วันพุ่ง — ยังทัน"""
    return fetch_trpc("ranking.goods.hotTrendData", {
        "pageSize": 24,
        "region": "TH",
        "itemCategoryId": "0",
        "trendFilterType": 2,
    })


def fetch_recommended():
    """Platform กำลัง push"""
    return fetch_trpc("ranking.goods.recommendGoodsRanking", {
        "pageSize": 24,
        "region": "TH",
        "categoryId": "0",
        "bizDate": YESTERDAY,
        "orderType": "7",
        "rankType": 1,
    })


def fetch_new_products():
    """สินค้าใหม่เพิ่งเข้า"""
    return fetch_trpc("ranking.goods.newGoodsRanking", {
        "pageSize": 24,
        "region": "TH",
        "categoryId": "0",
        "bizDate": YESTERDAY,
        "orderType": "3",
    })


# ══════════════════════════════════════
# SCORING
# ══════════════════════════════════════

def days_since(discover_time_str):
    """นับวันที่สินค้าเข้า TikTok Shop"""
    try:
        dt = datetime.fromisoformat(discover_time_str.replace("Z", ""))
        return (datetime.now() - dt).days
    except:
        return 999


def calculate_score(product, source_count):
    """
    คำนวณ score 0-100 สำหรับการตัดสินใจทำคลิป
    
    เกณฑ์:
    - ยอดขายเมื่อวาน (soldCount1d)   → 35 คะแนน
    - ความใหม่ของสินค้า (discoverTime) → 30 คะแนน
    - ติดหลาย API                     → 20 คะแนน
    - ราคาขายง่าย 50-500 บาท         → 15 คะแนน
    """
    score = 0
    reasons = []

    # 1. ยอดขาย 1 วัน
    sold_1d = product.get("soldCount1d", 0) or 0
    total   = product.get("soldCountTotal", 1) or 1
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

    # 2. ความใหม่
    days = days_since(product.get("discoverTime", ""))
    if days <= 3:
        score += 30
        reasons.append("ใหม่มาก! เพิ่งเข้า 3 วัน 🆕")
    elif days <= 7:
        score += 20
        reasons.append(f"ใหม่ {days} วัน")
    elif days <= 14:
        score += 10
        reasons.append(f"เข้ามา {days} วัน")

    # 3. ติดหลาย API
    if source_count >= 3:
        score += 20
        reasons.append("ติดสัญญาณ 3 แหล่ง ✅")
    elif source_count == 2:
        score += 12
        reasons.append("ติดสัญญาณ 2 แหล่ง")
    else:
        score += 5

    # 4. ราคา
    price = product.get("localPrice", 0) or 0
    if 50 <= price <= 500:
        score += 15
        reasons.append(f"ราคา ฿{price:.0f} ขายง่าย 💰")
    elif price < 50:
        score += 8
        reasons.append(f"ราคา ฿{price:.0f} ถูกมาก")
    else:
        reasons.append(f"ราคา ฿{price:.0f}")

    return min(score, 100), reasons


def zone_label(score):
    if score >= 70:
        return "A"
    elif score >= 45:
        return "B"
    else:
        return "C"


# ══════════════════════════════════════
# COLLECT + RANK
# ══════════════════════════════════════

def collect_all_products():
    """รวมสินค้าจากทุก API แล้วคัดกรอง"""
    print("กำลังดึงข้อมูล...")

    sources = {
        "surge_1d":    fetch_surge_1d(),
        "surge_3d":    fetch_surge_3d(),
        "recommended": fetch_recommended(),
        "new":         fetch_new_products(),
    }

    print(f"surge_1d: {len(sources['surge_1d'])} ตัว")
    print(f"surge_3d: {len(sources['surge_3d'])} ตัว")
    print(f"recommended: {len(sources['recommended'])} ตัว")
    print(f"new: {len(sources['new'])} ตัว")

    # รวมและนับว่าแต่ละ item ติด API กี่ตัว
    item_map   = {}   # itemId → product data
    item_count = {}   # itemId → จำนวน API ที่ติด

    for source_name, items in sources.items():
        for item in items:
            iid = item.get("itemId")
            if not iid:
                continue
            if iid not in item_map:
                item_map[iid]   = item
                item_count[iid] = 0
            item_count[iid] += 1

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

    # เรียง score มากสุดก่อน
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


# ══════════════════════════════════════
# FORMAT MESSAGES
# ══════════════════════════════════════

def fmt_product_full(rank, item):
    """Zone A — แสดงครบพร้อมเหตุผล"""
    p       = item["product"]
    score   = item["score"]
    reasons = item["reasons"]
    title   = p.get("itemTitle", "?")[:40]
    price   = p.get("localPrice", "?")
    total   = p.get("soldCountTotal", 0)

    lines = [
        f"\n{rank}. <b>{title}</b>",
        f"   💰 ฿{price:.0f}  📦 ยอดรวม {total:,}",
        f"   🎯 Score: {score}/100",
    ]
    for r in reasons[:2]:  # แสดงแค่ 2 เหตุผลหลัก
        lines.append(f"   • {r}")
    return "\n".join(lines)


def fmt_product_short(rank, item):
    """Zone B/C — แสดงสั้นๆ"""
    p     = item["product"]
    score = item["score"]
    title = p.get("itemTitle", "?")[:35]
    price = p.get("localPrice", "?")
    sold  = p.get("soldCount1d", 0) or 0
    return f"{rank}. {title}\n   ฿{price:.0f}  เมื่อวาน {sold:,} ชิ้น  [{score}]"


def build_message1(zone_a):
    """ข้อความที่ 1 — สรุปด่วน Zone A"""
    today_str = datetime.now().strftime("%d/%m/%Y")
    lines = [
        "🟢 <b>ทำเลยวันนี้! Top 5 ปักตะกร้า</b>",
        f"📅 {today_str}",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    for i, item in enumerate(zone_a[:5], 1):
        lines.append(fmt_product_full(i, item))
    lines += [
        "\n━━━━━━━━━━━━━━━━━━━━",
        "💡 Score สูง = คู่แข่งน้อย + ตลาดต้องการ",
        "📩 ดูรายการเพิ่มเติมในข้อความถัดไป",
    ]
    return "\n".join(lines)


def build_message2(zone_b, zone_c):
    """ข้อความที่ 2 — Zone B และ C"""
    lines = [
        "📋 <b>รายการสำรอง</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "\n🟡 <b>Zone B — ยังทันถ้ารีบ</b>",
        "<i>(คู่แข่งเริ่มมีบ้างแล้ว)</i>",
    ]
    for i, item in enumerate(zone_b[:10], 1):
        lines.append(fmt_product_short(i, item))

    lines += [
        "\n━━━━━━━━━━━━━━━━━━━━",
        "\n🔴 <b>Zone C — อ้างอิงเท่านั้น</b>",
        "<i>(ขายดีแล้ว แต่คู่แข่งเยอะ)</i>",
    ]
    for i, item in enumerate(zone_c[:10], 1):
        lines.append(fmt_product_short(i, item))

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
    # แบ่งถ้าเกิน 4000 ตัวอักษร
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

    print(f"Zone A: {len(zone_a)}  Zone B: {len(zone_b)}  Zone C: {len(zone_c)}")

    # ส่ง 2 ข้อความ
    send_telegram(build_message1(zone_a))
    send_telegram(build_message2(zone_b, zone_c))
    print("✅ ส่ง Telegram เรียบร้อย")


if __name__ == "__main__":
    main()
