# app/nlu.py
import re, unicodedata
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional, Tuple

# ----------------- normalización -----------------
def _norm(s: str) -> str:
    s = s.lower().strip()
    s = "".join(ch for ch in unicodedata.normalize("NFD", s) if unicodedata.category(ch) != "Mn")
    s = re.sub(r"\s+", " ", s)
    return s

# ----------------- saludos / despedidas -----------------
GREETINGS = [
    "hola","buenas","buenos dias","buen dia","buenas tardes","buenas noches",
    "que puedes hacer","ayuda","help","/start","/help"
]
FAREWELLS = [
    "gracias","nos vemos","bye","adios","hasta luego","hasta pronto",
    "hasta manana","hasta mañana","chao","me despido"
]

def is_greeting(text: str) -> bool:
    t = _norm(text)
    return any(w in t for w in GREETINGS)

def is_farewell(text: str) -> bool:
    t = _norm(text)
    return any(w in t for w in FAREWELLS)

# ----------------- meses / técnicos -----------------
MONTHS = {
    "enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,
    "julio":7,"agosto":8,"septiembre":9,"setiembre":9,"octubre":10,"noviembre":11,"diciembre":12
}
TECHS = ["andres","esteban","juan","sebastian","mateo","jose","pablo"]

# ----------------- intents -----------------
# Acepta variantes comunes en español
FILLER = r"(?:dime|muestr(?:a|ame)|podrias|puedes|por favor|como esta|cual es|indica|reporta|quiero saber|me dices)"

# --- INTENTS ---
INTENTS = {
    rf"\b(mttr|tiempo medio de reparacion)\b": "MTTR",
    rf"\b(mtbf|tiempo medio entre fallas)\b": "MTBF",
    rf"\b(cumplimiento\s*pm|pm compliance|preventiv[oa]s?\s*cumplimiento|cumplimiento\s*de\s*pm)\b": "PM_COMPLIANCE",
    rf"\b(backlog|atraso)\b": "BACKLOG",
    rf"\b(costos?|gastos?)\b": "COSTS",
    rf"\b(paradas|downtime|tiempo muerto|top downtime)\b": "TOP_DOWNTIME",
    rf"\b(estados?|estado|conteos?)\b": "STATUS_COUNTS",
    # preguntas tipo: cuántas órdenes/ots ... tiene <técnico>
    rf"\b(cuant[ao]s?)\b.*\b(ordenes|órdenes|ots)\b.*\b(tiene)\b": "TECH_BY_PERSON",
    # preguntas globales: cuántas órdenes abiertas/cerradas hay?
    rf"\b(cuant[ao]s?)\b.*\b(ordenes|órdenes|ots)\b.*\b(abiert[as]?|cerrad[as]?|progreso|en progreso|totales?)\b.*\b(hay)\b": "STATUS_COUNTS",
}


def detect_intent(text: str) -> str:
    t = _norm(text)

    # 1) Saludos -> HELP
    if any(g in t for g in GREETINGS):
        return "HELP"

    # 2) Pregunta general por órdenes (abiertas/cerradas/en progreso/estado)
    #    SIN mencionar un técnico -> mostrar ESTADO GENERAL (mes actual)
    has_orders = re.search(r"\b(ordenes|órdenes|ots)\b", t) is not None
    mentions_tech = any(tech in t for tech in TECHS)
    mentions_status_word = any(k in t for k in ["abiert", "cerrad", "progreso", "estado", "estados"])
    if has_orders and not mentions_tech:
        return "STATUS_COUNTS"

    # 3) Reviso intents declarados (luego de limpiar muletillas)
    t2 = re.sub(FILLER, "", t)
    for pat, name in INTENTS.items():
        if re.search(pat, t2):
            return name

    # 4) Fallback: si menciona un TÉCNICO y habla de abiertas/cerradas/progreso -> TECH_BY_PERSON
    if any(tech in t for tech in TECHS) and ("abiert" in t or "cerrad" in t or "progreso" in t):
        return "TECH_BY_PERSON"

    # 5) Predeterminado
    return "HELP"

# ----------------- fechas -----------------
def _month_range_from_name(t: str) -> Optional[Tuple[str, str]]:
    for name, m in MONTHS.items():
        mobj = re.search(rf"\b{name}\b(?:\s+(\d{{4}}))?", t)
        if mobj:
            y = int(mobj.group(1)) if mobj.group(1) else datetime.utcnow().year
            start = date(y, m, 1)
            if m == 12:
                end = date(y+1, 1, 1) - timedelta(days=1)
            else:
                end = date(y, m+1, 1) - timedelta(days=1)
            return (start.isoformat(), end.isoformat())
    return None

def _apply_date_pattern(t: str) -> Dict[str, Optional[str]]:
    slots = {"date_from": None, "date_to": None}
    now = datetime.utcnow()

    # mes por nombre (septiembre, septiembre 2025, etc.)
    mr = _month_range_from_name(t)
    if mr:
        slots["date_from"], slots["date_to"] = mr
        return slots

    if re.search(r"\beste mes\b", t):
        slots["date_from"] = now.replace(day=1).date().isoformat()
        slots["date_to"]   = now.date().isoformat(); return slots
    if re.search(r"\bmes pasado\b", t):
        first_this = now.replace(day=1)
        last_prev  = first_this - timedelta(days=1)
        first_prev = last_prev.replace(day=1)
        slots["date_from"] = first_prev.date().isoformat()
        slots["date_to"]   = last_prev.date().isoformat(); return slots
    if re.search(r"\besta semana\b", t):
        start = now - timedelta(days=now.weekday())
        slots["date_from"] = start.date().isoformat()
        slots["date_to"]   = now.date().isoformat(); return slots
    if re.search(r"\bsemana pasada\b", t):
        start_this = now - timedelta(days=now.weekday())
        start_prev = start_this - timedelta(days=7)
        end_prev   = start_this - timedelta(days=1)
        slots["date_from"] = start_prev.date().isoformat()
        slots["date_to"]   = end_prev.date().isoformat(); return slots

    m = re.search(r"\bultimos?\s+(\d+)\s+dias\b", t)
    if m:
        n = int(m.group(1))
        slots["date_from"] = (now - timedelta(days=n)).date().isoformat()
        slots["date_to"]   = now.date().isoformat(); return slots

    m = re.search(r"\bdesde\s+(\d{4}-\d{2}-\d{2})\s+hasta\s+(\d{4}-\d{2}-\d{2})\b", t)
    if m:
        slots["date_from"], slots["date_to"] = m.group(1), m.group(2); return slots

    return slots

# ----------------- extracción de slots -----------------
def extract_slots(text: str, known_sites: List[str] = None, known_areas: List[str] = None) -> Dict[str, Any]:
    t = _norm(text)
    slots: Dict[str, Any] = {
        "site": None, "area": None, "type": None, "status": None,
        "date_from": None, "date_to": None, "technician": None
    }

    # tipo de orden
    if re.search(r"\bpm\b", t): slots["type"] = "PM"
    if re.search(r"\bcm\b", t): slots["type"] = "CM"

    # estado
    if "abiert" in t: slots["status"] = "Abierta"
    elif "cerrad" in t: slots["status"] = "Cerrada"
    elif "progreso" in t: slots["status"] = "En Progreso"

    # técnico (si menciona ordenes/ots o abiertas/cerradas)
    if re.search(r"\b(ordenes|órdenes|ots)\b", t) or ("abiert" in t or "cerrad" in t):
        for tech in TECHS:
            if re.search(rf"\b{tech}\b", t):
                slots["technician"] = tech.capitalize()
                break

    # fechas
    d = _apply_date_pattern(t)
    slots.update(d)
    return slots
