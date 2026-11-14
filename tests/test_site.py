"""Sprint 3: basic checks on the dashboard files (SA-12, SA-13)."""
import os
import re

SITE = os.path.join(os.path.dirname(__file__), "..", "site")


def read(name):
    with open(os.path.join(SITE, name), encoding="utf-8") as f:
        return f.read()


def test_dashboard_files_exist():
    for name in ["index.html", "app.js", "style.css", "config.js"]:
        assert os.path.exists(os.path.join(SITE, name)), name


def test_page_loads_config_before_app():
    html = read("index.html")
    assert html.index('src="config.js"') < html.index('src="app.js"')
    for element_id in ["aqi", "temp", "aqi-chart", "temp-chart", "daily", "signup"]:
        assert f'id="{element_id}"' in html, element_id


def test_app_uses_all_three_endpoints():
    js = read("app.js")
    for path in ["/latest", "/history", "/subscribe"]:
        assert path in js, path


def test_aqi_levels_match_the_backend():
    js = read("app.js")
    names = re.findall(r'name: "([^"]+)"', js)
    assert names == ["Good", "Moderate", "Unhealthy for Sensitive Groups", "Unhealthy", "Very Unhealthy", "Hazardous"]
