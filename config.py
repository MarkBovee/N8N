from __future__ import annotations
import os
import json
from typing import Any, Dict, Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    github_token: Optional[str] = None
    github_base_url: str = os.environ.get('GITHUB_BASE_URL', 'https://models.github.ai/inference')
    tool_registry: Dict[str, Any] = {}
    # Default to local tool orchestration to allow tool instruction generation
    # Change to True if you want to forward requests to upstream passthrough by default
    proxy_tool_passthrough: bool = False
    max_tool_iterations: int = 3
    max_upstream_payload_bytes: int = 200_000
    trim_messages_strategy: str = 'drop_oldest'
    tool_timeout: int = 30
    log_dir: str = './logs'
    log_level: str = 'info'
    # When true, the original `tools` and `tool_choice` fields from incoming
    # requests will be forwarded to the upstream GitHub Models inference API
    # when running in passthrough mode. Set to False to drop them (safer).
    allow_passthrough_tools: bool = True

    class Config:
        env_prefix = ''


def _load_tool_registry_from_env() -> Dict[str, Any]:
    raw = os.environ.get('TOOL_REGISTRY_JSON', '')
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def get_settings() -> Settings:
    s = Settings()
    # load tool registry if provided via env
    try:
        s.tool_registry = _load_tool_registry_from_env()
    except Exception:
        s.tool_registry = {}
    return s
