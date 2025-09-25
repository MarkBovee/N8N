import json
import httpx
import structlog
from typing import Dict, Any, Tuple, Optional
from fastapi import HTTPException
from time import time

from .n8n_discovery import N8nDiscovery

logger = structlog.get_logger()

class ToolHandler:
    def __init__(self, registry: Dict[str, Any], timeout: float = 15.0):
        """Registry entries may be either:
        - a string URL, or
        - an object: {"url": "http://...", "headers": {"Authorization": "Bearer ..."}}
        """
        self.registry = registry or {}
        self.timeout = timeout
        # discovery helper (lazy init)
        self.discovery = N8nDiscovery()

    async def execute_tool(self, name: str, args: Dict[str, Any]) -> Any:
        # 1) Try static registry overrides first
        endpoint = self.registry.get(name)
        if not endpoint:
            alt = name.split('.')[-1]
            endpoint = self.registry.get(alt) or self.registry.get(f'functions.{alt}')

        req_headers: Dict[str, str] = {}
        if endpoint:
            if isinstance(endpoint, dict):
                req_headers = endpoint.get('headers', {}) or {}
                endpoint = endpoint.get('url')

        # 2) If registry did not provide an endpoint, try discovery
        discovered_used = False
        if not endpoint:
            discovered = await self.discovery.get(name)
            if discovered:
                endpoint = discovered.get('url')
                req_headers = discovered.get('headers') or {}
                discovered_used = True

        if not endpoint:
            raise HTTPException(status_code=400, detail=f"Unknown tool: {name}")

        async with httpx.AsyncClient() as client:
            try:
                logger.info("tool.call.start", tool=name, endpoint=endpoint, args=args, headers=bool(req_headers), discovered=discovered_used)
                resp = await client.post(endpoint, json=args, headers=req_headers or None, timeout=self.timeout)
                resp.raise_for_status()
                ctype = resp.headers.get("content-type", "")
                if ctype.startswith("application/json"):
                    return resp.json()
                return resp.text
            except httpx.HTTPStatusError as e:
                # On 404/NotRegistered from n8n, refresh discovery and retry once if we were using discovery or registry may be stale
                status = e.response.status_code
                body = e.response.text or ''
                logger.error("tool.call.http_error", tool=name, status=status, body=body[:500])
                if status == 404:
                    try:
                        logger.info('tool.call.404_refresh', tool=name)
                        await self.discovery.refresh()
                        # attempt to find a new endpoint
                        alt_discovered = await self.discovery.get(name)
                        if alt_discovered:
                            new_ep = alt_discovered.get('url')
                            new_headers = alt_discovered.get('headers') or {}
                            logger.info('tool.call.retry', tool=name, endpoint=new_ep)
                            resp2 = await client.post(new_ep, json=args, headers=new_headers or None, timeout=self.timeout)
                            resp2.raise_for_status()
                            ctype2 = resp2.headers.get('content-type', '')
                            if ctype2.startswith('application/json'):
                                return resp2.json()
                            return resp2.text
                    except Exception as e2:
                        logger.error('tool.call.retry_fail', tool=name, error=str(e2))

                raise HTTPException(status_code=502, detail=f"Tool {name} returned error: {status}")
            except httpx.RequestError as e:
                logger.error("tool.call.request_error", tool=name, error=str(e))
                raise HTTPException(status_code=502, detail=f"Tool execution failed: {e}")

    async def execute_tool_with_metrics(self, name: str, args: Dict[str, Any]) -> Tuple[Any, float]:
        start = time()
        try:
            result = await self.execute_tool(name, args)
            dur = time() - start
            logger.info("tool.call.success", tool=name, duration=dur)
            return result, dur
        except Exception:
            dur = time() - start
            logger.error("tool.call.fail", tool=name, duration=dur)
            raise

async def run_tool_calls_async(tool_handler: "ToolHandler", tool_calls: list):
    results = []
    for call in tool_calls:
        name = None
        args = {}
        if isinstance(call, dict):
            if call.get('function') and isinstance(call['function'], dict):
                name = call['function'].get('name')
                raw_args = call['function'].get('arguments')
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                except Exception:
                    args = {'raw': raw_args}
            else:
                name = call.get('name') or call.get('function_name')
                args = call.get('args') or call.get('arguments') or {}
        if not name:
            name = 'unknown_tool'
        try:
            result, duration = await tool_handler.execute_tool_with_metrics(name, args)
            content_str = result if isinstance(result, str) else json.dumps(result)
            # Return as a 'function' role message (OpenAI-style) so upstream
            # accepts the payload. Keep name and content fields.
            results.append({
                'role': 'function',
                'name': name,
                'content': content_str,
                'execution_time': duration
            })
        except Exception as e:
            # Log and return an inline tool result indicating the failure so the
            # caller can continue processing instead of the whole endpoint failing.
            logger.error('tool.call.exception_handled', tool=name, error=str(e))
            # On failure, return a function-style message with the error text so
            # the follow-up payload remains well-formed for upstream models.
            results.append({
                'role': 'function',
                'name': name,
                'content': f'[tool execution failed: {str(e)}]'
            })
    return results
