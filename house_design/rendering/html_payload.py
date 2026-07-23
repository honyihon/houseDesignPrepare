from __future__ import annotations

import json
from typing import Any


def encode_html_json(payload: dict[str, Any]) -> str:
    """Serialize data for an HTML script block without allowing a closing tag."""
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
