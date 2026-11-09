import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "query"))
import query_app  # noqa: E402

NOW = datetime(2026, 11, 8, 14, 0, tzinfo=timezone.utc)


def reading(ts, local, temp, aqi, pm25):
    return {"city": "saskatoon", "timestamp": ts, "local_time": local,
            "temperature_c": Decimal(str(temp)), "us_aqi": aqi, "pm2_5": Decimal(str(pm25)),
            "aqi_category": "Good"}


ITEMS = [
    reading("2026-11-07T20:00:00Z", "2026-11-07T14:00", -5.0, 30, 4.0),
    reading("2026-11-07T21:00:00Z", "2026-11-07T15:00", -3.0, 40, 6.0),
    reading("2026-11-08T12:00:00Z", "2026-11-08T06:00", -10.5, 20, 2.0),
    reading("2026-11-08T13:00:00Z", "2026-11-08T07:00", -9.5, 60, 8.0),
]


class FakeTable:
    """Acts like a DynamoDB table for the two queries the Lambda makes."""
    def __init__(self, items):
        self.items = items

    def query(self, **kw):
        vals = kw["ExpressionAttributeValues"]
        rows = [i for i in self.items if i["city"] == vals[":c"]]
        if ":since" in vals:
            rows = [i for i in rows if i["timestamp"] >= vals[":since"]]
        rows.sort(key=lambda i: i["timestamp"], reverse=not kw.get("ScanIndexForward", True))
        if "Limit" in kw:
            rows = rows[:kw["Limit"]]
        return {"Items": rows}


def call(path, params=None, items=ITEMS):
    event = {"resource": path, "queryStringParameters": params}
    res = query_app.lambda_handler(event, None, table=FakeTable(items), now=NOW)
    return res["statusCode"], json.loads(res["body"]), res["headers"]


def test_latest_returns_newest_reading():
    status, body, headers = call("/latest")
    assert status == 200
    assert body["timestamp"] == "2026-11-08T13:00:00Z"
    assert body["us_aqi"] == 60
    assert body["temperature_c"] == -9.5
    assert headers["Access-Control-Allow-Origin"] == "*"


def test_latest_404_when_no_data():
    status, body, _ = call("/latest", items=[])
    assert status == 404


def test_history_filters_by_hours():
    status, body, _ = call("/history", {"hours": "2"})
    assert status == 200
    assert body["count"] == 2
    assert [r["timestamp"] for r in body["readings"]] == ["2026-11-08T12:00:00Z", "2026-11-08T13:00:00Z"]


def test_history_daily_averages():
    status, body, _ = call("/history", {"hours": "48"})
    days = {d["date"]: d for d in body["daily_averages"]}
    assert days["2026-11-07"]["avg_temperature_c"] == -4.0
    assert days["2026-11-07"]["max_us_aqi"] == 40
    assert days["2026-11-08"]["avg_us_aqi"] == 40.0
    assert days["2026-11-08"]["min_temperature_c"] == -10.5
    assert days["2026-11-08"]["readings"] == 2


def test_history_rejects_bad_hours():
    assert call("/history", {"hours": "abc"})[0] == 400
    assert call("/history", {"hours": "0"})[0] == 400
    assert call("/history", {"hours": "500"})[0] == 400


def test_unknown_path_404():
    assert call("/nothing")[0] == 404
