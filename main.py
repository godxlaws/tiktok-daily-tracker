import requests
import os
import json
import time

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

BASE_URL = "https://www.tabcut.com"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Referer": f"{BASE_URL}/workbench",
})


# ======================
# FETCH API
# ======================

def fetch(endpoint, payload):
    url = f"{BASE_URL}/api/trpc/{endpoint}"
    res = session.get(url, params={"input": json.dumps(payload)})
    data = res.json()

    return (
        data.get("result", {})
            .get("data", {})
            .get("result", {})
            .get("data", [])
    )


def fetch_yesterday():
    return fetch("ranking.goods.hotTrendData", {
        "pageNo": 1,
        "pageSize": 24,
        "region": "TH",
        "itemCategoryId": "0",
        "trendFilterType": 1
    })


def fetch_3day():
    return fetch("ranking.goods.hotTrendData", {
        "pageNo": 1,
        "pageSize": 24,
        "region": "TH",
        "itemCategoryId": "0",
        "trendFilterType": 2
    })


# ======================
# HELPERS
# ======================

def get(p, *keys, default=0):
    for k in keys:
        if k in p and p[k] not in [None, ""]:
            return p[k]
    return default


def to_int(x):
    try:
        return int(float(x))
    except:
        return 0


def get_id(p):
    return get(p, "itemId")


def get_title(p):
    return str(get(p, "itemTitle", "title", "name", default="?"))[:50]


def get_price(p):
    return float(get(p, "localPrice", "price", default=0))


def get_1d(p):
    return to_int(get(p, "soldCount1d"))


def get_3d(p):
    return to_int(get(p, "soldCount3d"))


def get_total(p):
    return to_int(get(p, "soldCountTotal"))


def get_image(p):
    return get(p, "itemPicUrl", "imageUrl", default="")


def get_link(p):
    iid = get_id(p)
    if iid:
        return f"https://www.tiktok.com/view/product/{iid}"
    return ""


# ======================
# SCORING (หัวใจหลัก)
# ======================

def trend_score(p, p3=None):
    s1 = get_1d(p)
    s3 = get_3d(p)

    if s3 <= 0 and p3:
        s3 = get_3d(p3)

    avg3 = s3 / 3 if s3 > 0 else 0
    total = get_total(p)

    score = 0

    # Demand
    if s1 >= 500:
        score += 40
    elif s1 >= 200:
        score += 30
    elif s1 >= 100:
        score += 20
    else:
        score += 5

    # Momentum
    ratio = 0
    if avg3 > 0:
        ratio = s1 / avg3

        if ratio >= 2:
            score += 40
        elif ratio >= 1.5:
            score += 30
        elif ratio >= 1.2:
            score += 20
        elif ratio >= 1:
            score += 10
        else:
            score -= 10

    # Velocity
    if total > 0:
        v = s1 / total
        if v >= 0.3:
            score += 20
        elif v >= 0.15:
            score += 10

    return score, ratio


# ======================
# TELEGRAM
# ======================

def send_photo(img, caption):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"

    requests.post(url, json={
        "chat_id": CHAT_ID,
        "photo": img,
        "caption": caption
    })


# ======================
# MAIN
# ======================

def main():
    y = fetch_yesterday()
    d3 = fetch_3day()

    map3 = {get_id(x): x for x in d3}

    results = []

    for p in y:
        if get_1d(p) <= 0:
            continue

        p3 = map3.get(get_id(p))

        score, ratio = trend_score(p, p3)

        results.append({
            "p": p,
            "score": score,
            "ratio": ratio
        })

    results.sort(key=lambda x: x["score"], reverse=True)

    top = [x for x in results if x["score"] >= 60][:10]

    for i, item in enumerate(top, 1):
        p = item["p"]

        title = get_title(p)
        price = get_price(p)
        s1 = get_1d(p)
        s3 = get_3d(p)
        ratio = item["ratio"]
        score = item["score"]

        caption = (
            f"🔥 #{i} {title}\n"
            f"💰 ฿{price:.0f}\n"
            f"📊 1D: {s1} | 3D: {s3}\n"
            f"⚡ Ratio: {ratio:.2f}\n"
            f"🎯 Score: {score}\n\n"
            f"🛒 {get_link(p)}"
        )

        send_photo(get_image(p), caption)
        time.sleep(1)


if __name__ == "__main__":
    main()
