# Deployment

## From published images

```bash
echo 'MAPILLARY_TOKEN=MLY|your|token' > .env
docker compose up -d
```

| Variable | Default | Meaning |
|---|---|---|
| `MAPILLARY_TOKEN` | — | Required. Imagery and detections. |
| `POSTGRES_USER` / `_PASSWORD` / `_DB` | `mithra` | Database credentials |
| `CORS_ORIGINS` | `http://localhost:3000` | Where the console is served from |
| `API_PORT` / `WEB_PORT` | `8020` / `3000` | Host ports |
| `MITHRA_PROBE_PATH` | unset | Promote a trained classifier |

Migrations run as their own one-shot service rather than on API start, so two API
replicas starting together do not race the same migration.

## The one build-time value

`NEXT_PUBLIC_API_URL` is inlined into the client bundle by Next at build time. Setting
it at runtime does nothing — the browser will call whatever host was baked in.

```bash
docker build -f Dockerfile.web \
  --build-arg NEXT_PUBLIC_API_URL=https://api.example.org \
  -t mithra-web .
```

Getting this wrong is silent: the console loads, then every request fails against a
host that is not there. The console shows a banner naming the address it cannot
reach, precisely because this failure otherwise looks like loading forever.

## Volumes

| Volume | Holds | Losing it costs |
|---|---|---|
| `db` | Everything | Everything |
| `crops` | Sign crops | The evidence behind every count, and the training set |
| `models` | Trained probes, downloaded model weights | A retrain, and a few hundred MB re-downloaded |
| `redis` | Queue state | In-flight surveys |

Crops matter more than they look: they are what makes a count auditable, and they are
the training data for the classifier that replaces the zero-shot one.

### Upgrading a deployment made before model weights were cached

Earlier images did not create `/app/models`, so Docker created the volume as
root and the application user could not write to it. Weights were re-downloaded
on every run until they hit that wall. New deployments are fine; an existing one
needs its volume handed over once:

```bash
docker compose run --rm --user root worker chown -R 10001:999 /app/models
```

Without it, any detector that downloads weights fails with a permission error
the first time it is used — not at startup, which is what makes it worth doing
before the next run rather than after.

## Behind TLS

Set `secure` on the session cookie (`services/api/mithra_api/auth.py`) and point
`CORS_ORIGINS` at the console's real origin.

## Upgrading with tabs open

An operator watching a survey keeps a tab open for hours. After a deploy, that tab
holds a client bundle that no longer exists on the server: its next navigation asks
for a chunk that is gone, nothing throws, and the page appears to hang.

The console handles this. It stamps the build it was served, asks the server what is
running, and when they disagree the next link click becomes a full page load rather
than a client-side navigation. No action needed at deploy time.
