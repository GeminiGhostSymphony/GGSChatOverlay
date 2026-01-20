import requests
import json
import os
import re
import time
import random
import sys
import traceback
from bs4 import BeautifulSoup

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)

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

def get_scraped_data_playwright():
    print("DEBUG: Using Playwright fallback with element-based waiting")
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])

            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            stealth = Stealth()
            stealth.apply_stealth_sync(page)
            
            page.goto(SOURCE_URL, wait_until="domcontentloaded", timeout=60000)
            
            print("DEBUG: Waiting for badge links to appear...")
            page.wait_for_selector('a[href*="/twitch/global-badges/"]', timeout=15000)
            
            time.sleep(3)
            
            content = page.content()
            browser.close()
            return content
        except Exception as e:
            print(f"DEBUG: Playwright fallback failed: {e}")
            return None

def parse_html(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    scraped = []
    links = soup.find_all('a', href=re.compile(r'/twitch/global-badges/'))
    for link in links:
        img = link.find('img')
        if not img: continue
        parts = [p for p in link.get('href').strip('/').split('/') if p]
        if len(parts) >= 3:
            s_id = parts[2]
            v_id = parts[3] if len(parts) > 3 else "1"
            img_src = img.get('src', '')
            if not img_src or "static-cdn.jtvnw.net" not in img_src: continue
            url = re.sub(r'/(_?)[0-9]+$', '/3', img_src)
            if not url.endswith('/3'): url = f"{url.rstrip('/')}/3"
            scraped.append({"set_id": str(s_id), "id": str(v_id), "name": img.get('alt', s_id).strip(), "url": url})
    return scraped

def get_scraped_data():
    try:
        response = scraper.get(SOURCE_URL, timeout=20)
        if response.status_code == 403 or "cloudflare" in response.text.lower():
            html = get_scraped_data_playwright()
        else:
            html = response.text
    except Exception:
        html = get_scraped_data_playwright()
    return parse_html(html) if html else []

def is_url_broken(url):
    try:
        return requests.head(url, timeout=10, allow_redirects=True).status_code != 200
    except: return True

def sync():
    try:
        db = {"global": []}
        if os.path.exists(JSON_FILE):
            with open(JSON_FILE, 'r', encoding='utf-8') as f:
                db = json.load(f)

        scraped = get_scraped_data()
        if not scraped: 
            print("DEBUG: No data was scraped. Check if SOURCE_URL is accessible.")
            raise Exception("Scrape empty or blocked.")

        lookup = {(b['set_id'], str(b['id'])): b for b in scraped}
        changed, existing_combinations = False, set()

        # Build existing map
        print("DEBUG: Building map")
        if "global" in db:
            for item in db.get("global", []):
                sid = str(item.get("set_id"))
                for v in item.get("versions", []):
                    vid = str(v.get("id"))
                    existing_combinations.add((sid, vid))

        # Add New Badges
        print("DEBUG: Adding badges")
        for b in scraped:
            sid, vid = str(b["set_id"]), str(b["id"])
            if (sid, vid) in existing_combinations: continue
            
            target = next((i for i in db["global"] if str(i["set_id"]) == sid), None)
            new_v = {"id": vid, "image_url_1x": b["url"], "image_url_2x": b["url"], "image_url_4x": b["url"]}
            
            if not target:
                db["global"].append({"set_id": sid, "versions": [new_v]})
            else:
                target["versions"].append(new_v)

            message = f"New Twitch Badge Found: **{b['name']}** (`{b['set_id']}/{b['id']}`)"
            notify_discord(message, image_url=b['url'])
            
            changed = True
            existing_combinations.add((sid, vid))

        if changed:
            with open(JSON_FILE, 'w', encoding='utf-8') as f:
                json.dump(db, f, indent=4, ensure_ascii=False)
            print("DEBUG: Changes saved to JSON.")
        else:
            print("DEBUG: No new badges found.")
            
    except Exception:
        print("\n!!! CRITICAL ERROR DETECTED !!!")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    sync()
