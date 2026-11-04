"""SaskAir Watch - Ingest Lambda (Sprint 1).

Runs every hour (EventBridge). Calls the free Open-Meteo weather and
air quality REST APIs for one city and saves the raw JSON to S3.
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


def lambda_handler(event, context, s3_client=None, fetch=fetch_json, now=None):
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

    aqi = air.get("current", {}).get("us_aqi")
    temp = weather.get("current", {}).get("temperature_2m")
    print(json.dumps({"saved": f"s3://{bucket}/{key}", "us_aqi": aqi, "temperature_2m": temp}))
    return {"statusCode": 200, "bucket": bucket, "key": key, "us_aqi": aqi, "temperature_2m": temp}
