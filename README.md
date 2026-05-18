# instabot

A free, self-hosted Discord notifier for new Instagram posts and reels from public accounts. Removes the paywall behind a feature that RSS.app, MEE6, and similar services lock to paid tiers.

Designed for personal/private-server use. Runs entirely on GitHub Actions cron — no VM, no Discord bot account, no Instagram login.

## How it works

A GitHub Actions workflow runs `check.py` every 15 minutes. The script:

1. Reads the watched-accounts list from [accounts.json](accounts.json).
2. Anonymously scrapes each profile's recent posts via [Instaloader](https://instaloader.github.io/).
3. Compares against the last-seen post per account stored in [state.json](state.json).
4. Posts new content to a Discord channel via a webhook (URL kept in a repo secret).
5. Commits the updated `state.json` back to the repo so the next run knows where it left off.

## Setup

1. **Fork or clone this repo into your own GitHub account.**
2. **Create a Discord webhook** in the target channel:
   - Channel settings → Integrations → Webhooks → New Webhook → Copy URL.
3. **Add the webhook URL as a repo secret:**
   - Repo Settings → Secrets and variables → Actions → New repository secret.
   - Name: `DISCORD_WEBHOOK_URL`. Value: the webhook URL.
4. **Pick the accounts to watch.** Edit [accounts.json](accounts.json):
   ```json
   ["nasa", "natgeo"]
   ```
   Usernames only — no `@`, no URLs.
5. **Commit and push.** The workflow will start firing on its 15-minute cron. You can also run it on demand from the Actions tab → "instabot" → "Run workflow".

## First run behavior

The first time the workflow sees a new username, it records that account's latest post as the bootstrap point and sends **nothing** to Discord. This prevents the bot from spamming old posts when you first add an account. The next run onward, any new posts after that bootstrap point are posted to Discord.

To "force" a backfill of a few posts after the first run, edit `state.json` and roll the account's `last_seen_shortcode` back to an older post's shortcode (the part of an IG URL between `/p/` and the trailing slash, e.g. `https://www.instagram.com/p/Cabc123XYZ/` → `Cabc123XYZ`).

## Local smoke test

```sh
pip install -r requirements.txt
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
python check.py
```

On Windows PowerShell:

```powershell
pip install -r requirements.txt
$env:DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/..."
python check.py
```

## Known limitations (v1)

- Anonymous Instagram scraping may break if Meta tightens public-feed access further. If that happens, the fix is to log in with a throwaway IG account (store credentials as repo secrets and add an `L.login(...)` call). Not implemented in v1.
- Stories are not supported (would require login).
- All watched accounts post to a single channel (per-account routing is a future feature).
- No `@role` mentions.
- Discord embeds depend on Instagram's signed CDN URLs for thumbnails; these occasionally fail to render. The post link in the embed always works.

## Files

- [check.py](check.py) — single-file scraper + notifier.
- [requirements.txt](requirements.txt) — Python dependencies.
- [accounts.json](accounts.json) — list of Instagram usernames to watch.
- [state.json](state.json) — last-seen post per watched account. Mutated by the workflow.
- [.github/workflows/check.yml](.github/workflows/check.yml) — cron workflow.
