import logging
import json
from typing import Any
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "tool_name"):
            payload["tool_name"] = record.tool_name
        if hasattr(record, "params"):
            payload["params"] = self._sanitize(record.params)
        if hasattr(record, "status"):
            payload["status"] = record.status
        if hasattr(record, "duration_ms"):
            payload["duration_ms"] = record.duration_ms
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _sanitize(value: Any) -> Any:
        if isinstance(value, dict):
            result: dict[str, Any] = {}
            for key, item in value.items():
                normalized_key = key
                if normalized_key.endswith("Phone") or normalized_key in {"ownerAddr", "chipNo"}:
                    result[key] = "[REDACTED]"
                else:
                    result[key] = JsonFormatter._sanitize(item)
            return result
        if isinstance(value, list):
            return [JsonFormatter._sanitize(item) for item in value]
        return value


def configure_logging() -> None:
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
