import io
import json
import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "ingest"))
import app  # noqa: E402

NOW = datetime(2026, 11, 3, 14, 0, tzinfo=timezone.utc)
WEATHER = {"current": {"temperature_2m": -12.4, "apparent_temperature": -19.0,
                       "relative_humidity_2m": 80, "wind_speed_10m": 22.1}}
AIR = {"current": {"us_aqi": 42, "pm2_5": 6.3, "pm10": 9.1}}


def test_build_urls_has_location_and_fields():
    weather, air = app.build_urls(52.13, -106.67)
    assert weather.startswith("https://api.open-meteo.com/v1/forecast?")
    assert air.startswith("https://air-quality-api.open-meteo.com/v1/air-quality?")
    for url in (weather, air):
        assert "latitude=52.13" in url
        assert "longitude=-106.67" in url
    assert "us_aqi" in air
    assert "temperature_2m" in weather


def test_s3_key_is_partitioned_by_date():
    assert app.build_s3_key("Saskatoon", NOW) == \
        "raw/city=saskatoon/year=2026/month=11/day=03/hour=14.json"


def test_fetch_json_retries_then_succeeds():
    calls = {"n": 0}

    def flaky_opener(url, timeout):
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("slow API")
        return io.BytesIO(json.dumps(AIR).encode())

    assert app.fetch_json("http://x", retries=3, wait_seconds=0, opener=flaky_opener) == AIR
    assert calls["n"] == 3


def test_fetch_json_gives_up_after_retries():
    def always_fails(url, timeout):
        raise TimeoutError("down")

    with pytest.raises(RuntimeError):
        app.fetch_json("http://x", retries=2, wait_seconds=0, opener=always_fails)


def test_handler_saves_raw_json_to_s3(monkeypatch):
    monkeypatch.setenv("RAW_BUCKET", "test-bucket")
    s3 = MagicMock()
    fake_fetch = lambda url: AIR if "air-quality" in url else WEATHER

    result = app.lambda_handler({}, None, s3_client=s3, fetch=fake_fetch, now=NOW)

    s3.put_object.assert_called_once()
    kwargs = s3.put_object.call_args.kwargs
    assert kwargs["Bucket"] == "test-bucket"
    assert kwargs["Key"].startswith("raw/city=saskatoon/")
    body = json.loads(kwargs["Body"])
    assert body["air_quality"]["current"]["us_aqi"] == 42
    assert body["weather"]["current"]["temperature_2m"] == -12.4
    assert result["statusCode"] == 200
    assert result["us_aqi"] == 42


def test_build_record_keeps_both_responses():
    rec = app.build_record("Saskatoon", 52.13, -106.67, WEATHER, AIR, NOW)
    assert rec["city"] == "Saskatoon"
    assert rec["weather"] == WEATHER
    assert rec["air_quality"] == AIR
    assert rec["collected_at_utc"].startswith("2026-11-03T14")


# ---------- Sprint 2: cleaning (SA-7) and DynamoDB (SA-8) ----------

def test_clean_record_rounds_and_converts_units():
    clean = app.clean_record("Saskatoon", WEATHER, AIR, NOW)
    assert clean["city"] == "saskatoon"
    assert clean["timestamp"] == "2026-11-03T14:00:00Z"
    assert clean["temperature_c"] == -12.4
    assert clean["wind_kmh"] == 22.1
    assert clean["wind_ms"] == 6.1          # 22.1 km/h / 3.6
    assert clean["us_aqi"] == 42 and isinstance(clean["us_aqi"], int)
    assert clean["aqi_category"] == "Good"


def test_clean_record_handles_missing_and_bad_values():
    weather = {"current": {"temperature_2m": None, "wind_speed_10m": "n/a"}}
    clean = app.clean_record("Saskatoon", weather, {}, NOW)
    assert clean["temperature_c"] is None
    assert clean["wind_kmh"] is None and clean["wind_ms"] is None
    assert clean["us_aqi"] is None
    assert clean["aqi_category"] == "Unknown"


def test_negative_zero_becomes_zero():
    assert str(app.to_number(-0.0)) == "0.0"


@pytest.mark.parametrize("aqi,expected", [
    (0, "Good"), (50, "Good"), (51, "Moderate"), (120, "Unhealthy for Sensitive Groups"),
    (180, "Unhealthy"), (250, "Very Unhealthy"), (400, "Hazardous"),
])
def test_aqi_category(aqi, expected):
    assert app.aqi_category(aqi) == expected


def test_dynamo_item_uses_decimals_and_drops_empty_values():
    from decimal import Decimal
    item = app.to_dynamo_item({"temperature_c": -12.4, "us_aqi": 42, "pm10": None, "city": "saskatoon"})
    assert item["temperature_c"] == Decimal("-12.4")
    assert item["us_aqi"] == 42
    assert "pm10" not in item


def test_handler_saves_clean_record_to_dynamodb(monkeypatch):
    monkeypatch.setenv("RAW_BUCKET", "test-bucket")
    s3, table = MagicMock(), MagicMock()
    fake_fetch = lambda url: AIR if "air-quality" in url else WEATHER

    result = app.lambda_handler({}, None, s3_client=s3, fetch=fake_fetch, now=NOW, table=table)

    table.put_item.assert_called_once()
    item = table.put_item.call_args.kwargs["Item"]
    assert item["city"] == "saskatoon"
    assert item["timestamp"] == "2026-11-03T14:00:00Z"
    assert result["aqi_category"] == "Good"
