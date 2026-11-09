"""SaskAir Watch - Query Lambda (Sprint 2).

Behind API Gateway (REST API, Lambda proxy integration):
  GET /latest?city=saskatoon            -> most recent clean reading
  GET /history?city=saskatoon&hours=24  -> hourly readings + daily averages
"""
import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",   # the Sprint 3 dashboard calls this from the browser
    "Access-Control-Allow-Methods": "GET,OPTIONS",
}
MAX_HOURS = 168  # 7 days


def plain(value):
    """Convert DynamoDB Decimals back to normal ints/floats for JSON."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [plain(v) for v in value]
    return value


def respond(status, body):
    return {"statusCode": status, "headers": HEADERS, "body": json.dumps(body)}


def get_latest(table, city):
    res = table.query(
        KeyConditionExpression="city = :c",
        ExpressionAttributeValues={":c": city},
        ScanIndexForward=False,
        Limit=1,
    )
    items = res.get("Items", [])
    return plain(items[0]) if items else None


def get_history(table, city, since):
    items, kwargs = [], {
        "KeyConditionExpression": "city = :c AND #ts >= :since",
        "ExpressionAttributeNames": {"#ts": "timestamp"},  # "timestamp" is a reserved word in DynamoDB
        "ExpressionAttributeValues": {":c": city, ":since": since},
        "ScanIndexForward": True,
    }
    while True:
        res = table.query(**kwargs)
        items.extend(res.get("Items", []))
        if "LastEvaluatedKey" not in res:
            return plain(items)
        kwargs["ExclusiveStartKey"] = res["LastEvaluatedKey"]


def _avg(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 1) if values else None


def daily_averages(readings):
    """Group hourly readings by local date and work out the daily numbers."""
    days = {}
    for r in readings:
        day = (r.get("local_time") or r["timestamp"])[:10]
        days.setdefault(day, []).append(r)
    out = []
    for day in sorted(days):
        rows = days[day]
        temps = [r.get("temperature_c") for r in rows if r.get("temperature_c") is not None]
        aqis = [r.get("us_aqi") for r in rows if r.get("us_aqi") is not None]
        out.append({
            "date": day,
            "readings": len(rows),
            "avg_temperature_c": _avg(temps),
            "min_temperature_c": min(temps) if temps else None,
            "max_temperature_c": max(temps) if temps else None,
            "avg_us_aqi": _avg(aqis),
            "max_us_aqi": max(aqis) if aqis else None,
            "avg_pm2_5": _avg([r.get("pm2_5") for r in rows]),
        })
    return out


def lambda_handler(event, context, table=None, now=None):
    event = event or {}
    path = event.get("resource") or event.get("path") or ""
    params = event.get("queryStringParameters") or {}
    city = (params.get("city") or "saskatoon").strip().lower()

    if table is None:
        import boto3
        table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])

    if path.endswith("/latest"):
        latest = get_latest(table, city)
        if latest is None:
            return respond(404, {"message": f"No data yet for {city}"})
        return respond(200, latest)

    if path.endswith("/history"):
        try:
            hours = int(params.get("hours", 24))
        except ValueError:
            return respond(400, {"message": "hours must be a whole number"})
        if not 1 <= hours <= MAX_HOURS:
            return respond(400, {"message": f"hours must be between 1 and {MAX_HOURS}"})
        now = now or datetime.now(timezone.utc)
        since = (now - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:00:00Z")
        readings = get_history(table, city, since)
        return respond(200, {
            "city": city,
            "hours": hours,
            "count": len(readings),
            "readings": readings,
            "daily_averages": daily_averages(readings),
        })

    return respond(404, {"message": "Use /latest or /history"})
