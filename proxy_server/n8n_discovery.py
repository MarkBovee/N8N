import os
import time
import httpx
import structlog
from typing import Dict, Any, Optional

logger = structlog.get_logger()


class N8nDiscovery:
    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None, ttl: int = 60):
        self.base_url = base_url or os.environ.get('N8N_BASE_URL', 'http://n8n:5678')
        self.api_key = api_key or os.environ.get('N8N_API_KEY')
        self.ttl = int(os.environ.get('DISCOVERY_TTL', ttl))
        self._cache: Dict[str, Any] = {}
        self._last_refresh = 0

    def _auth_headers(self) -> Dict[str, str]:
        headers = {}
        if self.api_key:
            headers['X-N8N-API-KEY'] = self.api_key
        return headers


def _tokenize_name(s: str):
    """Return simple tokens from a name/path by splitting on non-alphanumeric characters."""
    import re
    toks = re.split(r'[^0-9A-Za-z]+', s)
    return [t for t in toks if t]

    async def refresh(self) -> Dict[str, Dict[str, Any]]:
        """Query n8n REST API to discover active webhook nodes.
        Returns mapping: tool_name -> { 'url': str, 'headers': {..} }
        """
        logger.info('n8n.discovery.start', base_url=self.base_url)
        mapping: Dict[str, Dict[str, Any]] = {}
        url = f"{self.base_url}/api/v1/workflows"
        headers = self._auth_headers()
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(url, headers=headers, timeout=15.0)
                resp.raise_for_status()
                workflows = resp.json() or []
            except Exception as e:
                logger.error('n8n.discovery.fail', error=str(e))
                return mapping

        # workflows can be a list or object depending on n8n version; normalize
        items = workflows if isinstance(workflows, list) else workflows.get('data', [])
        for wf in items:
            try:
                wf_id = wf.get('id')
                wf_name = wf.get('name')
                active = wf.get('active', False)
                if not active:
                    continue
                nodes = wf.get('nodes') or []
                for node in nodes:
                    if node.get('type', '').lower().endswith('.webhook') or node.get('type') == 'n8n-nodes-base.webhook':
                        node_name = node.get('name') or wf_name or ''
                        params = node.get('parameters') or {}
                        path = params.get('path') or ''
                        # Try to determine webhookId if present in node
                        webhookId = node.get('webhookId') or node.get('webhookId')
                        # Construct runtime URL patterns we've observed; prefer using workflow id
                        if webhookId:
                            endpoint = f"{self.base_url}/webhook/{webhookId}/{path}" if path else f"{self.base_url}/webhook/{webhookId}"
                        else:
                            endpoint = f"{self.base_url}/webhook/{wf_id}/webhook/{path}" if path else f"{self.base_url}/webhook/{wf_id}"

                        # Normalize tool name: prefer node name, fall back to workflow name
                        tool_key = node_name.strip()
                        if not tool_key:
                            tool_key = wf_name or wf_id

                        entry = {'url': endpoint, 'headers': headers or None}
                        # Primary keys
                        mapping[tool_key] = entry
                        mapping[tool_key.lower()] = entry

                        # last segment variants
                        alt = tool_key.split('.')[-1]
                        mapping[alt] = entry
                        mapping[alt.lower()] = entry

                        # functions.* variants
                        mapping[f'functions.{alt}'] = entry
                        mapping[f'functions.{alt.lower()}'] = entry

                        # workflow-name tokens
                        if wf_name:
                            mapping[wf_name] = entry
                            mapping[wf_name.lower()] = entry
                            for tok in _tokenize_name(wf_name):
                                mapping[tok] = entry
                                mapping[tok.lower()] = entry
                                mapping[f'functions.{tok}'] = entry

                        # path-based tokens (strip slashes)
                        if path:
                            p = path.strip('/')
                            if p:
                                mapping[p] = entry
                                mapping[p.lower()] = entry
                                for tok in _tokenize_name(p):
                                    mapping[tok] = entry
                                    mapping[tok.lower()] = entry
                                    mapping[f'functions.{tok}'] = entry
            except Exception:
                logger.exception('n8n.discovery.node_parse_fail', workflow=wf.get('id'))

        self._cache = mapping
        self._last_refresh = int(time.time())
        logger.info('n8n.discovery.done', count=len(mapping))
        return mapping

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        now = int(time.time())
        if (now - self._last_refresh) > self.ttl:
            await self.refresh()
        # Try direct match, then lower-case, then last segment
        if key in self._cache:
            return self._cache[key]
        lower = key.lower()
        if lower in self._cache:
            return self._cache[lower]
        alt = key.split('.')[-1]
        return self._cache.get(alt)
