# formatters.py
from datetime import datetime
from typing import Dict, Any, Iterable, Tuple, Optional


# -------------- Helpers --------------

def _period_label(slots: Optional[Dict[str, Any]]) -> str:
    """
    Devuelve:
      • ' (Mes actual)' si date_from = 1er día del mes y date_to = hoy
      • ' (YYYY-MM-DD → YYYY-MM-DD)' si hay rango explícito
      • '' si no hay fechas en los slots
    """
    if not slots:
        return ""

    df = slots.get("date_from")
    dt = slots.get("date_to")
    if not df or not dt:
        return ""

    try:
        today = datetime.utcnow().date()
        start = today.replace(day=1)
        if df == start.isoformat() and dt == today.isoformat():
            return " (Mes actual)"
        return f" ({df} → {dt})"
    except Exception:
        # Si por algún motivo el parse falla, igual mostramos el rango crudo
        return f" ({df} → {dt})"


def _fmt_money(n: float) -> str:
    """
    Formatea dinero con separador de miles y coma decimal (estilo ES).
    1234567.8 -> '1.234.567,80'
    """
    try:
        s = f"{float(n):,.2f}"  # '1,234,567.80'
        s = s.replace(",", "X").replace(".", ",").replace("X", ".")
        return s
    except Exception:
        return str(n)
        
def _range_tag(slots: dict) -> str:
    df = slots.get("date_from")
    dt = slots.get("date_to")
    if df and dt:
        return f"({df} → {dt})"
    return "(Mes actual)"

# -------------- KPI formatters --------------

def f_mttr(v: float, slots: Dict[str, Any]) -> str:
    return f"🛠️ MTTR: {v} h.{_period_label(slots)}"


def f_backlog(v: float, slots: Dict[str, Any]) -> str:
    return f"📚 Backlog: {v} días promedio.{_period_label(slots)}"


def f_pm(v: float, slots: Dict[str, Any]) -> str:
    return f"✅ Cumplimiento PM: {v}%." + _period_label(slots)


def f_costs(rows: Iterable[Tuple[str, float]], slots: Dict[str, Any]) -> str:
    """
    rows: iterable de (YYYY-MM, total)
    """
    lbl = _period_label(slots)
    rows = list(rows or [])
    if not rows:
        return f"💸 Sin costos en el periodo{lbl}."
    partes = [f"{ym}: ${_fmt_money(total)}" for ym, total in rows]
    return f"💸 Costos mensuales: " + "; ".join(partes) + f".{lbl}"


def f_top_dt(rows: Iterable[Tuple[str, str, float]], slots: Dict[str, Any]) -> str:
    """
    rows: iterable de (asset_id, name, downtime_hours)
    """
    lbl = _period_label(slots)
    rows = list(rows or [])
    if not rows:
        return f"⏱️ Sin paradas registradas en el periodo{lbl}."
    lines = [f"{aid} · {name}: {round(dt, 1)} h" for aid, name, dt in rows]
    return "⛔ Top downtime" + lbl + ":\n- " + "\n- ".join(lines)


def f_status(counts: dict, slots: dict) -> str:
    tag = _range_tag(slots)
    opened = counts.get("Abierta", 0)
    prog   = counts.get("En Progreso", 0)
    closed = counts.get("Cerrada", 0)
    total  = opened + prog + closed
    return (
        f"📊 Estados {tag}:\n"
        f"• Abiertas: {opened}\n"
        f"• En Progreso: {prog}\n"
        f"• Cerradas: {closed}\n"
        f"• Total: {total}"
    )

# -------------- Técnicos --------------

def f_tech_summary(open_map: Dict[str, int], closed_map: Dict[str, int], slots: Dict[str, Any]) -> str:
    """
    open_map: {tecnico: abiertas}
    closed_map: {tecnico: cerradas}
    """
    lbl = _period_label(slots)
    techs = sorted(set(open_map.keys()) | set(closed_map.keys()))
    if not techs:
        return f"👷 Órdenes por técnico{lbl}: no hay datos."

    lines = []
    for t in techs:
        o = open_map.get(t, 0)
        c = closed_map.get(t, 0)
        lines.append(f"• {t}: abiertas {o}, cerradas {c}")
    return "👷 Órdenes por técnico" + lbl + ":\n" + "\n".join(lines)


def f_tech_person(person: str, counts: dict, slots: dict) -> str:
    tag = _range_tag(slots)
    opened = counts.get("Abierta", 0)
    prog   = counts.get("En Progreso", 0)
    closed = counts.get("Cerrada", 0)
    total  = opened + prog + closed
    return (
        f"👤 {person} {tag}:\n"
        f"• Abiertas: {opened}\n"
        f"• En Progreso: {prog}\n"
        f"• Cerradas: {closed}\n"
        f"• Total: {total}"
    )
def f_daily_report(k_mttr: float, k_backlog: float, k_pm: float,
                   states: dict, topdt_rows, slots: dict | None = None) -> str:
    """
    Reporte compacto diario. Usa _period_label(slots) para indicar el periodo.
    """
    lbl = _period_label(slots or {})
    # Estados
    s_ab = states.get("Abierta", 0)
    s_ep = states.get("En Progreso", 0)
    s_ce = states.get("Cerrada", 0)
    s_to = states.get("Total", 0)

    # Top downtime
    if topdt_rows:
        lines = [f"- {aid} · {name}: {round(dt,1)} h" for aid, name, dt in topdt_rows]
        top_block = "\n".join(lines)
    else:
        top_block = "Sin paradas registradas en el periodo."

    return (
        f"📮 Reporte diario{lbl}\n"
        f"• 🛠️ MTTR: {k_mttr} h\n"
        f"• 📚 Backlog: {k_backlog} días\n"
        f"• ✅ Cumplimiento PM: {k_pm}%\n"
        f"• 📊 Estados: Abiertas {s_ab} · En Progreso {s_ep} · Cerradas {s_ce} · Total {s_to}\n"
        f"• ⛔ Top downtime:\n{top_block}"
    )


# -------------- (Opcional) MTBF --------------

def f_mtbf(v: float, slots: Dict[str, Any]) -> str:
    """Si implementas MTBF en data.py, este formatter ya queda listo."""
    return f"⚙️ MTBF: {v} h.{_period_label(slots)}"
