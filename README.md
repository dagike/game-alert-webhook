# game-alert-webhook

This bot posts a game deal summary to a Discord channel two times per day. It runs well on a Raspberry Pi 5 in Docker.

## What the summary contains

- Free games on Steam, Epic Games Store, and GOG.
- The newest PlayStation Plus Essential monthly games.
- New Fanatical bundles and sales promotions.
- Games from your wishlist that reach their all-time low price.

Each summary lists only items that are new since the last summary. A small SQLite file in `data/` remembers what the bot already sent.

## Data sources

- Epic Games Store: the official free games API.
- Steam and GOG giveaways: the GamerPower API. It needs no key.
- PlayStation Plus: the PlayStation Blog feed.
- Fanatical: the public JSON that the Fanatical website uses. Fanatical has no official API. If Fanatical changes its site, this source can break. The other sources keep working.
- Wishlist prices and all-time lows: the IsThereAnyDeal API. It needs a free key.

## What you need

- A Raspberry Pi 5 with Docker and Docker Compose. Compose version 2.24 or later is required.
- A Discord webhook URL.
- A free IsThereAnyDeal API key. You need it only for the wishlist.

## Set up on the Pi

### 1. Get a Discord webhook URL

1. Open the settings of your Discord channel.
2. Open Integrations, then Webhooks, then New Webhook.
3. Click Copy Webhook URL.

### 2. Get an IsThereAnyDeal API key

1. Go to https://isthereanydeal.com/apps/ and sign in.
2. Register a new app.
3. Copy the API key.

### 3. Download the project

```
git clone https://github.com/dagike/game-alert-webhook.git
cd game-alert-webhook
```

### 4. Add your secrets

```
cp .env.example .env
nano .env
```

Paste your webhook URL and your API key into `.env`. The file stays on your Pi. Git ignores it.

### 5. Add your configuration and wishlist

```
mkdir config data
cp config.example.yaml config/config.yaml
cp wishlist.yaml config/wishlist.yaml
nano config/wishlist.yaml
```

Write one game title per line in `config/wishlist.yaml`. Use the exact name that the store shows.

You must create the `data` folder yourself, as in the commands above. If it does not exist, Docker creates it as the root user, and the bot fails with the error `unable to open database file`. To repair this, run `sudo chown -R 1000:1000 data`.

### 6. Test without posting

```
docker compose run --rm gamealert python -m gamealert run-once --dry-run --config /config/config.yaml
```

The bot prints the summary in your terminal. It does not post to Discord and it does not save state.

### 7. Send a real test message

```
docker compose run --rm gamealert python -m gamealert run-once --config /config/config.yaml
```

This command posts to Discord. It also marks the listed items as sent, so the next summary does not repeat them.

### 8. Start the bot

```
docker compose up -d --build
```

The bot now runs at 09:00 and 21:00 in the `America/Toronto` time zone. The container restarts after a Pi reboot.

## Daily use

To read the log:

```
docker compose logs -f
```

To update the bot:

```
git pull
docker compose up -d --build
```

To stop the bot:

```
docker compose down
```

## Use the prebuilt image

GitHub Actions builds an image for the Pi (arm64) on every push to `main`. You can pull this image and skip the build on the Pi.

1. In `docker-compose.yml`, replace `build: .` and `image: game-alert-webhook` with `image: ghcr.io/dagike/game-alert-webhook:latest`.
2. Make the package public in the GitHub package settings. If you keep it private, you must run `docker login ghcr.io` on the Pi.
3. Run `docker compose pull`, then `docker compose up -d`.

## Configuration

Edit `config/config.yaml`, then restart with `docker compose restart`. The file `config.example.yaml` lists every option.

- `timezone`: the time zone name for the schedule. The default is `America/Toronto`.
- `run_times`: the times of day for the summary, in 24-hour `HH:MM` form. The default is two times, `09:00` and `21:00`.
- `country` and `currency`: the store region for wishlist prices. The default is `CA` and `CAD`.
- `post_when_empty`: if `true`, the bot posts a short "no new deals" line when nothing is new.
- `report_when_ok`: if `true`, the "Run status" box appears in every summary. If `false`, it appears only when a problem occurs.
- `wishlist_tolerance_percent`: if a price is within this percent of the all-time low, the bot sends an alert. The default is `0`, which means exactly at the low.
- `sources`: set one source to `false` to turn it off. The names are `free_games`, `ps_plus`, `fanatical`, and `wishlist`.

## Run status

Each summary ends with a "Run status" box. The box shows how many sources worked, how many new items the bot found, and how long the run took.

The color of the box shows the result:

- Green: all sources worked.
- Yellow: all sources worked, but the bot found a problem. For example, a wishlist title is not on IsThereAnyDeal.
- Red: at least one source failed. The box names the source and the error.

If a source fails, the other sources still post. If the whole run fails, the bot posts a short red "Run failed" message. If Discord itself is down, the bot cannot post, and the error appears only in `docker compose logs`.

The bot removes your API key and your webhook URL from the status box and from the log.

## What to expect

- On the first run, the summary lists all current Fanatical promotions, for example the long-running mystery game promotion. Later summaries list only new ones.
- Some Steam giveaways have conditions, for example a key that needs reward points from a partner site. GamerPower lists them as free, and so does the bot.
- When Sony publishes the post for a new month, the bot lists it. Sony usually publishes it near the end of the previous month.
- If one source fails, the other sources still post.

## Development

```
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
.venv/bin/ruff check .
```

The tests use saved sample data and need no network.

## License

MIT
