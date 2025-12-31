import requests
import json
import os
import re
import time
import random
from bs4 import BeautifulSoup

try:
    import cloudscraper
    scraper = cloudscraper.create_scraper()
except ImportError:
    scraper = requests.Session()

SOURCE_URL = "https://www.streamdatabase.com/twitch/global-badges"
JSON_FILE = "global-badges.json"
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")

def notify_discord(message, image_url=None):
    if not DISCORD_WEBHOOK: return
    payload = {"username": "GGS Badge Tracker", "content": message}
    if image_url:
        payload["embeds"] = [{"image": {"url": image_url}, "color": 10181046}]
    try:
        requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
        time.sleep(2) # rate limits
    except: pass

def is_url_broken(url):
    """HEAD request to check image availability."""
    try:
        response = requests.head(url, timeout=10, allow_redirects=True)
        return response.status_code != 200
    except: return True

def get_scraped_data():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        response = scraper.get(SOURCE_URL, headers=headers, timeout=20)
        response.raise_for_status()
    except Exception as e:
        print(f"Scrape failed: {e}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    scraped = []
    # Identify links matching global badge structure
    for link in soup.find_all('a', href=re.compile(r'/twitch/global-badges/')):
        img = link.find('img')
        if not img: continue
        parts = link.get('href').strip('/').split('/')
        if len(parts) >= 3:
            s_id = parts[2]
            v_id = parts[3] if len(parts) > 3 else "1"
            img_src = img.get('src')
            if "static-cdn.jtvnw.net" not in img_src: continue
            
            # Force high-res Twitch CDN URL (Size 3 for 72x72px)
            url = re.sub(r'/(_?)[0-9]+$', '/3', img_src)
            if not url.endswith('/3'): url = f"{url.rstrip('/')}/3"
            
            scraped.append({"set_id": s_id, "id": str(v_id), "name": img.get('alt', s_id).strip(), "url": url})
    return scraped

def sync():
    if not os.path.exists(JSON_FILE): return
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        try: db = json.load(f)
        except: return
    
    scraped = get_scraped_data()
    lookup = {(b['set_id'], b['id']): b for b in scraped}
    changed = False

    # Check 10% of existing + any broken ones
    if "global" in db:
        for item in db["global"]:
            sid = item.get("set_id")
            for v in item.get("versions", []):
                vid = str(v.get("id"))
                if random.random() < 0.10 or is_url_broken(v.get("image_url_1x")):
                    if is_url_broken(v.get("image_url_1x")):
                        fresh = lookup.get((sid, vid))
                        if fresh:
                            v.update({"image_url_1x": fresh["url"], "image_url_2x": fresh["url"], "image_url_4x": fresh["url"]})
                            changed = True
                            notify_discord(f"🔧 Repaired link: `{sid}` ({vid})", fresh["url"])

    # Add New Badges
    for b in scraped:
        target = next((i for i in db.get("global", []) if i["set_id"] == b["set_id"]), None)
        if not target:
            db["global"].append({"set_id": b["set_id"], "versions": [{"id": b["id"], "image_url_1x": b["url"], "image_url_2x": b["url"], "image_url_4x": b["url"]}]})
            changed = True
            notify_discord(f"🚀 New Badge Set: `{b['name']}`", b["url"])
        elif not any(str(v["id"]) == b["id"] for v in target["versions"]):
            target["versions"].append({"id": b["id"], "image_url_1x": b["url"], "image_url_2x": b["url"], "image_url_4x": b["url"]})
            changed = True
            notify_discord(f"✨ New Version Detected: `{b['set_id']}` ({b['id']})", b["url"])

    if changed:
        with open(JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(db, f, indent=4, ensure_ascii=False, sort_keys=False)

if __name__ == "__main__":
    sync()
