# Mithra on the demo server

Written for a host that already runs the shared nginx container from
`/root/docker-compose.yml`, with one config file per product in
`/root/nginx_config/conf.d/`.

Mithra differs from the static frontends in that deployment in one way worth
knowing before you start: **the console is a server, not a folder of files.** It
renders each page per request, so it is proxied like `ai.geotajak.ir` rather
than mounted into nginx as a volume. Nothing needs to be added to the nginx
container's volume list.

## What runs, and where the state lives

Six containers, from two images built out of this repository:

| Container | From | What it is |
|---|---|---|
| `web` | `mithra-web:local` | The console (Next.js server) |
| `api` | `mithra-api:local` | The HTTP API |
| `worker` | `mithra-api:local` | Runs detections off the queue |
| `migrate` | `mithra-api:local` | Runs once at startup, then exits |
| `db` | `postgis/postgis:16-3.4` | PostgreSQL + PostGIS |
| `redis` | `redis:7-alpine` | The job queue |

**The code is baked into the images, not mounted.** A deployment therefore
cannot drift from what was built, and changing code means rebuilding. Only data
is on named volumes:

| Volume | Holds | Losing it costs |
|---|---|---|
| `db` | The inventory, accounts, audit log | Everything |
| `crops` | The image behind every street detection | The evidence, and the training set |
| `models` | Downloaded model weights (~500 MB) | A re-download on the next run |
| `redis` | Queue state | Detections that were mid-flight |

## Install

```bash
cd /root
git clone https://github.com/itsmadson/Mithra.git mithra
cd mithra

cp deploy/.env.production.example .env
$EDITOR .env          # at minimum: BIND_ADDR, DB_PASSWORD, MAPILLARY_TOKEN
```

`BIND_ADDR` is the one people get wrong. nginx runs in a container, so
`127.0.0.1` there means the nginx container, not the host. Set it to the host
address the other products are already proxied to — `185.53.142.74` in this
deployment.

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml build
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Migrations run automatically before the API starts; there is no separate step.
Expect the first build to take several minutes — the API image installs PyTorch
and DeepForest.

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
curl -s http://185.53.142.74:8092/api/health     # {"status":"ok"}
```

Set the compose file pair once and you can drop it from every later command:

```bash
echo 'COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml' >> .env
```

## nginx

```bash
cp /root/mithra/deploy/nginx/mithra.conf /root/nginx_config/conf.d/mithra.conf
$EDITOR /root/nginx_config/conf.d/mithra.conf   # server_name, and the two upstream addresses

docker exec nginx nginx -t && docker exec nginx nginx -s reload
```

The file expects `includes/ssl-geotajak.conf` and `includes/proxy-headers.conf`,
which are already there. If the certificate for this hostname does not exist
yet, issue it the way the other hosts were issued before reloading — `nginx -t`
passes on a missing certificate and the reload then fails.

Two locations, and the order matters: `/api/` goes to the API, everything else
to the console. `client_max_body_size` is 512M because uploading a GeoTIFF is a
supported way to give Mithra imagery.

## The first account

Open `https://mithra.geotajak.ir`. **The first account created becomes the
administrator and brings the organisation into being; registration then closes**
— afterwards only an administrator can add people, from Settings. There is no
default password to change, and no way to create the first account except being
first.

Do this immediately after the stack comes up, before the URL is shared.

## Checking it actually works

Signing in is not proof the pipeline runs — that only proves the API and the
database are talking. A detection exercises the worker, the imagery source and
the model:

```bash
# From Detect, draw a box over a river and run water on Sentinel-2. Or:
docker compose exec worker python -c "
from mithra_worker.raster_pipeline import detect_over_area
found, prov = detect_over_area('sentinel2', {}, (48.62, 31.25, 48.76, 31.39), ['water'], 'ndwi-water')
print(len(found), 'water bodies at', round(prov['gsd_m']), 'm/pixel')"
```

The first run of any model downloads its weights into the `models` volume, so it
is slower than every run after it.

## Upgrading

```bash
cd /root/mithra
git pull
docker compose build
docker compose up -d
```

Migrations run on start. The console's API address is baked in at build time,
so a change to `PUBLIC_API_ORIGIN` needs `docker compose build web`, not just a
restart.

Operators with a tab open across a deploy are detected and reloaded rather than
left on a build that no longer exists.

## Things that will bite

- **`SESSION_COOKIE_SECURE=true` with plain HTTP.** Sign-in appears to succeed
  and the next request is unauthenticated, because the browser accepted the
  cookie and will not send it back over HTTP. Symptom: an immediate bounce back
  to the sign-in page.
- **`BIND_ADDR=127.0.0.1` with a containerised nginx.** 502 on every request;
  nginx is trying to reach itself.
- **A models volume from an older deployment.** Images before this release did
  not create `/app/models`, so Docker made it owned by root and no model could
  cache its weights. It fails during a run, not at startup:
  ```bash
  docker compose run --rm --user root worker chown -R 10001:999 /app/models
  ```
- **No Mapillary token.** Satellite, tile and uploaded imagery all work without
  one; street panoramas do not, and the failure is at run time.
- **A tile service that serves a drawn map.** Detection over cartography is
  refused when the run is created, because a model finds nothing in a rendering
  of a place. Declare tile services as photographs or as maps.

## Backup

The database is the one thing that cannot be rebuilt:

```bash
docker compose exec -T db pg_dump -U mithra mithra | gzip > mithra-$(date +%F).sql.gz
```

Crops are worth keeping too — they are the evidence behind every street
detection and the training data for the classifier that replaces the zero-shot
one:

```bash
docker run --rm -v mithra_crops:/crops -v "$PWD":/backup alpine \
  tar czf /backup/mithra-crops-$(date +%F).tar.gz -C /crops .
```
