import os
import json
import feedparser
import requests

RSS_URL = (
    "https://forum.pirategalaxy.com/"
    "forums/news_and_announcements/index.rss"
)

STATE_FILE = "state.json"
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")


def load_state():
    if not os.path.exists(STATE_FILE):
        return set()

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
        return set(data.get("known_threads", []))
    except Exception as error:
        print(f"[WARNING] Could not read state file: {error}")
        return set()


def save_state(known_threads):
    with open(STATE_FILE, "w", encoding="utf-8") as file:
        json.dump(
            {"known_threads": sorted(known_threads)},
            file,
            indent=4
        )


def get_entry_id(entry):
    return (
        entry.get("id")
        or entry.get("guid")
        or entry.get("link")
    )


def get_feed():
    try:
        response = requests.get(RSS_URL, timeout=30)
        response.raise_for_status()
        feed = feedparser.parse(response.content)

        if feed.bozo:
            print("[WARNING] RSS feed returned a parsing warning.")

        return feed

    except requests.RequestException as error:
        print(f"[ERROR] Could not read RSS feed: {error}")
        return None


def send_to_discord(entry):
    title = entry.get("title", "Pirate Galaxy Announcement")
    link = entry.get("link", RSS_URL)
    author = entry.get("author", "Pirate Galaxy")
    published = entry.get("published", "")

    embed = {
        "title": f"📢 {title}",
        "url": link,
        "description": (
            "A new announcement has been posted on the "
            "official Pirate Galaxy forum."
        ),
        "fields": [
            {
                "name": "Posted by",
                "value": author,
                "inline": True
            },
            {
                "name": "Date",
                "value": published or "Unknown",
                "inline": True
            }
        ],
        "footer": {
            "text": "Pirate Galaxy News & Announcements"
        }
    }

    payload = {
        "username": "Pirate Galaxy News",
        "embeds": [embed]
    }

    try:
        response = requests.post(
            WEBHOOK_URL,
            json=payload,
            timeout=30
        )

        if response.status_code in (200, 204):
            print(f"[DISCORD] Successfully posted: {title}")
            return True

        print(
            f"[ERROR] Discord returned "
            f"{response.status_code}: {response.text}"
        )
        return False

    except requests.exceptions.Timeout:
        print("[ERROR] Discord request timed out.")
        print(
            "[WARNING] The message may or may not have reached Discord."
        )
        return False

    except requests.exceptions.RequestException as error:
        print(f"[ERROR] Could not contact Discord: {error}")
        return False


def check_for_new_threads():
    feed = get_feed()

    if not feed or not feed.entries:
        print("[INFO] RSS feed contains no entries or could not be read.")
        return False

    known_threads = load_state()

    current_ids = {
        get_entry_id(entry)
        for entry in feed.entries
        if get_entry_id(entry)
    }

    # First run: remember existing announcements without posting them.
    if not known_threads:
        save_state(current_ids)
        print("[INFO] First run / baseline created.")
        print(f"[INFO] Remembered {len(current_ids)} existing threads.")
        print("[INFO] Existing announcements will NOT be posted.")
        return True

    new_entries = [
        entry
        for entry in feed.entries
        if get_entry_id(entry) and get_entry_id(entry) not in known_threads
    ]

    if not new_entries:
        print("[INFO] No new announcements.")
        return True

    print(f"[INFO] Found {len(new_entries)} new thread(s).")

    # RSS is newest -> oldest; post oldest -> newest.
    new_entries.reverse()

    for entry in new_entries:
        entry_id = get_entry_id(entry)
        print(f"[NEW THREAD] {entry.get('title', 'Unknown')}")

        if send_to_discord(entry):
            known_threads.add(entry_id)
            save_state(known_threads)
        else:
            print("[WARNING] Thread was NOT marked as processed.")
            print("[WARNING] Stopping this run to avoid losing track.")
            return False

    return True


if __name__ == "__main__":
    print("=" * 60)
    print("Pirate Galaxy -> Discord News Notifier")
    print("=" * 60)
    print(f"RSS feed: {RSS_URL}")
    print("[INFO] Running one check, then exiting.")

    if not WEBHOOK_URL:
        raise SystemExit(
            "ERROR: DISCORD_WEBHOOK_URL GitHub Secret was not found."
        )

    if not check_for_new_threads():
        raise SystemExit(1)
