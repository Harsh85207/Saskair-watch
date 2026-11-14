"""Live API tests (SA-11): calls the real REST API after every deploy.

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


def post(url, body):
    req = urllib.request.Request(url, data=body.encode(), method="POST", headers={"Content-Type": "text/plain"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
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

    status, _, _ = post(f"{base}/subscribe", '{"email": "not-an-email"}')
    check("/subscribe rejects a bad email with 400", status == 400)

    total = 7
    print(f"\n{total - len(failures)} of {total} API checks passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main(sys.argv[1])
