// SaskAir Watch dashboard (Sprint 3). Reads from our REST API: /latest, /history, /subscribe.
(function () {
  "use strict";
  var API = ((window.SASKAIR_CONFIG || {}).apiUrl || "").replace(/\/$/, "");
  var CITY = "saskatoon";

  var LEVELS = [
    { max: 50, name: "Good", color: "var(--good)", hex: "#2E8B57", advice: "Air quality is good. Enjoy your time outside." },
    { max: 100, name: "Moderate", color: "var(--moderate)", hex: "#C99A06", advice: "Air is okay for most people. Very sensitive people should take it easy outside." },
    { max: 150, name: "Unhealthy for Sensitive Groups", color: "var(--usg)", hex: "#E07A1F", advice: "People with asthma, kids and older adults should limit long or hard activity outside." },
    { max: 200, name: "Unhealthy", color: "var(--unhealthy)", hex: "#C0392B", advice: "Everyone should limit time outside. Keep windows closed if it's smoky." },
    { max: 300, name: "Very Unhealthy", color: "var(--very)", hex: "#7B2D8E", advice: "Avoid outdoor activity. Stay inside with clean air if you can." },
    { max: Infinity, name: "Hazardous", color: "var(--hazard)", hex: "#6E1423", advice: "Health warning: stay indoors and avoid all outdoor activity." }
  ];

  function level(aqi) {
    if (aqi === null || aqi === undefined) return null;
    for (var i = 0; i < LEVELS.length; i++) if (aqi <= LEVELS[i].max) return LEVELS[i];
    return LEVELS[LEVELS.length - 1];
  }
  function $(id) { return document.getElementById(id); }
  function fmt(v, digits) { return v === null || v === undefined ? "–" : Number(v).toFixed(digits === undefined ? 1 : digits); }
  function localDate(ts) { return new Date(ts); }
  function timeLabel(d, long) {
    return long
      ? d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })
      : d.toLocaleTimeString(undefined, { hour: "numeric" });
  }

  function getJSON(path) {
    return fetch(API + path).then(function (r) {
      return r.json().then(function (body) {
        if (!r.ok) throw new Error(body.message || ("Request failed: " + r.status));
        return body;
      });
    });
  }

  // ---------- current conditions ----------
  function showLatest(d) {
    var lv = level(d.us_aqi);
    $("aqi").textContent = d.us_aqi === undefined ? "–" : d.us_aqi;
    $("aqi-cat").textContent = lv ? lv.name : "Unknown";
    $("aqi-cat").style.color = lv ? lv.color : "";
    $("aqi").style.color = lv ? lv.color : "";
    $("aqi-card").style.borderTopColor = lv ? lv.hex : "";
    $("advice").textContent = lv ? lv.advice : "";
    $("temp").textContent = fmt(d.temperature_c);
    $("feels").textContent = fmt(d.feels_like_c);
    $("wind").textContent = fmt(d.wind_kmh);
    $("humidity").textContent = fmt(d.humidity_pct, 0);
    $("pm25").textContent = fmt(d.pm2_5);
    $("pm10").textContent = fmt(d.pm10);
    var when = localDate(d.timestamp);
    $("updated").textContent = "Last updated " + when.toLocaleString(undefined, { weekday: "short", hour: "numeric", minute: "2-digit" });
  }

  // ---------- simple SVG line chart ----------
  var NS = "http://www.w3.org/2000/svg";
  function el(name, attrs, text) {
    var n = document.createElementNS(NS, name);
    for (var k in attrs) n.setAttribute(k, attrs[k]);
    if (text !== undefined) n.textContent = text;
    return n;
  }

  function niceTicks(lo, hi, count) {
    var span = hi - lo || 1, step = Math.pow(10, Math.floor(Math.log10(span / count)));
    [1, 2, 5, 10].some(function (m) { if (span / (step * m) <= count) { step = step * m; return true; } return false; });
    var ticks = [], start = Math.floor(lo / step) * step;
    for (var v = start; v <= hi + step * 0.001; v += step) ticks.push(Math.round(v * 100) / 100);
    if (ticks[ticks.length - 1] < hi) ticks.push(ticks[ticks.length - 1] + step);
    return ticks;
  }

  function lineChart(box, points, opts) {
    box.innerHTML = "";
    if (!points.length) { box.textContent = "No data yet."; return; }
    var W = Math.max(300, Math.round(box.clientWidth || 960)), H = W < 600 ? 200 : 240, L = 40, R = 12, T = 12, B = 30;
    var xs = points.map(function (p) { return p.t.getTime(); });
    var vs = points.map(function (p) { return p.v; });
    var x0 = Math.min.apply(null, xs), x1 = Math.max.apply(null, xs);
    var vLo = Math.min.apply(null, vs), vHi = Math.max.apply(null, vs);
    if (opts.floor !== undefined) vLo = Math.min(vLo, opts.floor);
    var ticks = niceTicks(vLo, vHi, 4), y0 = ticks[0], y1 = ticks[ticks.length - 1];
    var X = function (t) { return x1 === x0 ? (L + W - R) / 2 : L + (t - x0) / (x1 - x0) * (W - L - R); };
    var Y = function (v) { return T + (1 - (v - y0) / (y1 - y0 || 1)) * (H - T - B); };
    var svg = el("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": opts.label });

    if (opts.bands) opts.bands.forEach(function (b) {   // AQI category bands behind the line
      var top = Math.min(b.max, y1), bottom = Math.max(b.min, y0);
      if (top <= bottom) return;
      svg.appendChild(el("rect", { x: L, width: W - L - R, y: Y(top), height: Y(bottom) - Y(top), fill: b.hex, "fill-opacity": 0.08 }));
    });
    ticks.forEach(function (v) {
      svg.appendChild(el("line", { x1: L, x2: W - R, y1: Y(v), y2: Y(v), stroke: "#E1E6EA" }));
      svg.appendChild(el("text", { x: L - 8, y: Y(v) + 4, "text-anchor": "end", "font-size": 12, fill: "#5B6670" }, v));
    });
    var long = (x1 - x0) > 36 * 3600e3, n = Math.min(W < 600 ? 3 : 6, points.length);
    for (var i = 0; i < n; i++) {
      var p = points[Math.round(i * (points.length - 1) / Math.max(n - 1, 1))];
      var anchor = n > 1 && i === 0 ? "start" : (n > 1 && i === n - 1 ? "end" : "middle");
      svg.appendChild(el("text", { x: X(p.t.getTime()), y: H - 8, "text-anchor": anchor, "font-size": 12, fill: "#5B6670" }, timeLabel(p.t, long)));
    }
    var d = points.map(function (p, i) { return (i ? "L" : "M") + X(p.t.getTime()).toFixed(1) + " " + Y(p.v).toFixed(1); }).join("");
    svg.appendChild(el("path", { d: d, fill: "none", stroke: opts.color, "stroke-width": 2.5, "stroke-linejoin": "round" }));
    var last = points[points.length - 1];
    svg.appendChild(el("circle", { cx: X(last.t.getTime()), cy: Y(last.v), r: 4.5, fill: opts.color }));

    var hover = el("circle", { r: 5, fill: "#fff", stroke: opts.color, "stroke-width": 2, visibility: "hidden" });
    svg.appendChild(hover);
    box.appendChild(svg);
    var tip = document.createElement("div"); tip.className = "tip"; tip.hidden = true; box.appendChild(tip);
    svg.addEventListener("mousemove", function (e) {
      var r = svg.getBoundingClientRect(), mx = (e.clientX - r.left) / r.width * W, best = points[0];
      points.forEach(function (p) { if (Math.abs(X(p.t.getTime()) - mx) < Math.abs(X(best.t.getTime()) - mx)) best = p; });
      hover.setAttribute("cx", X(best.t.getTime())); hover.setAttribute("cy", Y(best.v)); hover.setAttribute("visibility", "visible");
      tip.hidden = false;
      tip.textContent = fmt(best.v, opts.digits) + opts.unit + " · " + best.t.toLocaleString(undefined, { weekday: "short", hour: "numeric" });
      tip.style.left = (X(best.t.getTime()) / W * r.width) + "px";
      tip.style.top = (Y(best.v) / H * r.height) + "px";
    });
    svg.addEventListener("mouseleave", function () { hover.setAttribute("visibility", "hidden"); tip.hidden = true; });
  }

  // ---------- history + daily averages ----------
  var lastHistory = null;
  function showHistory(h) {
    lastHistory = h;
    var rows = h.readings || [];
    var aqi = rows.filter(function (r) { return r.us_aqi !== undefined && r.us_aqi !== null; })
      .map(function (r) { return { t: localDate(r.timestamp), v: r.us_aqi }; });
    var temp = rows.filter(function (r) { return r.temperature_c !== undefined && r.temperature_c !== null; })
      .map(function (r) { return { t: localDate(r.timestamp), v: r.temperature_c }; });
    var bands = LEVELS.map(function (l, i) { return { min: i ? LEVELS[i - 1].max : 0, max: l.max === Infinity ? 500 : l.max, hex: l.hex }; });
    lineChart($("aqi-chart"), aqi, { color: "#E07A1F", unit: " AQI", digits: 0, floor: 0, bands: bands, label: "Air quality over time" });
    lineChart($("temp-chart"), temp, { color: "#1F3A4D", unit: " °C", digits: 1, label: "Temperature over time" });
    $("trend-note").textContent = rows.length + " hourly readings in this range. Coloured bands show the AQI categories.";

    var tbody = $("daily");
    tbody.innerHTML = "";
    (h.daily_averages || []).slice().reverse().forEach(function (d) {
      var lv = level(d.max_us_aqi);
      var tr = document.createElement("tr");
      var dateTxt = new Date(d.date + "T12:00:00").toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
      [dateTxt, fmt(d.avg_temperature_c) + " °C", fmt(d.min_temperature_c) + " / " + fmt(d.max_temperature_c) + " °C",
        fmt(d.avg_us_aqi), null, fmt(d.avg_pm2_5), d.readings].forEach(function (v, i) {
        var td = document.createElement("td");
        if (i === 4) {
          var dot = document.createElement("span"); dot.className = "dot"; dot.style.background = lv ? lv.hex : "#ccc";
          td.appendChild(dot); td.appendChild(document.createTextNode(fmt(d.max_us_aqi, 0)));
        } else td.textContent = v;
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
  }

  var currentHours = 24;
  function loadHistory() {
    return getJSON("/history?city=" + CITY + "&hours=" + currentHours).then(showHistory);
  }
  function loadAll() {
    $("error").hidden = true;
    return Promise.all([getJSON("/latest?city=" + CITY).then(showLatest), loadHistory()]).catch(function (err) {
      $("error").hidden = false;
      $("error").textContent = "Couldn't load the latest data: " + err.message;
    });
  }

  Array.prototype.forEach.call(document.querySelectorAll(".toggle button"), function (b) {
    b.addEventListener("click", function () {
      currentHours = Number(b.getAttribute("data-hours"));
      Array.prototype.forEach.call(document.querySelectorAll(".toggle button"), function (o) { o.classList.toggle("on", o === b); });
      loadHistory();
    });
  });

  // ---------- email sign-up ----------
  $("signup").addEventListener("submit", function (e) {
    e.preventDefault();
    var msg = $("signup-msg");
    msg.textContent = "Signing you up…";
    // text/plain keeps this a "simple" request, so the browser doesn't need a CORS preflight
    fetch(API + "/subscribe", { method: "POST", headers: { "Content-Type": "text/plain" }, body: JSON.stringify({ email: $("email").value }) })
      .then(function (r) { return r.json().then(function (b) { msg.textContent = b.message; if (r.ok) $("email").value = ""; }); })
      .catch(function () { msg.textContent = "Something went wrong. Please try again."; });
  });

  var resizeTimer;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () { if (lastHistory) showHistory(lastHistory); }, 200);
  });

  loadAll();
  setInterval(loadAll, 15 * 60 * 1000);   // refresh every 15 minutes
})();
