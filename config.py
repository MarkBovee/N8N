from __future__ import annotations
import os
import json
from typing import Any, Dict, Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    github_token: str = os.environ.get('GITHUB_TOKEN', '')
    github_base_url: str = os.environ.get('GITHUB_BASE_URL', 'https://models.github.ai/inference')
    tool_registry: Dict[str, Any] = {}
    # Default to passthrough since we are now handling tools directly
    proxy_tool_passthrough: bool = True
    max_tool_iterations: int = 3
        max_upstream_payload_bytes: int = 15000
    trim_messages_strategy: str = 'drop_oldest'
    tool_timeout: int = 30
    log_dir: str = './logs'
    log_level: str = 'info'
    # This should be True to allow n8n to control tool execution
    allow_passthrough_tools: bool = True

    class Config:
        env_prefix = ''


def get_settings() -> Settings:
    s = Settings()
    return s
