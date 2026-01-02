import requests
import json
import os
import re
import time
import random
from bs4 import BeautifulSoup

from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

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
    """Fallback method using a headless browser to bypass aggressive Cloudflare."""
    print("Cloudscraper failed or challenged. Attempting Playwright fallback...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        stealth_sync(page)
        try:
            page.goto(SOURCE_URL, wait_until="networkidle", timeout=60000)
            # Extra wait for Cloudflare JS challenge to resolve
            time.sleep(5)
            content = page.content()
            browser.close()
            return content
        except Exception as e:
            print(f"Playwright fallback failed: {e}")
            browser.close()
            return None

def parse_html(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    scraped = []
    for link in soup.find_all('a', href=re.compile(r'/twitch/global-badges/')):
        img = link.find('img')
        if not img: continue
        parts = link.get('href').strip('/').split('/')
        if len(parts) >= 3:
            s_id = parts[2]
            v_id = parts[3] if len(parts) > 3 else "1"
            img_src = img.get('src')
            if "static-cdn.jtvnw.net" not in img_src: continue
            url = re.sub(r'/(_?)[0-9]+$', '/3', img_src)
            if not url.endswith('/3'): url = f"{url.rstrip('/')}/3"
            scraped.append({"set_id": str(s_id), "id": str(v_id), "name": img.get('alt', s_id).strip(), "url": url})
    return scraped

def get_scraped_data():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        response = scraper.get(SOURCE_URL, headers=headers, timeout=20)
        if response.status_code == 403 or "cloudflare" in response.text.lower():
            html = get_scraped_data_playwright()
        else:
            response.raise_for_status()
            html = response.text
    except Exception:
        html = get_scraped_data_playwright()
    
    return parse_html(html) if html else []

def is_url_broken(url):
    try:
        response = requests.head(url, timeout=10, allow_redirects=True)
        return response.status_code != 200
    except: return True

def sync():
    try:
        db = {"global": []}
        if os.path.exists(JSON_FILE):
            with open(JSON_FILE, 'r', encoding='utf-8') as f:
                db = json.load(f)

        scraped = get_scraped_data()
        if not scraped: raise Exception("Scrape empty.")

        lookup = {(b['set_id'], str(b['id'])): b for b in scraped}
        changed, existing_combinations = False, set()

        for item in db.get("global", []):
            sid = str(item.get("set_id"))
            for v in item.get("versions", []):
                vid = str(v.get("id"))
                existing_combinations.add((sid, vid))
                if is_url_broken(v.get("image_url_1x")):
                    fresh = lookup.get((sid, vid))
                    if fresh:
                        v.update({"image_url_1x": fresh["url"], "image_url_2x": fresh["url"], "image_url_4x": fresh["url"]})
                        changed = True

        for b in scraped:
            sid, vid = str(b["set_id"]), str(b["id"])
            if (sid, vid) in existing_combinations: continue
            target = next((i for i in db["global"] if str(i["set_id"]) == sid), None)
            new_v = {"id": vid, "image_url_1x": b["url"], "image_url_2x": b["url"], "image_url_4x": b["url"]}
            if not target:
                db["global"].append({"set_id": sid, "versions": [new_v]})
                notify_discord(f"🚀 New Badge Set: `{b['name']}`", b["url"])
            else:
                target["versions"].append(new_v)
                notify_discord(f"✨ New Version Detected: `{sid}` ({vid})", b["url"])
            changed, existing_combinations.add((sid, vid))

        if changed:
            with open(JSON_FILE, 'w', encoding='utf-8') as f:
                json.dump(db, f, indent=4, ensure_ascii=False)
            print("Changes detected and saved.")
        else:
            print("No changes found.")
    except Exception as e:
        print(f"Error: {e}")
        raise

if __name__ == "__main__":
    sync()
