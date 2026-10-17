# Rate limiting

`/v1/*` routes are protected by an in-process token bucket
(`app/core/ratelimit.py`).

## Config (`.env`)

```env
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS=30        # bucket capacity
RATE_LIMIT_WINDOW_SECONDS=60  # time to fully refill the bucket
```

With the defaults, a caller gets 30 requests up front, refilling continuously
at 1 every 2 seconds, up to a cap of 30.

## Key
Each caller is tracked separately: by their bearer token when `GTG_API_KEY`
is set, otherwise by client IP. This means one noisy IP or key can't starve
others.

## Behavior at the limit
A `429` is returned with the standard error envelope and a `Retry-After`
header (seconds, rounded up) telling the client when it'll have a token
again.

## Limitations
- **In-memory, per-process.** If you run more than one uvicorn worker or
  replica, each enforces its own independent limit — effective capacity is
  multiplied by the worker count. For a shared limit across processes, swap
  the bucket storage in `app/core/ratelimit.py` for Redis or similar.
- Buckets are pruned periodically but not persisted; a restart resets
  everyone's bucket.
- This is abuse protection for a self-hosted gateway, not a billing-grade
  quota system.

`config/nginx.conf.example` shows a coarser second layer (`limit_req`) you
can put in front of this if you're exposing the gateway beyond localhost.
