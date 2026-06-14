import html
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
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
    ok_user = secrets.compare_digest(credentials.username, ADMIN_USER)
    ok_pass = secrets.compare_digest(credentials.password, ADMIN_PASS)
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


@app.get("/admin", response_class=HTMLResponse)
async def admin(user: str = Depends(check_auth)):
    conn = get_db()
    now_utc = datetime.now(timezone.utc)
    now_msk = now_utc.astimezone(MSK)

    today_start_msk = datetime.combine(now_msk.date(), datetime.min.time(), tzinfo=MSK)
    today_start_utc = today_start_msk.astimezone(timezone.utc)
    week_start_utc = now_utc - timedelta(days=7)

    total = conn.execute("SELECT COUNT(*) FROM visits").fetchone()[0]
    today = conn.execute(
        "SELECT COUNT(*) FROM visits WHERE ts >= ?", (today_start_utc.isoformat(),)
    ).fetchone()[0]
    week = conn.execute(
        "SELECT COUNT(*) FROM visits WHERE ts >= ?", (week_start_utc.isoformat(),)
    ).fetchone()[0]

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

    # Recent visits
    recent = conn.execute(
        "SELECT ts, ip, user_agent, referer FROM visits ORDER BY id DESC LIMIT 20"
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

    hour_bars = "".join(
        f'<div class="bar" style="height:{max(int(h / max_hour * 100), 2 if h else 0)}%" title="{i}:00 — {h}"></div>'
        for i, h in enumerate(hours)
    )
    day_bars = "".join(
        f'<div class="bar" style="height:{max(int(c / max_day * 100), 2 if c else 0)}%" title="{d} — {c}"></div>'
        for d, c in days
    )
    day_labels = "".join(f"<span>{d}</span>" for d, _ in days)

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
</style>
</head>
<body>
  <h1>Black &amp; Red — Админ-панель</h1>
  <div class="updated">Обновлено: {now_msk.strftime('%d.%m.%Y %H:%M')} (МСК) · автообновление каждую минуту</div>

  <div class="kpis">
    <div class="kpi"><div class="num">{total}</div><div class="label">Всего визитов</div></div>
    <div class="kpi"><div class="num">{today}</div><div class="label">Сегодня</div></div>
    <div class="kpi"><div class="num">{week}</div><div class="label">За 7 дней</div></div>
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

  <div class="panel">
    <h2>Последние визиты</h2>
    <table>
      <thead><tr><th>Время (МСК)</th><th>Устройство</th><th>Браузер</th><th>Источник</th></tr></thead>
      <tbody>{recent_rows}</tbody>
    </table>
  </div>
</body>
</html>"""
    return HTMLResponse(page_html)
