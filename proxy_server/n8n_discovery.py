import os
import time
import re
from typing import Dict, Any, Optional, Set

try:
    import httpx
except Exception:
    httpx = None

try:
    import structlog
    logger = structlog.get_logger()
except Exception:
    import logging
    logger = logging.getLogger('n8n_discovery')


def _tokenize_name(s: str):
    """Return simple tokens from a name/path by splitting on non-alphanumeric characters."""
    toks = re.split(r'[^0-9A-Za-z]+', s or '')
    return [t for t in toks if t]


def _generate_variants(s: str) -> Set[str]:
    """Generate a set of name variants to improve matching.

    Variants include case-insensitive forms, underscore/dash swaps, removal of separators,
    last-segment of dotted names and token-based variants.
    """
    if not s:
        return set()
    variants: Set[str] = set()
    s = s.strip()
    variants.add(s)
    variants.add(s.lower())

    # separator swaps
    variants.add(s.replace(' ', '_'))
    variants.add(s.replace(' ', '-'))
    variants.add(s.replace('-', '_'))
    variants.add(s.replace('_', '-'))
    variants.add(s.replace('_', ' '))

    # remove separators
    variants.add(re.sub(r'[^0-9A-Za-z]', '', s))
    variants.add(re.sub(r'[^0-9A-Za-z]', '', s).lower())

    # dotted last segment
    if '.' in s:
        last = s.split('.')[-1]
        variants.add(last)
        variants.add(last.lower())

    # tokenized pieces
    for tok in _tokenize_name(s):
        variants.add(tok)
        variants.add(tok.lower())
        variants.add(f'functions.{tok}')
        variants.add(f'functions.{tok.lower()}')

    # also add underscore variants for tokens (e.g., Joke_API -> Joke_API, JokeAPI)
    joined = '_'.join(_tokenize_name(s))
    if joined:
        variants.add(joined)
        variants.add(joined.lower())
        variants.add(joined.replace('_', '-'))

    return variants


class ToolDiscovery:
    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None, ttl: int = 60):
        self.base_url = base_url or os.environ.get('N8N_BASE_URL', 'http://n8n:5678')
        self.api_key = api_key or os.environ.get('N8N_API_KEY')
        self.ttl = int(os.environ.get('DISCOVERY_TTL', ttl))
        self._cache: Dict[str, Any] = {}
        self._last_refresh = 0
        # load optional aliases file
        self._aliases = {}
        alias_path = os.path.join(os.path.dirname(__file__), 'aliases.json')
        try:
            if os.path.exists(alias_path):
                with open(alias_path, 'r', encoding='utf-8') as f:
                    import json

                    self._aliases = json.load(f)
        except Exception:
            logger.exception('n8n.discovery.alias_load_fail', path=alias_path)

    def _auth_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self.api_key:
            headers['X-N8N-API-KEY'] = self.api_key
        return headers

    async def refresh(self) -> Dict[str, Dict[str, Any]]:
        """Query n8n REST API to discover active webhook nodes.
        Returns mapping: tool_name -> { 'url': str, 'headers': {..} }
        """
        logger.info('n8n.discovery.start base_url=%s', self.base_url)
        mapping: Dict[str, Dict[str, Any]] = {}
        url = f"{self.base_url}/api/v1/workflows"
        headers = self._auth_headers()
        if httpx is None:
            logger.error('n8n.discovery.fail httpx_missing')
            return mapping

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(url, headers=headers, timeout=15.0)
                resp.raise_for_status()
                workflows = resp.json() or []
            except Exception as e:
                logger.error('n8n.discovery.fail %s', str(e))
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
                    webhookId = node.get('webhookId')
                    params = node.get('parameters') or {}
                    path = params.get('path') or ''
                    node_name = (node.get('name') or wf_name or '')

                    # Build a common set of variants we will register for this node
                    variants: Set[str] = set()
                    if node_name:
                        variants.update(_generate_variants(node_name))
                    if wf_name:
                        variants.update(_generate_variants(wf_name))
                    if path:
                        variants.update(_generate_variants(path.strip('/')))

                    # 1) ChatTrigger / other nodes which expose a webhookId
                    if webhookId:
                        endpoints = []
                        if path:
                            endpoints.append(f"{self.base_url}/webhook/{webhookId}/{path}")
                        endpoints.append(f"{self.base_url}/webhook/{webhookId}")
                        endpoints.append(f"{self.base_url}/webhook/{webhookId}/chat")
                        endpoints.append(f"{self.base_url}/webhook/{webhookId}/webhook")

                        entry_base = {'url': None, 'headers': headers or None, 'node': node_name, 'workflow': wf_name}
                        for endpoint in endpoints:
                            entry = dict(entry_base)
                            entry['url'] = endpoint
                            for v in variants:
                                if v not in mapping:
                                    mapping[v] = entry

                    # 2) Classic webhook node types that reference a path
                    else:
                        ntype = (node.get('type') or '')
                        ntype_l = ntype.lower()
                        if ntype_l.endswith('.webhook') or ntype_l == 'n8n-nodes-base.webhook':
                            endpoints = []
                            if path:
                                endpoints.append(f"{self.base_url}/webhook/{wf_id}/webhook/{path}")
                            endpoints.append(f"{self.base_url}/webhook/{wf_id}")

                            entry_base = {'url': None, 'headers': headers or None, 'node': node_name, 'workflow': wf_name}
                            for endpoint in endpoints:
                                entry = dict(entry_base)
                                entry['url'] = endpoint
                                for v in variants:
                                    if v not in mapping:
                                        mapping[v] = entry

                        # 3) httpRequestTool nodes (tools embedded in workflow) - register them as tools
                        elif ntype_l == 'n8n-nodes-base.httprequesttool' or ntype_l.endswith('.httprequesttool'):
                            # Capture tool properties so the proxy can call the external API on behalf of the agent
                            tool_params = {
                                'url': params.get('url'),
                                'responseType': params.get('responseType'),
                                'onlyContent': params.get('onlyContent'),
                                'optimizeResponse': params.get('optimizeResponse'),
                                'toolDescription': params.get('toolDescription'),
                                'raw_parameters': params,
                            }

                            # For httpRequestTool we want the canonical tool key to be the node name
                            tool_key = node_name.strip() or wf_name or wf_id
                            tool_variants = _generate_variants(tool_key)
                            # also add workflow name variants
                            if wf_name:
                                tool_variants.update(_generate_variants(wf_name))

                            entry = {
                                'toolType': 'httpRequestTool',
                                'node': node_name,
                                'workflow': wf_name,
                                'parameters': tool_params,
                                'headers': headers or None,
                            }

                            for v in tool_variants:
                                if v not in mapping:
                                    mapping[v] = entry
                            # continue to next node
                            continue

            except Exception:
                logger.exception('n8n.discovery.node_parse_fail', workflow=wf.get('id'))

        self._cache = mapping
        self._last_refresh = int(time.time())
        logger.info('n8n.discovery.done count=%d', len(mapping))
        return mapping

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        now = int(time.time())
        # Check aliases first (exact match and lower-case) so aliases work offline
        if key in self._aliases:
            return self._aliases[key]
        if key.lower() in self._aliases:
            return self._aliases[key.lower()]

        if (now - self._last_refresh) > self.ttl:
            try:
                await self.refresh()
            except Exception:
                # refresh may fail in offline or container-host contexts; ignore and rely on cache/aliases
                logger.error('n8n.discovery.refresh_error')

        # Try many normalization variants for the incoming key
        candidates = set()
        candidates.add(key)
        candidates.add(key.lower())
        candidates.update(_generate_variants(key))
        # last segment of dotted names
        if '.' in key:
            candidates.add(key.split('.')[-1])
            candidates.add(key.split('.')[-1].lower())

        for c in candidates:
            if c in self._cache:
                return self._cache[c]

        return None
