"""Measure lookup latency against a running lookup service.

Sends sequential GETs over one keep-alive connection and reports percentiles. The timings are as seen
by this client, so they include client overhead and are an upper bound on service-side latency.

Usage (from lookup_service/, with the service running, e.g. via `docker compose --profile lookup up`):
    uv run python scripts/latency_check.py --url http://localhost:8090 --requests 5000
"""

from __future__ import annotations

import argparse
import http.client
import statistics
import sys
import time
import urllib.parse

DEFAULT_PATHS = [
    "/api/v1/lookup/health_board_mapping?k=224",
    "/api/v1/lookup/ward_map?k=FAC1&k=W2",
]
WARMUP_REQUESTS = 200


def run(base_url: str, paths: list[str], total: int) -> int:
    parsed = urllib.parse.urlsplit(base_url)
    if parsed.scheme != "http" or not parsed.hostname:
        raise SystemExit("--url must be an http:// URL, e.g. http://localhost:8090")
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=5)

    def get(path: str) -> int:
        connection.request("GET", path)
        response = connection.getresponse()
        response.read()
        return response.status

    for i in range(WARMUP_REQUESTS):
        get(paths[i % len(paths)])

    timings_ms: list[float] = []
    failures = 0
    started = time.perf_counter()
    for i in range(total):
        request_started = time.perf_counter()
        if get(paths[i % len(paths)]) != 200:
            failures += 1
        timings_ms.append((time.perf_counter() - request_started) * 1000)
    elapsed = time.perf_counter() - started
    connection.close()

    centiles = statistics.quantiles(timings_ms, n=100)
    print(f"requests={total} failures={failures} throughput={total / elapsed:.0f} req/s (sequential)")
    print(f"p50={centiles[49]:.2f}ms p95={centiles[94]:.2f}ms p99={centiles[98]:.2f}ms max={max(timings_ms):.2f}ms")
    return 1 if failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://localhost:8090", help="Service base URL")
    parser.add_argument("--requests", type=int, default=5000, help="Number of timed requests")
    parser.add_argument("--path", action="append", help="Lookup path to request (repeatable)")
    args = parser.parse_args()
    if args.requests < 100:
        parser.error("--requests must be at least 100 for meaningful percentiles")
    sys.exit(run(args.url, args.path or DEFAULT_PATHS, args.requests))


if __name__ == "__main__":
    main()
