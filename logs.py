import contextvars
import json
import sys
from datetime import datetime, timezone

# Set once per HTTP request; every log line written while handling it carries the same ID.
request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)


def log(level: str, msg: str, **fields) -> None:
    record = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "level": level, "msg": msg, "request_id": request_id.get(), **fields}
    print(json.dumps(record, default=str, ensure_ascii=False), file=sys.stdout, flush=True)
