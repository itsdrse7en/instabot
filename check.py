"""Poll the Instagram Graph API for new media and post to a Discord webhook.

The connected Instagram account is identified by the access token. The token is
auto-refreshed (long-lived tokens last 60 days; we refresh after 30) and stored
back into state.json so subsequent runs use the rotated token. The bootstrap
token comes from the INSTAGRAM_ACCESS_TOKEN env var on the first run.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

STATE_FILE = Path("state.json")
SCAN_LIMIT = 25
CAPTION_LIMIT = 300
INSTAGRAM_BRAND_COLOR = 0xE4405F
GRAPH_API_BASE = "https://graph.instagram.com/v22.0"
REFRESH_AFTER_DAYS = 30


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


def post_kind(media: dict) -> str:
    if media.get("media_product_type") == "REELS":
        return "Reel"
    media_type = media.get("media_type")
    if media_type == "CAROUSEL_ALBUM":
        return "Carousel"
    if media_type == "VIDEO":
        return "Video"
    return "Photo"


def build_embed(profile: dict, media: dict) -> dict:
    image_url = media.get("thumbnail_url") or media.get("media_url") or ""
    return {
        "url": media.get("permalink", ""),
        "description": truncate(media.get("caption"), CAPTION_LIMIT),
        "timestamp": media.get("timestamp", ""),
        "color": INSTAGRAM_BRAND_COLOR,
        "author": {
            "name": f"@{profile['username']}",
            "url": f"https://www.instagram.com/{profile['username']}/",
            "icon_url": profile.get("profile_picture_url", ""),
        },
        "image": {"url": image_url},
        "footer": {"text": f"Instagram · {post_kind(media)}"},
    }


def send_discord(webhook_url: str, embed: dict) -> None:
    response = requests.post(
        webhook_url,
        json={"embeds": [embed]},
        timeout=15,
    )
    response.raise_for_status()


def graph_get(path: str, token: str, **params) -> dict:
    params["access_token"] = token
    response = requests.get(f"{GRAPH_API_BASE}{path}", params=params, timeout=15)
    response.raise_for_status()
    return response.json()


def refresh_token(token: str) -> dict:
    response = requests.get(
        f"{GRAPH_API_BASE}/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": token},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def main() -> int:
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("ERROR: DISCORD_WEBHOOK_URL is not set", file=sys.stderr)
        return 2

    state = load_json(STATE_FILE, {})
    auth = state.get("auth", {})
    token = auth.get("access_token") or os.environ.get("INSTAGRAM_ACCESS_TOKEN")
    if not token:
        print(
            "ERROR: no access token. Set INSTAGRAM_ACCESS_TOKEN secret for the first run.",
            file=sys.stderr,
        )
        return 2

    last_refresh = auth.get("refreshed_at")
    needs_refresh = True
    if last_refresh:
        try:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(last_refresh)
            needs_refresh = age.days >= REFRESH_AFTER_DAYS
        except ValueError:
            pass

    if needs_refresh:
        try:
            payload = refresh_token(token)
            token = payload["access_token"]
            auth = {
                "access_token": token,
                "refreshed_at": datetime.now(timezone.utc).isoformat(),
                "expires_in": payload.get("expires_in"),
            }
            state["auth"] = auth
            print(f"Refreshed access token (expires_in={payload.get('expires_in')}s)")
        except Exception as exc:
            print(f"WARNING: token refresh failed, using existing token: {exc}", file=sys.stderr)

    try:
        profile = graph_get(
            "/me",
            token,
            fields="id,username,profile_picture_url,account_type",
        )
        media_response = graph_get(
            "/me/media",
            token,
            fields="id,caption,media_type,media_product_type,media_url,permalink,thumbnail_url,timestamp",
            limit=SCAN_LIMIT,
        )
        media = media_response.get("data", [])
    except Exception as exc:
        print(f"ERROR fetching from Graph API: {exc}", file=sys.stderr)
        save_state(state)
        return 1

    username = profile["username"]
    state.setdefault("accounts", {})
    last_seen = state["accounts"].get(username, {}).get("last_seen_id")

    if last_seen is None:
        latest_id = media[0]["id"] if media else None
        state["accounts"][username] = {"last_seen_id": latest_id}
        print(f"@{username}: bootstrapped (last={latest_id})")
        save_state(state)
        return 0

    new_media = []
    for item in media:
        if item["id"] == last_seen:
            break
        new_media.append(item)
    new_media.reverse()

    last_successful = last_seen
    for item in new_media:
        try:
            send_discord(webhook_url, build_embed(profile, item))
            last_successful = item["id"]
        except Exception as exc:
            print(f"@{username}: failed to send {item['id']}: {exc}", file=sys.stderr)
            break

    state["accounts"][username]["last_seen_id"] = last_successful
    print(f"@{username}: {len(new_media)} new (last={last_successful})")
    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
