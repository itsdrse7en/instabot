# instabot

A free, self-hosted Discord notifier for new posts and reels from an Instagram Creator/Business account you own. Removes the paywall on a feature that RSS.app, MEE6, and similar services lock to paid tiers.

Designed for personal/private-server use. Runs entirely on GitHub Actions cron — no VM, no Discord bot account, no scraping.

## How it works

A GitHub Actions workflow runs `check.py` every 15 minutes. The script:

1. Reads the Instagram access token (and last-seen post id) from [state.json](state.json).
2. Calls the **Instagram Graph API** to list the connected account's recent media.
3. Compares against the last-seen post id and posts new media to a Discord channel via a webhook.
4. Auto-refreshes the access token when it's more than 30 days old (long-lived tokens expire after 60 days). The rotated token is written back into `state.json`, so steady-state operation needs zero manual intervention.

The "connected account" is whichever Instagram account authorized the Meta Developer App. To monitor a different account, repeat the auth flow with that account and replace the bootstrap token.

## One-time setup

### 1. Convert the Instagram account to Professional (Creator)

In the Instagram mobile app:

- Settings and activity → Account type and tools → Switch to professional account.
- Pick a category. Choose **Creator** (Business requires a connected Facebook Page, which we don't need).

### 2. Create a Meta Developer App

- Go to `https://developers.facebook.com/apps/` and sign in.
- Create app → **Other** → **Business** type → name it whatever.
- In the app dashboard: **Add products** → **Instagram** → **Set up**.
- Use the **Instagram business login** flow (NOT Facebook Login).
- Add your Instagram account: log in when prompted, authorize the app.
- Generate a **long-lived access token** for the account. Copy it — it starts with `IGQVJ...`.

### 3. Set up the Discord webhook

- In Discord: right-click your target channel → Edit Channel → Integrations → Webhooks → New Webhook → Copy URL. Treat the URL as a password.

### 4. Add repo secrets

In this repo on github.com: Settings → Secrets and variables → Actions → **New repository secret**:

| Name | Value |
|---|---|
| `DISCORD_WEBHOOK_URL` | The webhook URL from step 3 |
| `INSTAGRAM_ACCESS_TOKEN` | The token from step 2 |

### 5. Bootstrap run

- Actions tab → **instabot** → **Run workflow** → from `main`.
- Watch the log. First run should log `bootstrapped (last=<id>)` and send nothing to Discord. A follow-up commit (`chore: update state [skip ci]`) saves the token + last-seen-id into `state.json`.
- The 15-minute cron now takes over. New posts on the connected account land in Discord within ~15 min of being published.

## Verifying delivery without waiting for a real post

After the bootstrap run completes:

1. Edit `state.json` on github.com (pencil icon).
2. Change `accounts.<username>.last_seen_id` to `"AAA"` (or any non-matching value). Commit.
3. Re-run the workflow manually. It'll find no match in recent media, treat the recent ~25 posts as new, and dump them all to Discord.
4. The next real post is then detected against the new last-seen-id normally.

## Token lifecycle

- Tokens are valid for 60 days.
- The script auto-refreshes the token if it's older than 30 days, rotating it every run thereafter.
- The new token is committed to `state.json` after each refresh.
- **If you don't run the workflow for 60+ days,** the token expires and the workflow will fail with an auth error. Fix: generate a fresh token in the Meta developer console and overwrite the `INSTAGRAM_ACCESS_TOKEN` secret. Clear the `auth` block in `state.json` (so the script picks up the secret again on the next run).

## Files

- [check.py](check.py) — Graph API client + Discord webhook poster.
- [requirements.txt](requirements.txt) — just `requests`.
- [state.json](state.json) — auth token + last-seen post id. Mutated by the workflow.
- [.github/workflows/check.yml](.github/workflows/check.yml) — cron workflow.

## Out of scope (v1)

- Stories (would need `instagram_business_manage_insights` and additional setup).
- Multiple Instagram accounts (each would need its own token; would require restructuring `state.json`).
- Per-account Discord channel routing.
- `@role` mentions on new posts.

## Why this is durable

Earlier iterations of this bot tried anonymous scraping (Instaloader) and cookie-based auth. Both work briefly and then break — Instagram actively blocks anonymous scrapers from cloud IPs, and session cookies expire or get flagged. The Graph API path is officially sanctioned by Meta: as long as the developer app exists, the token gets refreshed, and the account remains a Creator/Business account, this will keep working without intervention.
