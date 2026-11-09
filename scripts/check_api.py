"""Sprint 2 API tests (SA-11): calls the live REST API after every deploy.

Usage: python scripts/check_api.py https://<api-id>.execute-api.<region>.amazonaws.com/prod
"""
import json
import sys
import urllib.error
import urllib.request


def get(url):
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return r.status, json.loads(r.read()), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}"), dict(e.headers)


def main(base):
    base = base.rstrip("/")
    failures = []

    def check(name, ok):
        print(("PASS " if ok else "FAIL ") + name)
        if not ok:
            failures.append(name)

    status, body, headers = get(f"{base}/latest")
    print("/latest ->", status, json.dumps(body)[:300])
    check("/latest returns 200", status == 200)
    check("/latest has us_aqi and temperature_c", "us_aqi" in body and "temperature_c" in body)
    check("/latest allows the dashboard (CORS)", headers.get("Access-Control-Allow-Origin") == "*")

    status, body, _ = get(f"{base}/history?hours=24")
    print("/history ->", status, "count =", body.get("count"))
    check("/history returns 200", status == 200)
    check("/history has readings and daily_averages",
          isinstance(body.get("readings"), list) and isinstance(body.get("daily_averages"), list))

    status, _, _ = get(f"{base}/history?hours=abc")
    check("/history rejects a bad hours value with 400", status == 400)

    print(f"\n{6 - len(failures)} of 6 API checks passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main(sys.argv[1])
