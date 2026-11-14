"""SaskAir Watch - Ingest Lambda.

Runs every hour (EventBridge). Calls the free Open-Meteo weather and
air quality REST APIs for one city, saves the raw JSON to S3 (Sprint 1),
then cleans the data and saves one record per hour in DynamoDB (Sprint 2),
and sends an SNS email alert when conditions become unsafe (Sprint 3).
"""
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

WEATHER_FIELDS = "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m"
AIR_FIELDS = "us_aqi,pm2_5,pm10"


def build_urls(lat, lon, tz="America/Regina"):
    """Return the two Open-Meteo request URLs for a location."""
    weather = WEATHER_URL + "?" + urllib.parse.urlencode(
        {"latitude": lat, "longitude": lon, "current": WEATHER_FIELDS, "timezone": tz}
    )
    air = AIR_URL + "?" + urllib.parse.urlencode(
        {"latitude": lat, "longitude": lon, "current": AIR_FIELDS, "timezone": tz}
    )
    return weather, air


def fetch_json(url, retries=3, wait_seconds=2, opener=urllib.request.urlopen):
    """GET a URL and return parsed JSON. Retries a few times before giving up."""
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            with opener(url, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as err:  # network error, timeout, bad JSON
            last_error = err
            print(f"Attempt {attempt}/{retries} failed for {url}: {err}")
            if attempt < retries:
                time.sleep(wait_seconds)
    raise RuntimeError(f"Could not fetch {url} after {retries} tries") from last_error


def build_s3_key(city, now):
    """Date-partitioned key, e.g. raw/city=saskatoon/year=2026/month=11/day=03/hour=14.json"""
    return (
        f"raw/city={city.lower()}/year={now:%Y}/month={now:%m}/day={now:%d}/"
        f"hour={now:%H}.json"
    )


def build_record(city, lat, lon, weather, air, now):
    """Combine both API responses into one raw record."""
    return {
        "city": city,
        "latitude": lat,
        "longitude": lon,
        "collected_at_utc": now.isoformat(),
        "weather": weather,
        "air_quality": air,
    }


# ---------- Sprint 2: cleaning and transformation (SA-7) ----------
AQI_LEVELS = [
    (50, "Good"),
    (100, "Moderate"),
    (150, "Unhealthy for Sensitive Groups"),
    (200, "Unhealthy"),
    (300, "Very Unhealthy"),
]


def aqi_category(aqi):
    """US AQI number -> category name used by the dashboard colours."""
    if aqi is None:
        return "Unknown"
    for limit, name in AQI_LEVELS:
        if aqi <= limit:
            return name
    return "Hazardous"


def to_number(value, digits=1):
    """Round a value, or return None if it is missing or not a number."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return round(float(value), digits) + 0.0  # + 0.0 turns -0.0 into 0.0
    except (TypeError, ValueError):
        return None


def clean_record(city, weather, air, now):
    """Turn the two raw API responses into one flat, clean hourly record."""
    w = (weather or {}).get("current") or {}
    a = (air or {}).get("current") or {}
    aqi = to_number(a.get("us_aqi"), 0)
    aqi = int(aqi) if aqi is not None else None
    wind_kmh = to_number(w.get("wind_speed_10m"))
    return {
        "city": city.lower(),
        "timestamp": now.strftime("%Y-%m-%dT%H:00:00Z"),
        "local_time": w.get("time") or a.get("time"),
        "temperature_c": to_number(w.get("temperature_2m")),
        "feels_like_c": to_number(w.get("apparent_temperature")),
        "humidity_pct": to_number(w.get("relative_humidity_2m"), 0),
        "wind_kmh": wind_kmh,
        "wind_ms": round(wind_kmh / 3.6, 1) if wind_kmh is not None else None,
        "us_aqi": aqi,
        "pm2_5": to_number(a.get("pm2_5")),
        "pm10": to_number(a.get("pm10")),
        "aqi_category": aqi_category(aqi),
    }


def to_dynamo_item(record):
    """DynamoDB needs Decimal instead of float, and no empty (None) values."""
    from decimal import Decimal
    item = {}
    for key, value in record.items():
        if value is None:
            continue
        item[key] = Decimal(str(value)) if isinstance(value, float) else value
    return item


# ---------- Sprint 3: email alerts (SA-14) ----------
def alert_limits():
    return {
        "aqi": float(os.environ.get("AQI_LIMIT", "100")),
        "cold": float(os.environ.get("COLD_LIMIT", "-30")),
        "hot": float(os.environ.get("HOT_LIMIT", "32")),
    }


def check_alerts(reading, limits):
    """Return which limits this reading breaks: 'aqi', 'cold' and/or 'hot'."""
    if not reading:
        return []
    reasons = []
    aqi = reading.get("us_aqi")
    feels = reading.get("feels_like_c")
    if feels is None:
        feels = reading.get("temperature_c")
    temp = reading.get("temperature_c")
    if aqi is not None and aqi > limits["aqi"]:
        reasons.append("aqi")
    if feels is not None and feels < limits["cold"]:
        reasons.append("cold")
    if temp is not None and temp > limits["hot"]:
        reasons.append("hot")
    return reasons


def new_alerts(current, previous):
    """Only alert when a problem STARTS, so people don't get an email every hour."""
    return [r for r in current if r not in previous]


def previous_reading(table, city, timestamp):
    res = table.query(
        KeyConditionExpression="city = :c AND #ts < :t",
        ExpressionAttributeNames={"#ts": "timestamp"},
        ExpressionAttributeValues={":c": city, ":t": timestamp},
        ScanIndexForward=False,
        Limit=1,
    )
    items = res.get("Items", [])
    return items[0] if items else None


def alert_message(city, reading, reasons, limits):
    lines = [f"SaskAir Watch alert for {city.title()} ({reading.get('local_time') or reading['timestamp']})", ""]
    if "aqi" in reasons:
        lines.append(f"- Air quality is {reading.get('aqi_category')} (US AQI {reading.get('us_aqi')}, limit {limits['aqi']:g}). "
                     "Limit time outside, especially if you have asthma or breathing problems.")
    if "cold" in reasons:
        lines.append(f"- Extreme cold: feels like {reading.get('feels_like_c')} C (limit {limits['cold']:g} C). "
                     "Cover exposed skin and limit time outside.")
    if "hot" in reasons:
        lines.append(f"- Extreme heat: {reading.get('temperature_c')} C (limit {limits['hot']:g} C). Stay hydrated and find shade.")
    lines += ["", f"Temperature: {reading.get('temperature_c')} C, PM2.5: {reading.get('pm2_5')} ug/m3",
              "You are getting this because you subscribed to SaskAir Watch alerts."]
    subject = f"SaskAir Watch: {', '.join(r.upper() if r == 'aqi' else r for r in reasons)} alert for {city.title()}"
    return subject[:100], "\n".join(lines)


def lambda_handler(event, context, s3_client=None, fetch=fetch_json, now=None, table=None, sns_client=None):
    city = os.environ.get("CITY", "Saskatoon")
    lat = float(os.environ.get("LATITUDE", "52.13"))
    lon = float(os.environ.get("LONGITUDE", "-106.67"))
    bucket = os.environ["RAW_BUCKET"]
    now = now or datetime.now(timezone.utc)

    weather_url, air_url = build_urls(lat, lon)
    weather = fetch(weather_url)
    air = fetch(air_url)

    record = build_record(city, lat, lon, weather, air, now)
    key = build_s3_key(city, now)

    if s3_client is None:
        import boto3  # available in the Lambda runtime
        s3_client = boto3.client("s3")
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(record).encode("utf-8"),
        ContentType="application/json",
    )

    # Sprint 2: clean the data and save it in DynamoDB (skipped if no table is set up yet)
    clean = clean_record(city, weather, air, now)
    table_name = os.environ.get("TABLE_NAME")
    if table is None and table_name:
        import boto3
        table = boto3.resource("dynamodb").Table(table_name)
    previous = None
    if table is not None:
        previous = previous_reading(table, clean["city"], clean["timestamp"])
        table.put_item(Item=to_dynamo_item(clean))

    # Sprint 3: send an email alert when a limit is newly crossed (or on demand for a demo)
    limits = alert_limits()
    reasons = new_alerts(check_alerts(clean, limits), check_alerts(previous, limits))
    if (event or {}).get("test_alert"):
        reasons = reasons or ["aqi"]
    topic_arn = os.environ.get("ALERT_TOPIC_ARN")
    alerts_sent = []
    if reasons and topic_arn:
        if sns_client is None:
            import boto3
            sns_client = boto3.client("sns")
        subject, message = alert_message(city, clean, reasons, limits)
        if (event or {}).get("test_alert"):
            subject = "[TEST] " + subject
        sns_client.publish(TopicArn=topic_arn, Subject=subject[:100], Message=message)
        alerts_sent = reasons

    aqi = clean["us_aqi"]
    temp = clean["temperature_c"]
    print(json.dumps({"saved": f"s3://{bucket}/{key}", "stored_in_dynamodb": table is not None,
                      "alerts_sent": alerts_sent, "clean": clean}))
    return {"statusCode": 200, "bucket": bucket, "key": key, "us_aqi": aqi,
            "temperature_2m": temp, "aqi_category": clean["aqi_category"], "alerts_sent": alerts_sent}
