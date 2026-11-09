"""SaskAir Watch - Ingest Lambda.

Runs every hour (EventBridge). Calls the free Open-Meteo weather and
air quality REST APIs for one city, saves the raw JSON to S3 (Sprint 1),
then cleans the data and saves one record per hour in DynamoDB (Sprint 2).
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


def lambda_handler(event, context, s3_client=None, fetch=fetch_json, now=None, table=None):
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
    if table is not None:
        table.put_item(Item=to_dynamo_item(clean))

    aqi = clean["us_aqi"]
    temp = clean["temperature_c"]
    print(json.dumps({"saved": f"s3://{bucket}/{key}", "stored_in_dynamodb": table is not None, "clean": clean}))
    return {"statusCode": 200, "bucket": bucket, "key": key, "us_aqi": aqi,
            "temperature_2m": temp, "aqi_category": clean["aqi_category"]}
