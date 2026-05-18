"""Poll public Instagram accounts and post new content to a Discord webhook."""

from __future__ import annotations

import itertools
import json
import os
import sys
from pathlib import Path

import instaloader
import requests

ACCOUNTS_FILE = Path("accounts.json")
STATE_FILE = Path("state.json")
SCAN_LIMIT = 20
CAPTION_LIMIT = 300
INSTAGRAM_BRAND_COLOR = 0xE4405F


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE_FILE.write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def truncate(text, limit: int) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def post_kind(post) -> str:
    if post.typename == "GraphSidecar":
        return "Carousel"
    if post.is_video:
        return "Reel / Video"
    return "Photo"


def build_embed(profile, post) -> dict:
    return {
        "url": f"https://www.instagram.com/p/{post.shortcode}/",
        "description": truncate(post.caption, CAPTION_LIMIT),
        "timestamp": post.date_utc.isoformat(),
        "color": INSTAGRAM_BRAND_COLOR,
        "author": {
            "name": f"@{profile.username}",
            "url": f"https://www.instagram.com/{profile.username}/",
            "icon_url": profile.profile_pic_url,
        },
        "image": {"url": post.url},
        "footer": {"text": f"Instagram · {post_kind(post)}"},
    }


def send_discord(webhook_url: str, embed: dict) -> None:
    response = requests.post(
        webhook_url,
        json={"embeds": [embed]},
        timeout=15,
    )
    response.raise_for_status()


def main() -> int:
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("ERROR: DISCORD_WEBHOOK_URL is not set", file=sys.stderr)
        return 2

    accounts = load_json(ACCOUNTS_FILE, [])
    if not accounts:
        print("No accounts configured in accounts.json")
        return 0
    state = load_json(STATE_FILE, {})

    loader = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        quiet=True,
    )

    successes = 0
    for username in accounts:
        try:
            profile = instaloader.Profile.from_username(loader.context, username)
            posts = list(itertools.islice(profile.get_posts(), SCAN_LIMIT))
        except Exception as exc:
            print(f"@{username}: ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
            continue

        last_seen = state.get(username, {}).get("last_seen_shortcode")
        latest_shortcode = posts[0].shortcode if posts else None

        if last_seen is None:
            state[username] = {"last_seen_shortcode": latest_shortcode}
            print(f"@{username}: bootstrapped (last={latest_shortcode})")
            successes += 1
            continue

        new_posts = []
        for post in posts:
            if post.shortcode == last_seen:
                break
            new_posts.append(post)
        new_posts.reverse()

        last_successful = last_seen
        for post in new_posts:
            try:
                send_discord(webhook_url, build_embed(profile, post))
                last_successful = post.shortcode
            except Exception as exc:
                print(
                    f"@{username}: failed to send {post.shortcode}: {exc}",
                    file=sys.stderr,
                )
                break

        state[username]["last_seen_shortcode"] = last_successful
        print(
            f"@{username}: {len(new_posts)} new (last={state[username]['last_seen_shortcode']})"
        )
        successes += 1

    save_state(state)

    if successes == 0:
        print("ERROR: no accounts successfully checked", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
