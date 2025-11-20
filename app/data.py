import os, sqlite3, pandas as pd
from typing import Dict, Any, Tuple, List, Optional
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "mat.db")

# ---------- bootstrap / schema ----------
def ensure_schema():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS user_sessions(
        chat_id     INTEGER PRIMARY KEY,
        report_time TEXT,
        last_seen_at TEXT
    )""")
    conn.commit(); conn.close()

def load_csv_to_sqlite(assets_csv: str, wo_csv: str):
    ensure_schema()
    conn = sqlite3.connect(DB_PATH)
    pd.read_csv(assets_csv).to_sql("assets", conn, if_exists="replace", index=False)

    dfwo = pd.read_csv(wo_csv)
    if "mttr_hours" not in dfwo.columns and "labor_hours" in dfwo.columns:
        dfwo["mttr_hours"] = dfwo["labor_hours"]
    if "cost_total" not in dfwo.columns:
        dfwo["cost_total"] = dfwo.get("cost_parts", 0) + dfwo.get("cost_labor", 0)
    dfwo.to_sql("work_orders", conn, if_exists="replace", index=False)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_wo_asset ON work_orders(asset_id)")
    conn.commit(); conn.close()

# ---------- subscriptions ----------
def update_last_seen(chat_id: int):
    ensure_schema()
    now = datetime.utcnow().isoformat(timespec="seconds")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO user_sessions(chat_id, last_seen_at) VALUES(?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET last_seen_at=excluded.last_seen_at
    """, (chat_id, now))
    conn.commit(); conn.close()

def set_report_time(chat_id: int, hhmm: str):
    ensure_schema()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO user_sessions(chat_id, report_time) VALUES(?,?)
        ON CONFLICT(chat_id) DO UPDATE SET report_time=excluded.report_time
    """, (chat_id, hhmm))
    conn.commit(); conn.close()

def get_report_time(chat_id: int) -> Optional[str]:
    ensure_schema()
    conn = sqlite3.connect(DB_PATH)
    r = conn.execute("SELECT report_time FROM user_sessions WHERE chat_id=?", (chat_id,)).fetchone()
    conn.close()
    return r[0] if r and r[0] else None

def all_chat_ids_with_time() -> List[Tuple[int, str]]:
    ensure_schema()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT chat_id, report_time FROM user_sessions WHERE report_time IS NOT NULL").fetchall()
    conn.close()
    return rows

# ---------- helpers de filtros ----------
def _filters_to_where(slots: Dict[str, Any]) -> Tuple[str, list]:
    clauses, params = [], []
    if slots.get("site"):
        clauses.append("work_orders.asset_id IN (SELECT asset_id FROM assets WHERE site=?)"); params.append(slots["site"])
    if slots.get("area"):
        clauses.append("work_orders.asset_id IN (SELECT asset_id FROM assets WHERE area=?)"); params.append(slots["area"])
    if slots.get("status"):
        clauses.append("status=?"); params.append(slots["status"])
    if slots.get("type"):
        clauses.append("type=?"); params.append(slots["type"])
    if slots.get("technician"):
        clauses.append("LOWER(technician)=LOWER(?)"); params.append(slots["technician"])
    if slots.get("date_from"):
        clauses.append("date(substr(COALESCE(closed_at, opened_at),1,10)) >= date(?)"); params.append(slots["date_from"])
    if slots.get("date_to"):
        clauses.append("date(substr(COALESCE(closed_at, opened_at),1,10)) <= date(?)"); params.append(slots["date_to"])
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params

def query_known_values() -> Tuple[List[str], List[str]]:
    conn = sqlite3.connect(DB_PATH)
    sites = [r[0] for r in conn.execute("SELECT DISTINCT site FROM assets WHERE site IS NOT NULL")] if _table_has_column(conn,"assets","site") else []
    areas = [r[0] for r in conn.execute("SELECT DISTINCT area FROM assets WHERE area IS NOT NULL")] if _table_has_column(conn,"assets","area") else []
    conn.close(); return sites, areas

def _table_has_column(conn, table, col) -> bool:
    try:
        conn.execute(f"SELECT {col} FROM {table} LIMIT 1")
        return True
    except sqlite3.OperationalError:
        return False

# ---------- KPIs ----------
def kpi_mttr(slots: Dict[str, Any]) -> float:
    where, params = _filters_to_where({**slots, "status": "Cerrada"})
    sql = f"SELECT AVG(COALESCE(mttr_hours, labor_hours)) FROM work_orders {where}"
    conn = sqlite3.connect(DB_PATH); cur = conn.execute(sql, params)
    val = cur.fetchone()[0]; conn.close(); return round(val or 0.0, 2)

def kpi_backlog_days(slots: Dict[str, Any]) -> float:
    where, params = _filters_to_where({**slots, "status": None})
    where = f"{where} {' AND ' if where else 'WHERE '} status!='Cerrada'"
    sql = f"SELECT opened_at FROM work_orders {where}"
    conn = sqlite3.connect(DB_PATH); rows = [r[0] for r in conn.execute(sql, params)]
    conn.close()
    if not rows: return 0.0
    now = datetime.utcnow(); days=[]
    for s in rows:
        try: days.append((now - datetime.fromisoformat(s)).days)
        except: pass
    return round(sum(days)/len(days), 2) if days else 0.0

def kpi_pm_compliance(slots: Dict[str, Any], window_days: int = 31) -> float:
    where, params = _filters_to_where({**slots, "type": "PM"})
    sql = f"SELECT due_date, closed_at FROM work_orders {where}"
    conn = sqlite3.connect(DB_PATH); rows = conn.execute(sql, params).fetchall(); conn.close()
    if not rows: return 0.0
    from datetime import date, timedelta
    if slots.get("date_from") and slots.get("date_to"):
        start = date.fromisoformat(slots["date_from"])
    else:
        start = date.today().replace(day=1)
    due = [(d,c) for d,c in rows if d and d >= str(start)]
    if not due: return 0.0
    good = sum(1 for d,c in due if c and c[:10] <= d)
    return round(100.0 * good / len(due), 2)

def kpi_costs_monthly(slots: Dict[str, Any], months: int = 6):
    # Si se especifica mes (date_from/to en el mismo mes) -> devolver SOLO ese mes
    if slots.get("date_from") and slots.get("date_to"):
        year_month = slots["date_from"][:7]
        where, params = _filters_to_where(slots)
        sql = f"""
            SELECT substr(opened_at,1,7) AS ym, SUM(cost_total)
            FROM work_orders {where}
            GROUP BY ym HAVING ym = ?
            ORDER BY ym DESC
        """
        conn = sqlite3.connect(DB_PATH); rows = conn.execute(sql, params + [year_month]).fetchall(); conn.close()
        return rows

    # default: últimos N meses del rango filtrado
    where, params = _filters_to_where(slots)
    sql = f"""
        SELECT substr(opened_at,1,7) AS ym, SUM(cost_total)
        FROM work_orders {where}
        GROUP BY ym ORDER BY ym DESC LIMIT ?
    """
    conn = sqlite3.connect(DB_PATH); rows = conn.execute(sql, params + [months]).fetchall(); conn.close()
    return rows

def top_downtime(slots: Dict[str, Any], n: int = 5):
    where, params = _filters_to_where(slots)
    sql = f"""SELECT a.asset_id, a.name, SUM(work_orders.downtime_hours) as dt
              FROM work_orders JOIN assets a ON a.asset_id = work_orders.asset_id
              {where}
              GROUP BY a.asset_id, a.name ORDER BY dt DESC LIMIT ?"""
    conn = sqlite3.connect(DB_PATH); rows = conn.execute(sql, params + [n]).fetchall(); conn.close()
    return rows

def status_counts(slots: Dict[str, Any]):
    where, params = _filters_to_where(slots)
    sql = f"SELECT status, COUNT(*) FROM work_orders {where} GROUP BY status"
    conn = sqlite3.connect(DB_PATH); rows = conn.execute(sql, params).fetchall(); conn.close()
    d = {"Abierta":0,"En Progreso":0,"Cerrada":0}
    for s,c in rows: d[s]=c
    d["Total"]=sum(d.values()); return d

def kpi_mtbf(slots: Dict[str, Any]) -> float:
    # MTBF simple: diferencia promedio (horas) entre fechas de fallas (CM cerradas) ordenadas
    wslots = {**slots, "type":"CM", "status":"Cerrada"}
    where, params = _filters_to_where(wslots)
    sql = f"SELECT closed_at FROM work_orders {where} AND closed_at IS NOT NULL ORDER BY closed_at"
    conn = sqlite3.connect(DB_PATH); rows = [r[0] for r in conn.execute(sql, params)]
    conn.close()
    times = []
    prev = None
    for s in rows:
        try:
            t = datetime.fromisoformat(s)
            if prev: times.append((t - prev).total_seconds()/3600.0)
            prev = t
        except: pass
    if not times: return 0.0
    return round(sum(times)/len(times), 2)

# --------- Técnicos ----------
def tech_person_counts(slots: Dict[str, Any], person: str):
    w = {**slots, "technician": person}
    where, params = _filters_to_where(w)
    sql = f"SELECT status, COUNT(*) FROM work_orders {where} GROUP BY status"
    conn = sqlite3.connect(DB_PATH); rows = conn.execute(sql, params).fetchall(); conn.close()
    d = {"Abierta":0,"En Progreso":0,"Cerrada":0}
    for s,c in rows: d[s]=c
    d["Total"]=sum(d.values()); return d
