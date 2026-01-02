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
    payload = {"username": "Badge Bot", "content": message}
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
    """Synchronizes local JSON file with newly scraped badge data."""
    if not os.path.exists(JSON_FILE):
        db = {"global": []}
    else:
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            try:
                db = json.load(f)
            except:
                db = {"global": []}
    
    scraped = get_scraped_data()
    # Normalize scraped data into a lookup table for repairs
    lookup = {(b['set_id'], str(b['id'])): b for b in scraped}
    changed = False

    # Map existing badges to prevent duplicates, usubf a set of (set_id, version_id) tuples for O(1) lookups
    existing_combinations = set()
    if "global" in db:
        for item in db["global"]:
            sid = str(item.get("set_id"))
            for v in item.get("versions", []):
                existing_combinations.add((sid, str(v.get("id"))))

    # Repair Existing/Broken Links
    if "global" in db:
        for item in db["global"]:
            sid = str(item.get("set_id"))
            for v in item.get("versions", []):
                vid = str(v.get("id"))
                # Randomly check 10% for updates, or always check if broken
                if random.random() < 0.10 or is_url_broken(v.get("image_url_1x")):
                    fresh = lookup.get((sid, vid))
                    if fresh and v.get("image_url_1x") != fresh["url"]:
                        v.update({
                            "image_url_1x": fresh["url"], 
                            "image_url_2x": fresh["url"], 
                            "image_url_4x": fresh["url"]
                        })
                        changed = True
                        print(f"Repaired: {sid} v{vid}")

    # 3. Add New Badges & Versions
    for b in scraped:
        sid = str(b["set_id"])
        vid = str(b["id"])
        
        # SKIP if this specific set and version already exists
        if (sid, vid) in existing_combinations:
            continue

        target = next((i for i in db.get("global", []) if str(i["set_id"]) == sid), None)
        
        if not target:
            # Add an entirely new badge set
            db["global"].append({
                "set_id": sid, 
                "versions": [{
                    "id": vid, 
                    "image_url_1x": b["url"], 
                    "image_url_2x": b["url"], 
                    "image_url_4x": b["url"]
                }]
            })
            changed = True
            notify_discord(f"🚀 New Badge Set: `{b['name']}`", b["url"])
        else:
            # Add a new version to an existing set
            target["versions"].append({
                "id": vid, 
                "image_url_1x": b["url"], 
                "image_url_2x": b["url"], 
                "image_url_4x": b["url"]
            })
            changed = True
            notify_discord(f"✨ New Version Detected: `{sid}` ({vid})", b["url"])
        
        # Add to seen set to prevent internal duplicates during the same run
        existing_combinations.add((sid, vid))

    # Save changes back to file
    if changed:
        with open(JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(db, f, indent=4, ensure_ascii=False, sort_keys=False)
        print("Sync complete. Changes saved.")
    else:
        print("Sync complete. No changes needed.")

if __name__ == "__main__":
    sync()
