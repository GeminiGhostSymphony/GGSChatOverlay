# GGS Chat Overlay - Global Badge Tracker

This repository contains an automated system to track and update Twitch Global Badges, including event-specific and limited-time badges.

## How it Works
1. **Scraping:** A Python script runs every 15 minutes via GitHub Actions.
2. **Detection:** It scrapes StreamDatabase to find new `set_id`s or `version`s.
3. **High Resolution:** It automatically converts Twitch CDN URLs to Size 3 (72x72px) for maximum quality.
4. **Data Integrity:**
   - Existing badges (including legacy ImgBB links) are preserved.
   - New badges are appended using `1x`, `2x`, and `4x` keys for high-DPI support.
5. **Discord Alerts:** Whenever a new badge is added, a notification is sent to a private Discord channel via Webhook.

## Setup (Admin Only)
To maintain the automation:
- Ensure the `DISCORD_WEBHOOK` is added to the repository **Secrets** (Settings > Secrets and variables > Actions).
- Do not change the root key `global` in `global-badges.json`, as the script relies on this structure for safety.
