# app/logging_conf.py
import os, json, logging, logging.handlers, re
from datetime import datetime

SECRET_PATTERNS = [
    re.compile(r"(bot\d+:|AAG|AAH)[A-Za-z0-9_-]{20,}"),   # tokens tg (heurístico)
    re.compile(r"[A-Za-z0-9]{24,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{27,}"), # estilo JWT
]

def _sanitize(value: str) -> str:
    if not isinstance(value, str):
        return value
    masked = value
    for p in SECRET_PATTERNS:
        masked = p.sub("***", masked)
    return masked

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
            "lvl": record.levelname,
            "msg": _sanitize(record.getMessage()),
            "logger": record.name,
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        if hasattr(record, "extra"):
            # asegura que no explote por objetos raros
            try:
                payload["extra"] = json.loads(json.dumps(record.extra, default=str))
            except Exception:
                payload["extra"] = str(record.extra)
        return json.dumps(payload, ensure_ascii=False)

def setup_logging():
    log_dir  = os.environ.get("LOG_DIR", "logs")
    os.makedirs(log_dir, exist_ok=True)
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    root = logging.getLogger()
    root.setLevel(level)

    # Consola
    sh = logging.StreamHandler()
    sh.setFormatter(JsonFormatter())
    root.addHandler(sh)

    # Archivo rotativo (5 MB x 7)
    fh = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, "app.log"), maxBytes=5*1024*1024, backupCount=7, encoding="utf-8"
    )
    fh.setFormatter(JsonFormatter())
    root.addHandler(fh)

    # Reduce ruido de libs
    logging.getLogger("uvicorn").setLevel("WARNING")
    logging.getLogger("httpx").setLevel("WARNING")
