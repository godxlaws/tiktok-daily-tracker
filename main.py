import requests
import os
import json
import time
import base64
import glob
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

TABCUT_EMAIL    = require_env("TABCUT_EMAIL")
TABCUT_PASSWORD = require_env("TABCUT_PASSWORD")

BASE_URL      = "https://www.tabcut.com"
YESTERDAY     = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
KEEP_DAYS     = 30   # เก็บย้อนหลังกี่วัน

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
        r = session.post(f"{BASE_URL}/api/auth/callback/email?", data={
            "email": TABCUT_EMAIL, "password": enc_pw,
            "csrfToken": csrf, "callbackUrl": f"{BASE_URL}/workbench",
            "redirect": "false", "json": "true",
        })
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
        "pageNo": 1, "pageSize": 24, "region": "TH",
        "itemCategoryId": "0", "trendFilterType": trend_type,
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
        "pageNo": 1, "pageSize": 24, "rankType": 1,
        "bizDate": YESTERDAY, "region": "TH",
        "categoryId": "0", "orderType": "1", "sellerType": "",
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
        valid = [p for p in items if top_sold(p) > 0]
        print(f"[TOP] found {len(items)} → valid {len(valid)}")
        return valid[:limit]
    except Exception as e:
        print(f"[TOP] error: {e}")
        return []

# ══════════════════════════════════════
# HELPERS
# ══════════════════════════════════════

def get(p, key, default=0):
    return p.get(key, default) or default

def safe_int(x):
    try: return int(float(x))
    except: return 0

def safe_float(x):
    try: return float(x)
    except: return 0.0

def sold_1d(p): return safe_int(get(p, "soldCount1d"))
def sold_3d(p): return safe_int(get(p, "soldCount3d"))
def title(p):   return get(p, "itemTitle", "?")[:60]

def link_from_id(item_id):
    return f"https://www.tiktok.com/view/product/{item_id}" if item_id else ""

def link(p):  return link_from_id(get(p, "itemId"))
def img(p):
    url = get(p, "itemPicUrl")
    return url if url and url != 0 else ""

def top_sold(p):
    info = p.get("soldCountInfo") or {}
    return safe_int(info.get("periodCurrent") or info.get("total") or 0)

def top_total_sold(p):
    info = p.get("soldCountInfo") or {}
    return safe_int(info.get("total") or 0)

def top_growth(p):
    rate = safe_float(p.get("soldCountGrowthRate") or 0)
    if rate >= 1: return None
    return round(rate * 100, 1)

def top_commission(p):
    rate = safe_float(p.get("commissionRate") or 0)
    return round(rate * 100, 1)

def top_videos(p):
    info = p.get("relatedVideoInfo") or {}
    val  = info.get("period90d")
    return safe_int(val) if val is not None else None

def top_creators(p):
    info = p.get("relatedCreatorInfo") or {}
    val  = info.get("period90d")
    return safe_int(val) if val is not None else None

def top_img(p):
    url = p.get("itemPicUrl") or ""
    return url if url and url != 0 else ""

def top_link(p): return link_from_id(p.get("itemId", ""))

# ══════════════════════════════════════
# ANALYZE + GROUP
# ══════════════════════════════════════

def analyze(p):
    s1     = sold_1d(p)
    s3     = sold_3d(p)
    avg3   = s3 / 3 if s3 > 0 else 1
    growth = s1 / avg3
    score  = (s1 * 2) + s3 + (growth * 100)
    return s1, s3, growth, score

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
        s1, s3, growth, score = analyze(p)
        if s1 <= 0 or s3 <= 0:
            continue
        item = {"p": p, "s1": s1, "s3": s3, "growth": round(growth, 2), "score": score}
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
# BUILD JSON
# ══════════════════════════════════════

def build_trend_card(item):
    p = item["p"]
    return {
        "id":     get(p, "itemId"),
        "title":  title(p),
        "img":    img(p),
        "link":   link(p),
        "sold1d": item["s1"],
        "sold3d": item["s3"],
        "growth": item["growth"],
    }

def build_top_card(p):
    return {
        "id":       p.get("itemId"),
        "title":    (p.get("itemName") or "?")[:60],
        "img":      top_img(p),
        "link":     top_link(p),
        "seller":   p.get("sellerName") or "",
        "sold":     top_sold(p),
        "total":    top_total_sold(p),
        "growth":   top_growth(p),
        "comm":     top_commission(p),
        "videos":   top_videos(p),
        "creators": top_creators(p),
    }

# ══════════════════════════════════════
# SAVE + ROTATE + INDEX
# ══════════════════════════════════════

def save_and_rotate(viral, stable, peak, top, now):
    os.makedirs("data", exist_ok=True)

    data = {
        "updated": now.strftime("%d/%m/%Y %H:%M"),
        "date":    now.strftime("%Y-%m-%d"),
        "viral":   [build_trend_card(i) for i in viral],
        "stable":  [build_trend_card(i) for i in stable],
        "peak":    [build_trend_card(i) for i in peak],
        "top5":    [build_top_card(p)   for p in top],
    }

    # 1. บันทึกไฟล์วันนี้
    date_str  = now.strftime("%Y-%m-%d")
    date_file = f"data/{date_str}.json"
    with open(date_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ บันทึก {date_file}")

    # 2. บันทึก latest.json (เขียนทับ)
    with open("data/latest.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("✅ บันทึก data/latest.json")

    # 3. ลบไฟล์เก่าเกิน KEEP_DAYS
    cutoff = (now - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    deleted = []
    for fpath in glob.glob("data/????-??-??.json"):
        fname = os.path.basename(fpath)          # เช่น 2026-08-01.json
        fdate = fname.replace(".json", "")        # เช่น 2026-08-01
        if fdate < cutoff:
            os.remove(fpath)
            deleted.append(fdate)
    if deleted:
        print(f"🗑️  ลบไฟล์เก่า: {', '.join(deleted)}")

    # 4. อัพเดท index.json — list วันที่ทั้งหมดที่มีข้อมูล
    available = sorted([
        os.path.basename(f).replace(".json", "")
        for f in glob.glob("data/????-??-??.json")
    ], reverse=True)   # ล่าสุดก่อน

    with open("data/index.json", "w", encoding="utf-8") as f:
        json.dump({"dates": available}, f, ensure_ascii=False, indent=2)
    print(f"✅ index.json มี {len(available)} วัน: {available[:3]}{'...' if len(available) > 3 else ''}")

# ══════════════════════════════════════
# MAIN
# ══════════════════════════════════════

def main():
    if not login():
        print("❌ Login ไม่สำเร็จ")
        return

    viral, stable, peak = collect_and_group()
    top  = fetch_top_selling(5)
    now  = datetime.now(ZoneInfo("Asia/Bangkok"))

    save_and_rotate(viral, stable, peak, top, now)
    print("✅ เสร็จแล้ว")

if __name__ == "__main__":
    main()
