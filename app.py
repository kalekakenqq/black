import html
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "visits.db"

MSK = timezone(timedelta(hours=3))

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "blackred2026")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_IDS = [c.strip() for c in os.environ.get("TELEGRAM_CHAT_ID", "").split(",") if c.strip()]

app = FastAPI()
security = HTTPBasic()


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS visits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            ip TEXT,
            user_agent TEXT,
            referer TEXT,
            path TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS banquet_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            name TEXT,
            phone TEXT,
            event_type TEXT,
            event_date TEXT,
            guests TEXT,
            hall TEXT,
            comment TEXT
        )
        """
    )
    return conn


def log_visit(request: Request, path: str) -> None:
    try:
        ip = request.headers.get("x-forwarded-for", "")
        if not ip and request.client:
            ip = request.client.host
        ua = request.headers.get("user-agent", "")
        ref = request.headers.get("referer", "")
        conn = get_db()
        conn.execute(
            "INSERT INTO visits (ts, ip, user_agent, referer, path) VALUES (?, ?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), ip, ua, ref, path),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def check_auth(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    ok_user = secrets.compare_digest(
        credentials.username.encode("utf-8"), ADMIN_USER.encode("utf-8")
    )
    ok_pass = secrets.compare_digest(
        credentials.password.encode("utf-8"), ADMIN_PASS.encode("utf-8")
    )
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


app.mount("/css", StaticFiles(directory=str(BASE_DIR / "css")), name="css")
app.mount("/js", StaticFiles(directory=str(BASE_DIR / "js")), name="js")
app.mount("/images", StaticFiles(directory=str(BASE_DIR / "images")), name="images")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    log_visit(request, "/")
    return FileResponse(str(BASE_DIR / "index.html"))


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(str(BASE_DIR / "images" / "favicon.ico"))


async def notify_telegram(text: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_IDS:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            for chat_id in TELEGRAM_CHAT_IDS:
                await client.post(url, json={"chat_id": chat_id, "text": text})
    except Exception:
        pass


def clip(value, max_len: int) -> str:
    return str(value or "").strip()[:max_len]


@app.post("/api/banquet")
async def banquet_request(request: Request):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Некорректный запрос")

    name = clip(data.get("name"), 100)
    phone = clip(data.get("phone"), 40)
    event_type = clip(data.get("event_type"), 60)
    event_date = clip(data.get("date"), 40)
    guests = clip(data.get("guests"), 20)
    hall = clip(data.get("hall"), 60)
    comment = clip(data.get("comment"), 600)

    if not name or not phone:
        raise HTTPException(status_code=422, detail="Укажите имя и телефон")

    ts = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    conn.execute(
        """INSERT INTO banquet_requests (ts, name, phone, event_type, event_date, guests, hall, comment)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (ts, name, phone, event_type, event_date, guests, hall, comment),
    )
    conn.commit()
    conn.close()

    lines = ["Новая заявка на банкет / аренду зала — Black & Red", f"Имя: {name}", f"Телефон: {phone}"]
    if event_type:
        lines.append(f"Тип события: {event_type}")
    if event_date:
        lines.append(f"Дата: {event_date}")
    if guests:
        lines.append(f"Гостей: {guests}")
    if hall:
        lines.append(f"Формат: {hall}")
    if comment:
        lines.append(f"Комментарий: {comment}")
    await notify_telegram("\n".join(lines))

    return {"ok": True}


def parse_device(ua: str) -> str:
    ua = ua or ""
    if any(key in ua for key in ("Mobile", "Android", "iPhone", "iPad")):
        return "Телефон / планшет"
    return "Компьютер"


def parse_browser(ua: str) -> str:
    ua = ua or ""
    if "YaBrowser" in ua:
        return "Яндекс.Браузер"
    if "Edg/" in ua:
        return "Edge"
    if "OPR" in ua or "Opera" in ua:
        return "Opera"
    if "Chrome" in ua:
        return "Chrome"
    if "Firefox" in ua:
        return "Firefox"
    if "Safari" in ua:
        return "Safari"
    return "Другой"


def parse_source(ref: str) -> str:
    ref = (ref or "").lower()
    if not ref:
        return "Напрямую"
    if "yandex." in ref or "ya.ru" in ref:
        return "Яндекс"
    if "google." in ref:
        return "Google"
    if "t.me" in ref or "telegram" in ref:
        return "Telegram"
    if "whatsapp" in ref or "wa.me" in ref:
        return "WhatsApp"
    try:
        netloc = urlparse(ref).netloc or ref
        return netloc.replace("www.", "")
    except Exception:
        return "Другое"


def breakdown_rows(items, total: int) -> str:
    if not items:
        return '<div class="bd-row bd-empty">Пока нет данных</div>'
    rows = ""
    for label, count in items:
        pct = round(count / total * 100) if total else 0
        rows += (
            '<div class="bd-row">'
            f'<span class="bd-label">{html.escape(str(label))}</span>'
            f'<div class="bd-bar"><div class="bd-fill" style="width:{pct}%"></div></div>'
            f'<span class="bd-pct">{pct}%</span>'
            "</div>"
        )
    return rows


@app.get("/admin/export.csv", include_in_schema=False)
async def export_csv(user: str = Depends(check_auth)):
    import csv
    import io

    conn = get_db()
    rows = conn.execute(
        "SELECT ts, ip, user_agent, referer, path FROM visits ORDER BY id"
    ).fetchall()
    conn.close()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["время (МСК)", "ip", "устройство", "браузер", "источник", "страница"])
    for ts, ip, ua, ref, path in rows:
        dt = datetime.fromisoformat(ts).astimezone(MSK)
        writer.writerow([
            dt.strftime("%Y-%m-%d %H:%M:%S"),
            ip or "",
            parse_device(ua),
            parse_browser(ua),
            parse_source(ref),
            path or "",
        ])

    return Response(
        content="\ufeff" + buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=visits.csv"},
    )


@app.get("/admin", response_class=HTMLResponse)
async def admin(user: str = Depends(check_auth)):
    conn = get_db()
    now_utc = datetime.now(timezone.utc)
    now_msk = now_utc.astimezone(MSK)

    today_start_msk = datetime.combine(now_msk.date(), datetime.min.time(), tzinfo=MSK)
    today_start_utc = today_start_msk.astimezone(timezone.utc)
    week_start_utc = now_utc - timedelta(days=7)
    prev_week_start_utc = now_utc - timedelta(days=14)

    total = conn.execute("SELECT COUNT(*) FROM visits").fetchone()[0]
    today = conn.execute(
        "SELECT COUNT(*) FROM visits WHERE ts >= ?", (today_start_utc.isoformat(),)
    ).fetchone()[0]
    week = conn.execute(
        "SELECT COUNT(*) FROM visits WHERE ts >= ?", (week_start_utc.isoformat(),)
    ).fetchone()[0]
    prev_week = conn.execute(
        "SELECT COUNT(*) FROM visits WHERE ts >= ? AND ts < ?",
        (prev_week_start_utc.isoformat(), week_start_utc.isoformat()),
    ).fetchone()[0]

    if prev_week > 0:
        delta_pct = round((week - prev_week) / prev_week * 100)
    elif week > 0:
        delta_pct = 100
    else:
        delta_pct = 0

    # Visits by hour, today (Moscow time)
    rows_today = conn.execute(
        "SELECT ts FROM visits WHERE ts >= ?", (today_start_utc.isoformat(),)
    ).fetchall()
    hours = [0] * 24
    for (ts,) in rows_today:
        dt = datetime.fromisoformat(ts).astimezone(MSK)
        hours[dt.hour] += 1
    max_hour = max(hours) or 1

    # Visits per day, last 7 days (Moscow time)
    days = []
    for i in range(6, -1, -1):
        day = (now_msk - timedelta(days=i)).date()
        day_start = datetime.combine(day, datetime.min.time(), tzinfo=MSK).astimezone(timezone.utc)
        day_end = day_start + timedelta(days=1)
        cnt = conn.execute(
            "SELECT COUNT(*) FROM visits WHERE ts >= ? AND ts < ?",
            (day_start.isoformat(), day_end.isoformat()),
        ).fetchone()[0]
        days.append((day.strftime("%d.%m"), cnt))
    max_day = max((c for _, c in days), default=0) or 1

    # Sources, devices, browsers — last 7 days
    rows_week = conn.execute(
        "SELECT user_agent, referer FROM visits WHERE ts >= ?", (week_start_utc.isoformat(),)
    ).fetchall()
    source_counts: dict[str, int] = {}
    device_counts: dict[str, int] = {}
    browser_counts: dict[str, int] = {}
    for ua, ref in rows_week:
        src = parse_source(ref)
        source_counts[src] = source_counts.get(src, 0) + 1
        dev = parse_device(ua)
        device_counts[dev] = device_counts.get(dev, 0) + 1
        br = parse_browser(ua)
        browser_counts[br] = browser_counts.get(br, 0) + 1

    week_total = len(rows_week) or 1
    top_sources = sorted(source_counts.items(), key=lambda x: -x[1])[:5]
    top_devices = sorted(device_counts.items(), key=lambda x: -x[1])
    top_browsers = sorted(browser_counts.items(), key=lambda x: -x[1])[:5]

    # Recent visits
    recent = conn.execute(
        "SELECT ts, ip, user_agent, referer FROM visits ORDER BY id DESC LIMIT 20"
    ).fetchall()

    # Recent banquet requests
    banquets = conn.execute(
        """SELECT ts, name, phone, event_type, event_date, guests, hall, comment
           FROM banquet_requests ORDER BY id DESC LIMIT 20"""
    ).fetchall()
    conn.close()

    recent_rows = ""
    for ts, ip, ua, ref in recent:
        dt = datetime.fromisoformat(ts).astimezone(MSK)
        device = parse_device(ua)
        browser = parse_browser(ua)
        source = ref if ref else "напрямую"
        source = html.escape(source[:200])
        recent_rows += (
            f"<tr><td>{dt.strftime('%d.%m %H:%M')}</td>"
            f"<td>{device}</td><td>{browser}</td>"
            f"<td class='src'>{source}</td></tr>"
        )
    if not recent_rows:
        recent_rows = "<tr><td colspan='4' class='empty'>Пока нет визитов</td></tr>"

    banquet_rows = ""
    for ts, name, phone, event_type, event_date, guests, hall, comment in banquets:
        dt = datetime.fromisoformat(ts).astimezone(MSK)
        details = " · ".join(
            x for x in [event_type, event_date, f"{guests} гостей" if guests else "", hall] if x
        )
        banquet_rows += (
            f"<tr><td>{dt.strftime('%d.%m %H:%M')}</td>"
            f"<td>{html.escape(name)}</td>"
            f"<td>{html.escape(phone)}</td>"
            f"<td>{html.escape(details)}</td>"
            f"<td class='src'>{html.escape(comment)}</td></tr>"
        )
    if not banquet_rows:
        banquet_rows = "<tr><td colspan='5' class='empty'>Заявок пока нет</td></tr>"

    hour_bars = "".join(
        f'<div class="bar" style="height:{max(int(h / max_hour * 100), 2 if h else 0)}%" title="{i}:00 — {h}"></div>'
        for i, h in enumerate(hours)
    )
    day_bars = "".join(
        f'<div class="bar" style="height:{max(int(c / max_day * 100), 2 if c else 0)}%" title="{d} — {c}"></div>'
        for d, c in days
    )
    day_labels = "".join(f"<span>{d}</span>" for d, _ in days)

    source_rows = breakdown_rows(top_sources, week_total)
    device_rows = breakdown_rows(top_devices, week_total)
    browser_rows = breakdown_rows(top_browsers, week_total)

    if delta_pct > 0:
        delta_label = f"+{delta_pct}% к прошлой неделе"
        delta_class = "up"
    elif delta_pct < 0:
        delta_label = f"{delta_pct}% к прошлой неделе"
        delta_class = "down"
    else:
        delta_label = "как на прошлой неделе"
        delta_class = ""

    page_html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="60">
<title>Black &amp; Red — Админ-панель</title>
<style>
  :root {{
    color-scheme: dark;
    --bg: #0d0a0c;
    --bg-card: #1d1620;
    --red: #b3122a;
    --gold: #cda653;
    --gold-soft: #e9d9b6;
    --text: #f5f1ea;
    --text-muted: #8f8189;
    --line: rgba(233, 217, 182, 0.14);
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: 'Manrope', 'Segoe UI', sans-serif;
    background: var(--bg);
    color: var(--text);
    padding: 24px;
  }}
  h1 {{
    font-family: 'Playfair Display', Georgia, serif;
    font-size: 1.6rem;
    margin: 0 0 4px;
  }}
  .updated {{ color: var(--text-muted); font-size: .85rem; margin-bottom: 24px; }}
  .kpis {{
    display: flex; flex-wrap: wrap; gap: 14px; margin-bottom: 28px;
  }}
  .kpi {{
    background: var(--bg-card); border: 1px solid var(--line);
    border-radius: 12px; padding: 16px 22px; min-width: 140px;
  }}
  .kpi .num {{ font-family: 'Playfair Display', Georgia, serif; font-size: 1.8rem; color: var(--gold); }}
  .kpi .label {{ font-size: .8rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: .06em; }}
  .panels {{ display: flex; flex-wrap: wrap; gap: 18px; margin-bottom: 28px; }}
  .panel {{
    background: var(--bg-card); border: 1px solid var(--line);
    border-radius: 12px; padding: 18px; flex: 1; min-width: 280px;
  }}
  .panel h2 {{ font-size: .95rem; margin: 0 0 14px; color: var(--gold-soft); }}
  .chart {{
    display: flex; align-items: flex-end; gap: 4px; height: 110px;
  }}
  .chart .bar {{
    flex: 1; background: linear-gradient(180deg, var(--gold), var(--red));
    border-radius: 3px 3px 0 0; min-height: 2px;
  }}
  .chart-labels {{
    display: flex; justify-content: space-between; margin-top: 6px;
    font-size: .7rem; color: var(--text-muted);
  }}
  .chart-labels.hours span:not(:nth-child(4n+1)) {{ display: none; }}
  table {{ width: 100%; border-collapse: collapse; font-size: .85rem; }}
  th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--line); }}
  th {{ color: var(--text-muted); font-weight: 600; text-transform: uppercase; font-size: .7rem; letter-spacing: .06em; }}
  td.src {{ color: var(--text-muted); max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  td.empty {{ color: var(--text-muted); text-align: center; padding: 20px; }}
  .kpi .delta {{ font-size: .75rem; margin-top: 2px; }}
  .kpi .delta.up {{ color: #7bc88a; }}
  .kpi .delta.down {{ color: var(--red); }}
  .bd-row {{
    display: flex; align-items: center; gap: 10px;
    font-size: .85rem; padding: 5px 0;
  }}
  .bd-label {{ flex: 0 0 110px; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .bd-bar {{ flex: 1; height: 6px; background: rgba(233,217,182,.1); border-radius: 4px; overflow: hidden; }}
  .bd-fill {{ height: 100%; background: linear-gradient(90deg, var(--gold), var(--red)); border-radius: 4px; }}
  .bd-pct {{ flex: 0 0 38px; text-align: right; color: var(--text-muted); font-size: .8rem; }}
  .bd-empty {{ color: var(--text-muted); }}
  .export {{
    display: inline-block; margin-bottom: 24px; padding: 8px 16px;
    border: 1px solid var(--line); border-radius: 8px; color: var(--gold-soft);
    text-decoration: none; font-size: .85rem;
  }}
  .export:hover {{ border-color: var(--gold); }}
</style>
</head>
<body>
  <h1>Black &amp; Red — Админ-панель</h1>
  <div class="updated">Обновлено: {now_msk.strftime('%d.%m.%Y %H:%M')} (МСК) · автообновление каждую минуту</div>
  <a class="export" href="/admin/export.csv">Скачать визиты (CSV)</a>

  <div class="kpis">
    <div class="kpi"><div class="num">{total}</div><div class="label">Всего визитов</div></div>
    <div class="kpi"><div class="num">{today}</div><div class="label">Сегодня</div></div>
    <div class="kpi">
      <div class="num">{week}</div><div class="label">За 7 дней</div>
      <div class="delta {delta_class}">{delta_label}</div>
    </div>
  </div>

  <div class="panels">
    <div class="panel">
      <h2>Визиты по часам сегодня (МСК)</h2>
      <div class="chart">{hour_bars}</div>
      <div class="chart-labels hours">{''.join(f'<span>{i}</span>' for i in range(24))}</div>
    </div>
    <div class="panel">
      <h2>Визиты за 7 дней</h2>
      <div class="chart">{day_bars}</div>
      <div class="chart-labels">{day_labels}</div>
    </div>
  </div>

  <div class="panels">
    <div class="panel">
      <h2>Источники (7 дней)</h2>
      {source_rows}
    </div>
    <div class="panel">
      <h2>Устройства (7 дней)</h2>
      {device_rows}
    </div>
    <div class="panel">
      <h2>Браузеры (7 дней)</h2>
      {browser_rows}
    </div>
  </div>

  <div class="panel">
    <h2>Последние визиты</h2>
    <table>
      <thead><tr><th>Время (МСК)</th><th>Устройство</th><th>Браузер</th><th>Источник</th></tr></thead>
      <tbody>{recent_rows}</tbody>
    </table>
  </div>

  <div class="panel" style="margin-top: 18px;">
    <h2>Заявки на банкеты / аренду зала</h2>
    <table>
      <thead><tr><th>Время (МСК)</th><th>Имя</th><th>Телефон</th><th>Детали</th><th>Комментарий</th></tr></thead>
      <tbody>{banquet_rows}</tbody>
    </table>
  </div>
</body>
</html>"""
    return HTMLResponse(page_html)
