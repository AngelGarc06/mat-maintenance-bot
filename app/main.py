import os, httpx, logging
from datetime import datetime
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app import nlu, data, formatters as F
from app.logging_conf import setup_logging
from app.version import as_dict as version_dict, as_text as version_text

# --- Config ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
WEBHOOK_SECRET     = os.environ.get("WEBHOOK_SECRET", "")
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

HELP_TEXT = (
    "👋 Hola, ¿cómo estás?\n\n"
    "Soy MAT (Maintenance Agent Tool). Puedo ayudarte con KPIs:\n"
    "• MTTR • MTBF • Backlog • Cumplimiento PM • Costos • Top downtime • Estados.\n\n"
    "EJEMPLOS RÁPIDOS\n"
    "• mttr este mes\n"
    "• top downtime últimos 30 días\n"
    "• costos últimos 60 días\n"
    "• cumplimiento pm agosto\n"
    "• ¿cuántas órdenes abiertas tiene Andres?\n"
    "• ¿cuántas órdenes cerradas tiene Sebastian en septiembre?\n\n"
    "REPORTES AUTOMÁTICOS\n"
    "• Comenzar: /subscribe\n"
    "• Detener: /unsubscribe\n"
    "• Hora diaria: /setreport 07:00"
)

# --- App / Logging / Scheduler ---
setup_logging()
log = logging.getLogger("app")

app = FastAPI()
scheduler = AsyncIOScheduler()

# --- Middleware de logging HTTP ---
@app.middleware("http")
async def add_logging(request: Request, call_next):
    start = datetime.utcnow()
    try:
        resp = await call_next(request)
        dur_ms = (datetime.utcnow() - start).total_seconds() * 1000
        log.info(
            "http_request",
            extra={"method": request.method, "path": request.url.path, "status": getattr(resp, "status_code", None), "ms": round(dur_ms, 1)}
        )
        return resp
    except Exception:
        log.exception("http_error", extra={"path": request.url.path})
        return JSONResponse({"detail": "internal error"}, status_code=500)

# --- Telegram send helper ---
async def send_message(chat_id: int, text: str):
    if not text:
        return
    async with httpx.AsyncClient(timeout=15) as client:
        await client.post(
            f"{BASE_URL}/sendMessage",
            json={"chat_id": chat_id, "text": text},
        )

# --- Lifecycle hooks ---
@app.on_event("startup")
async def _startup():
    data.ensure_schema()
    scheduler.start()
    # Cargar trabajos de reportes que estén guardados en DB
    for chat_id, hhmm in data.all_chat_ids_with_time():
        try:
            hh, mm = map(int, hhmm.split(":"))
            scheduler.add_job(
                send_daily_report,
                CronTrigger(hour=hh, minute=mm),
                args=[chat_id],
                id=f"rep_{chat_id}",
                replace_existing=True,
            )
        except Exception:
            pass

@app.on_event("shutdown")
async def _shutdown():
    if scheduler.running:
        scheduler.shutdown(wait=False)

# --- Daily report job (mes en curso) ---
async def send_daily_report(chat_id: int):
    # Rango del mes actual: 1 → hoy (para que el label sea “Mes actual”)
    today = datetime.utcnow().date()
    start = today.replace(day=1)
    slots_month = {"date_from": start.isoformat(), "date_to": today.isoformat()}

    k_mttr = data.kpi_mttr(slots_month)
    k_back = data.kpi_backlog_days(slots_month)
    k_pm   = data.kpi_pm_compliance(slots_month)
    states = data.status_counts(slots_month)
    topdt  = data.top_downtime(slots_month)

    txt = F.f_daily_report(k_mttr, k_back, k_pm, states, topdt, slots_month)
    await send_message(chat_id, txt)

# --- Health / Version ---
@app.get("/health")
def health():
    return {"ok": True, "version": version_dict()}

@app.get("/version")
def version():
    return version_dict()

# --- Telegram webhook ---
@app.post("/telegram/webhook")
async def telegram_webhook(
    req: Request,
    x_tg_secret: str = Header(None, alias="X-Telegram-Bot-Api-Secret-Token"),
):
    if WEBHOOK_SECRET and x_tg_secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="invalid signature")

    body = await req.json()
    msg = body.get("message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    text    = (msg.get("text") or "").strip()
    if not text:
        return {"ok": True}

    # Tocar sesión
    data.update_last_seen(chat_id)

    low = text.lower()

    # Saludo inmediato
    if nlu.is_greeting(text):
        await send_message(chat_id, HELP_TEXT)
        return {"ok": True}

    # Despedida natural
    if nlu.is_farewell(text):
        await send_message(chat_id, "¡Gracias! Me alegra ayudarte. Nos vemos mañana 👋")
        data.update_last_seen(chat_id)
        return {"ok": True}

    # Utilidades
    if low.startswith("/version"):
        await send_message(chat_id, version_text())
        return {"ok": True}

    # --- Comandos de reportes ---
    if low.startswith("/setreport"):
        parts = text.split()
        if len(parts) != 2 or ":" not in parts[1]:
            await send_message(chat_id, "⚠️ Formato de hora inválido. Usa HH:MM (ej. 07:00).")
        else:
            try:
                hh, mm = map(int, parts[1].split(":"))
                hhmm = f"{hh:02d}:{mm:02d}"
                data.set_report_time(chat_id, hhmm)
                scheduler.add_job(
                    send_daily_report,
                    CronTrigger(hour=hh, minute=mm),
                    args=[chat_id],
                    id=f"rep_{chat_id}",
                    replace_existing=True,
                )
                await send_message(chat_id, f"⏰ Hora de reporte establecida en {hhmm} (mes en curso).")
            except Exception:
                await send_message(chat_id, "⚠️ No pude interpretar esa hora. Usa HH:MM (ej. 07:00).")
        return {"ok": True}

    if low.startswith("/subscribe"):
        hhmm = data.get_report_time(chat_id) or "07:00"
        hh, mm = map(int, hhmm.split(":"))
        data.set_report_time(chat_id, hhmm)
        scheduler.add_job(
            send_daily_report,
            CronTrigger(hour=hh, minute=mm),
            args=[chat_id],
            id=f"rep_{chat_id}",
            replace_existing=True,
        )
        await send_message(
            chat_id,
            f"🔔 Suscripción activada. Enviaré el reporte diario (mes en curso) a la hora configurada ({hhmm})."
        )
        return {"ok": True}

    if low.startswith("/unsubscribe"):
        job = scheduler.get_job(f"rep_{chat_id}")
        if job:
            scheduler.remove_job(job.id)
        data.set_report_time(chat_id, None)
        await send_message(chat_id, "🔕 Suscripción cancelada. Ya no enviaré reportes diarios.")
        return {"ok": True}

    if low.startswith("/testrun"):
        await send_daily_report(chat_id)
        return {"ok": True}

    # --- NLU/Slots ---
    sites, areas = data.query_known_values()
    intent = nlu.detect_intent(text)
    slots  = nlu.extract_slots(text, sites, areas)

    # Si no hay rango, por defecto “mes actual” (1..hoy)
    def _ensure_month_default(s: dict):
        if not s.get("date_from") and not s.get("date_to"):
            today = datetime.utcnow().date()
            start = today.replace(day=1)
            s["date_from"] = start.isoformat()
            s["date_to"]   = today.isoformat()

    # --- Intent routing ---
    if intent in {
        "MTTR", "MTBF", "PM_COMPLIANCE", "BACKLOG",
        "COSTS", "TOP_DOWNTIME", "STATUS_COUNTS", "TECH_BY_PERSON"
    }:
        _ensure_month_default(slots)

    if intent == "MTTR":
        out = F.f_mttr(data.kpi_mttr(slots), slots)

    elif intent == "MTBF":
        out = F.f_mtbf(data.kpi_mtbf(slots), slots)

    elif intent == "PM_COMPLIANCE":
        out = F.f_pm(data.kpi_pm_compliance(slots), slots)

    elif intent == "BACKLOG":
        out = F.f_backlog(data.kpi_backlog_days(slots), slots)

    elif intent == "COSTS":
        out = F.f_costs(data.kpi_costs_monthly(slots), slots)

    elif intent == "TOP_DOWNTIME":
        out = F.f_top_dt(data.top_downtime(slots), slots)

    elif intent == "STATUS_COUNTS":
        # Siempre mostrar el resumen completo del mes, sin filtrar por estado.
        slots["status"] = None
        out = F.f_status(data.status_counts(slots), slots)

    elif intent == "TECH_BY_PERSON":
        person = slots.get("technician")
        if not person:
            out = "¿De qué técnico quieres ver las órdenes? (Andres, Esteban, Juan, Sebastian, Mateo, Jose, Pablo)"
        else:
            # Resumen completo del técnico aunque el texto diga 'abiertas' o 'cerradas'
            slots.pop("status", None)
            counts = data.tech_person_counts(slots, person)
            out = F.f_tech_person(person, counts, slots)

    else:
        out = (
            "Lo siento, no puedo ayudarte con esa solicitud. Por ahora solo puedo apoyar con: "
            "MTTR, MTBF, Backlog, Cumplimiento PM, Costos, Top downtime, Estados y órdenes por técnico.\n\n"
            "Ejemplos:\n• MTTR este mes\n• MTBF este mes\n• Costos septiembre\n• Cumplimiento PM agosto\n"
            "• ¿Cuántas órdenes cerradas tiene Sebastian en septiembre?"
        )

    await send_message(chat_id, out)
    return {"ok": True}
