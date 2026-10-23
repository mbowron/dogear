# Installing Dogear

Dogear runs as two Docker containers: **dogear** (the app) and **tailscale**
(gives it an HTTPS address that only your devices can reach). HTTPS matters:
browsers only keep the screen awake and show timer notifications on secure
pages.

These steps are written for an Odroid running CoreELEC with the Docker add-on,
where everything lives under `/storage`. On any other Linux box, swap
`/storage/dogear` for a folder of your choice, or use `deploy/compose.yaml`.

The image is built for 64-bit ARM and x86 (`linux/arm64`, `linux/amd64`).

## 1. Folders

SSH into the Odroid (`ssh root@<odroid-ip>`) and run:

```sh
mkdir -p /storage/dogear/recipes /storage/dogear/data \
         /storage/dogear/tailscale /storage/dogear/tailscale-config
chown -R 1000:1000 /storage/dogear/recipes /storage/dogear/data
docker network create dogear
```

The app runs as user 1000, so it needs to own the recipes and data folders.

## 2. Recipes

Copy your `.md` recipe files into `/storage/dogear/recipes`, for example from
a Mac:

```sh
scp my-recipes/*.md root@<odroid-ip>:/storage/dogear/recipes/
ssh root@<odroid-ip> chown -R 1000:1000 /storage/dogear/recipes
```

With CoreELEC's Samba share turned on, the folder is also reachable from
Finder at `smb://<odroid-ip>/storage/dogear/recipes`, and edits show up in the
app on the next page load.

## 3. Dogear

```sh
docker run -d --name dogear --network dogear --restart unless-stopped \
  -v /storage/dogear/recipes:/recipes \
  -v /storage/dogear/data:/data \
  -p 8000:8000 \
  ghcr.io/mbowron/dogear:latest
```

Check it: `curl http://localhost:8000/api/health`. It is now at
`http://<odroid-ip>:8000` on your home network (plain HTTP, so no screen
wake lock there).

## 4. Tailscale

1. In the Tailscale admin console, open **DNS** and turn on **MagicDNS** and
   **HTTPS Certificates**.
2. Under **Settings → Keys**, generate an auth key (reusable off, expiry is
   fine since the node stays logged in).
3. Copy `deploy/serve.json` from this repo to
   `/storage/dogear/tailscale-config/serve.json`.
4. Run, with your key in place of `tskey-auth-...`:

```sh
docker run -d --name dogear-tailscale --network dogear --restart unless-stopped \
  -e TS_AUTHKEY=tskey-auth-... \
  -e TS_HOSTNAME=dogear \
  -e TS_STATE_DIR=/var/lib/tailscale \
  -e TS_SERVE_CONFIG=/config/serve.json \
  -v /storage/dogear/tailscale:/var/lib/tailscale \
  -v /storage/dogear/tailscale-config:/config:ro \
  tailscale/tailscale:latest
```

Dogear is now at `https://dogear.<your-tailnet>.ts.net` from any device
signed in to your tailnet, at home or away. The first visit can take a few
seconds while the certificate is issued.

On an iPad or iPhone, open that address in Safari and use **Share → Add to
Home Screen** to get a full-screen app.

## Updating

```sh
docker pull ghcr.io/mbowron/dogear:latest
docker rm -f dogear
# then the docker run command from step 3 again
```

Recipes and the cook log live in the mounted folders, so nothing is lost.

## Backups

Back up `/storage/dogear/recipes` (your recipes) and
`/storage/dogear/data/dogear.db` (ratings and cook log).

## Running without Docker

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
python -m dogear serve --recipes path/to/recipes --data path/to/data
```
