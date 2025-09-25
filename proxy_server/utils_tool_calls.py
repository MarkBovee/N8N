import json
import re
import structlog
from typing import List, Dict, Any, Optional, Tuple

logger = structlog.get_logger()

TOOL_JSON_BLOCK = re.compile(r'```json\s*(\{.*?\})\s*```', re.DOTALL)
INLINE_TOOL_OBJ = re.compile(r'\{[^{}]*"tool_call"[^{}]*\}')


def extract_tool_calls(content: str) -> List[Dict[str, Any]]:
    tool_calls: List[Dict[str, Any]] = []
    if not content or not isinstance(content, str):
        return tool_calls
    # Direct JSON
    try:
        parsed = json.loads(content.strip())
        if isinstance(parsed, dict) and parsed.get('tool_call'):
            tc = parsed['tool_call']
            tool_calls.append({'name': tc.get('name'), 'args': tc.get('arguments', {})})
    except Exception:
        pass
    # JSON code blocks
    for match in TOOL_JSON_BLOCK.findall(content):
        try:
            parsed = json.loads(match)
            if isinstance(parsed, dict) and parsed.get('tool_call'):
                tc = parsed['tool_call']
                tool_calls.append({'name': tc.get('name'), 'args': tc.get('arguments', {})})
        except Exception:
            continue
    # Inline objects
    for match in INLINE_TOOL_OBJ.findall(content):
        try:
            parsed = json.loads(match)
            if isinstance(parsed, dict) and parsed.get('tool_call'):
                tc = parsed['tool_call']
                tool_calls.append({'name': tc.get('name'), 'args': tc.get('arguments', {})})
        except Exception:
            continue
    return tool_calls

class StreamHandler:
    def __init__(self):
        self.accumulated = ""

    def process_line(self, line: str) -> Tuple[Optional[dict], bool]:
        if not line.strip():
            return None, False
        if line.strip() == 'data: [DONE]':
            return {'done': True}, True
        if line.startswith('data: '):
            payload_txt = line[6:].strip()
            try:
                payload = json.loads(payload_txt)
            except Exception:
                return None, False
            try:
                choices = payload.get('choices', [])
                for ch in choices:
                    delta = ch.get('delta', {})
                    content = delta.get('content')
                    if content:
                        self.accumulated += content
                # Try extraction when braces balanced
                if self._braces_balanced(self.accumulated):
                    tcs = extract_tool_calls(self.accumulated)
                    if tcs:
                        payload['extracted_tool_calls'] = tcs
                return payload, False
            except Exception:
                return None, False
        return None, False

    def _braces_balanced(self, text: str) -> bool:
        return text.count('{') == text.count('}') and text.count('{') > 0
