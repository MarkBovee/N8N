import os
import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
import structlog

from config import get_settings
from .tool_handler import ToolHandler, run_tool_calls_async
from .utils_tool_calls import extract_tool_calls, StreamHandler
from .n8n_discovery import ToolDiscovery

settings = get_settings()

# Structured logging configuration (idempotent)
os.makedirs(settings.log_dir, exist_ok=True)
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt='iso'),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True
)
logger = structlog.get_logger()

GITHUB_TOKEN = settings.github_token
GITHUB_BASE_URL = settings.github_base_url
TOOL_REGISTRY = settings.tool_registry
PROXY_TOOL_PASSTHROUGH = settings.proxy_tool_passthrough
MAX_TOOL_ITERATIONS = settings.max_tool_iterations
MAX_UPSTREAM_PAYLOAD_BYTES = settings.max_upstream_payload_bytes
TRIM_MESSAGES_STRATEGY = settings.trim_messages_strategy
ALLOW_PASSTHROUGH_TOOLS = getattr(settings, 'allow_passthrough_tools', False)

tool_handler = ToolHandler(TOOL_REGISTRY, timeout=settings.tool_timeout)
discovery = ToolDiscovery()

class OpenAIMessage(BaseModel):
    role: str
    content: str
    name: Optional[str] = None

class OpenAIChatRequest(BaseModel):
    model: str
    messages: List[OpenAIMessage]
    temperature: Optional[float] = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    stream: Optional[bool] = False
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Any] = None
    # Add stream_options for usage reporting in streams
    stream_options: Optional[Dict[str, Any]] = None

    @validator('messages')
    def validate_messages_not_empty(cls, v):
        if not v:
            raise ValueError('Messages cannot be empty')
        return v

    @validator('tools')
    def validate_tools_format(cls, v):
        if v is None:
            return v
        for tool in v:
            if not isinstance(tool, dict):
                raise ValueError('Each tool must be a dictionary')
            if tool.get('type') != 'function':
                raise ValueError('Only function tools are supported')
            if not tool.get('function', {}).get('name'):
                raise ValueError('Tool function must have a name')
        return v

class OpenAIModel(BaseModel):
    id: str
    object: str = 'model'
    created: int
    owned_by: str = 'github-models'

class OpenAIModelsResponse(BaseModel):
    object: str = 'list'
    data: List[OpenAIModel]

def validate_model(model: str) -> str:
    mapping = {
        'gpt-4o': 'openai/gpt-4o',
        'gpt-4o-mini': 'openai/gpt-4o-mini',
        'gpt-4': 'openai/gpt-4',
        'gpt-3.5-turbo': 'openai/gpt-3.5-turbo'
    }
    if model in mapping:
        logger.info('model.mapped', original=model, mapped=mapping[model])
        return mapping[model]
    if '/' in model and model.startswith(('openai/', 'microsoft/', 'meta/')):
        logger.info('model.as_is', model=model)
        return model
    logger.warning('model.unknown_fallback', original=model, fallback='openai/gpt-4o-mini')
    return 'openai/gpt-4o-mini'

def trim_request_payload(request_data: Dict[str, Any], max_bytes: int) -> Dict[str, Any]:
    """
    Trims the request payload to be under max_bytes.
    Tries to remove oldest non-system messages first.
    """
    request_copy = json.loads(json.dumps(request_data)) # Deep copy
    
    if len(json.dumps(request_copy).encode('utf-8')) <= max_bytes:
        return request_copy

    messages = request_copy.get("messages", [])
    system_messages = [m for m in messages if m.get("role") == "system"]
    user_messages = [m for m in messages if m.get("role") != "system"]

    while len(json.dumps(request_copy).encode('utf-8')) > max_bytes and user_messages:
        user_messages.pop(0)
        request_copy["messages"] = system_messages + user_messages
        
    logger.info(
        "payload.trimmed",
        original_size=len(json.dumps(request_data).encode('utf-8')),
        new_size=len(json.dumps(request_copy).encode('utf-8')),
        messages_remaining=len(request_copy.get("messages", [])),
    )
    
    return request_copy

def prepare_messages_for_local_ai(messages: List[Dict[str, Any]]):
    transformed = []
    for msg in messages:
        if msg.get('role') == 'tool':
            transformed.append({'role': 'function', 'name': msg.get('name'), 'content': msg.get('content')})
        else:
            transformed.append(msg)
    return transformed

def transform_tools_for_local_ai(tools: List[Dict[str, Any]]):
    local = []
    for t in tools:
        if isinstance(t, dict) and t.get('type') == 'function' and t.get('function'):
            fd = t['function']
            local.append({
                'name': fd.get('name'),
                'description': fd.get('description'),
                'parameters': fd.get('parameters')
            })
    return local

def transform_local_response(local_response: Dict[str, Any]):
    if not local_response:
        return {'choices': []}
    # If the upstream returned choices, preserve them but normalize so that
    # each choice.message has a 'content' (may be None) and preserves
    # any embedded 'tool_calls'. This prevents collapsing the whole response
    # into an empty content when tool_calls are present inside choices.
    if isinstance(local_response, dict) and local_response.get('choices'):
        normalized_choices = []
        try:
            for ch in local_response.get('choices', []):
                if isinstance(ch, dict) and isinstance(ch.get('message'), dict):
                    msg = dict(ch.get('message'))
                    # Ensure role exists
                    role = msg.get('role', 'assistant')
                    content = msg.get('content') if 'content' in msg else None
                    out_msg = {'role': role}
                    # Preserve content even if it's None (we'll handle None later)
                    out_msg['content'] = content
                    # Preserve tool_calls if present
                    if msg.get('tool_calls'):
                        out_msg['tool_calls'] = msg.get('tool_calls')
                    normalized_choices.append({'message': out_msg})
                else:
                    normalized_choices.append(ch)
            return {'choices': normalized_choices}
        except Exception:
            # Fall back to returning the original structure if normalization fails
            return local_response

    # If upstream returned a top-level tool_calls array, convert to assistant choice
    if local_response.get('tool_calls'):
        return {
            'choices': [{
                'message': {
                    'role': 'assistant',
                    'content': local_response.get('content', ''),
                    'tool_calls': [
                        {
                            'id': f"call_{uuid4().hex[:8]}",
                            'type': 'function',
                            'function': {
                                'name': c.get('name'),
                                'arguments': json.dumps(c.get('args', {}))
                            }
                        }
                        for c in local_response.get('tool_calls', [])
                    ]
                }
            }]
        }

    # Otherwise, represent the response as a single assistant choice with content
    return {
        'choices': [{
            'message': {
                'role': 'assistant',
                'content': local_response.get('content', '') if isinstance(local_response, dict) else str(local_response)
            }
        }]
    }

def build_headers():
    return {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'}


def _aggressive_trim_request(github_request: Dict[str, Any], target_bytes: int) -> Dict[str, Any]:
    """Attempt stronger trimming to get the serialized request under target_bytes.
    Strategies (in order):
    - drop non-system messages from the front (already done elsewhere but repeat)
    - truncate long message contents (keep roles and names)
    - remove the 'tools' key if present
    Returns the trimmed request (may be unchanged if nothing to do).
    """
    req = dict(github_request)
    try:
        # quick size
        raw = json.dumps(req).encode('utf-8')
        if len(raw) <= target_bytes:
            return req

        # 1) drop non-system messages from the start
        preserved_system = [m for m in req.get('messages', []) if m.get('role') == 'system']
        non_system = [m for m in req.get('messages', []) if m.get('role') != 'system']
        while non_system and len(json.dumps({**req, 'messages': preserved_system + non_system}).encode('utf-8')) > target_bytes:
            non_system.pop(0)
        req['messages'] = preserved_system + non_system
        raw = json.dumps(req).encode('utf-8')
        if len(raw) <= target_bytes:
            logger.info('payload.aggressive_trim', new_size=len(raw), message_count=len(req.get('messages', [])))
            return req

        # 2) truncate longest messages (cut to 1024 chars, then 512, then 256)
        lengths = [len(m.get('content','') or '') for m in req.get('messages', [])]
        if lengths:
            caps = [1024, 512, 256, 128]
            for cap in caps:
                for m in req.get('messages', []):
                    if isinstance(m.get('content'), str) and len(m['content']) > cap:
                        m['content'] = m['content'][:cap] + '...'
                raw = json.dumps(req).encode('utf-8')
                if len(raw) <= target_bytes:
                    logger.info('payload.truncated_messages', cap=cap, new_size=len(raw))
                    return req

        # 3) remove tools block if present (may be large)
        if 'tools' in req:
            req.pop('tools', None)
            raw = json.dumps(req).encode('utf-8')
            if len(raw) <= target_bytes:
                logger.info('payload.removed_tools', new_size=len(raw))
                return req

        # still large: as last resort, truncate all non-system message contents to small length
        for m in req.get('messages', []):
            if m.get('role') != 'system' and isinstance(m.get('content'), str):
                m['content'] = (m['content'][:120] + '...') if len(m['content']) > 120 else m['content']
        raw = json.dumps(req).encode('utf-8')
        logger.info('payload.last_resort_truncate', new_size=len(raw))
        return req
    except Exception:
        logger.exception('aggressive_trim_failed')
        return github_request

app = FastAPI(title='GitHub Models Proxy')
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.on_event('startup')
async def _startup_refresh_discovery():
    """On server startup, refresh discovery and log configured + discovered tool names for debugging."""
    try:
        logger.info('startup.tools.status', note='refreshing n8n discovery and listing configured tools')
        discovered = await discovery.refresh()
        logger.info('startup.configured_tools', configured=list(TOOL_REGISTRY.keys()))
        logger.info('startup.discovered_tools', discovered_count=len(discovered), discovered_keys=list(discovered.keys())[:100], note='aliasing and underscore/dash variants included')
    except Exception:
        logger.exception('startup.discovery_failed')

@app.get('/')
async def root():
    return {'message': 'GitHub Models Proxy'}

@app.get('/health')
async def health():
    status = {'status': 'healthy', 'timestamp': datetime.now().isoformat(), 'tool_count': len(TOOL_REGISTRY), 'configured_tools': list(TOOL_REGISTRY.keys())}
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get('https://models.github.ai/v1/models', headers={'Authorization': f'Bearer {GITHUB_TOKEN}'}, timeout=5)
            status['github_models'] = 'connected' if r.status_code == 200 else f'error:{r.status_code}'
    except Exception:
        status['github_models'] = 'unreachable'
    return status

@app.get('/v1/models')
async def list_models(authorization: str = Header(None)):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get('https://models.github.ai/v1/models', headers={'Authorization': f'Bearer {GITHUB_TOKEN}'}, timeout=10)
            response.raise_for_status()
            return response.json()
    except Exception:
        created_time = int(datetime.now().timestamp())
        models = [OpenAIModel(id=m, created=created_time) for m in ['openai/gpt-4o', 'openai/gpt-4o-mini']]
        return OpenAIModelsResponse(data=models).model_dump()

@app.post('/v1/chat/completions')
async def chat_completions(request: OpenAIChatRequest, authorization: str = Header(None)):
    """
    Main endpoint for proxying chat completions.
    - If PROXY_TOOL_PASSTHROUGH is True, it forwards the request directly to GitHub Models,
      including tools and tool_choice, and returns the response as-is.
    - Otherwise, it uses a local tool orchestration loop.
    """
    try:
        validated_model = validate_model(request.model)

        # Build the base request for GitHub Models API
        github_request = {
            "model": validated_model,
            "messages": [msg.model_dump(exclude_none=True) for msg in request.messages],
            "temperature": request.temperature,
            "stream": request.stream,
        }
        if request.max_tokens:
            github_request["max_tokens"] = request.max_tokens
        if request.tools:
            github_request["tools"] = request.tools
        if request.tool_choice:
            github_request["tool_choice"] = request.tool_choice
        if request.stream and request.stream_options:
            github_request["stream_options"] = request.stream_options

        # Trim payload if it exceeds the max size
        payload_bytes = len(json.dumps(github_request).encode('utf-8'))
        if payload_bytes > MAX_UPSTREAM_PAYLOAD_BYTES:
            logger.warning(
                "payload.too_large",
                size=payload_bytes,
                max_size=MAX_UPSTREAM_PAYLOAD_BYTES,
                strategy="trim_oldest_messages",
            )
            github_request = trim_request_payload(github_request, MAX_UPSTREAM_PAYLOAD_BYTES)

        # Log the prepared request for debugging
        logger.info(
            "outbound.request.prepared",
            model=validated_model,
            stream=request.stream,
            tools_present=bool(request.tools),
            tool_choice_present=bool(request.tool_choice),
        )

        # Handle streaming responses
        if request.stream:
            async def stream_generator():
                async with httpx.AsyncClient(timeout=120.0) as client:
                    async with client.stream(
                        "POST",
                        f"{GITHUB_BASE_URL}/chat/completions",
                        json=github_request,
                        headers={"Authorization": f"Bearer {GITHUB_TOKEN}"},
                    ) as response:
                        response.raise_for_status()
                        async for chunk in response.aiter_bytes():
                            yield chunk

            return StreamingResponse(
                stream_generator(),
                media_type="text/event-stream",
            )

        # Handle non-streaming responses
        else:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{GITHUB_BASE_URL}/chat/completions",
                    json=github_request,
                    headers={"Authorization": f"Bearer {GITHUB_TOKEN}"},
                )
                response.raise_for_status()
                
                # Forward the exact response from GitHub, including 'usage' and 'tool_calls'
                resp_json = response.json()
                logger.info("outbound.response.received", body=json.dumps(resp_json)[:1000])
                return JSONResponse(content=resp_json, status_code=response.status_code)

    except httpx.HTTPStatusError as e:
        logger.error(
            "http_status_error",
            status_code=e.response.status_code,
            response_text=e.response.text,
            request_details=json.dumps(github_request)[:1000] if 'github_request' in locals() else "github_request not available",
        )
        return JSONResponse(
            content={"error": {"message": e.response.text, "type": "upstream_error"}},
            status_code=e.response.status_code,
        )
    except Exception as e:
        logger.exception("chat.endpoint.error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.error('http_exception', status=exc.status_code, detail=exc.detail, path=str(request.url))
    return JSONResponse(status_code=exc.status_code, content={'error': {'message': exc.detail, 'type': 'api_error', 'code': exc.status_code}})

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception('unhandled_exception', path=str(request.url))
    return JSONResponse(status_code=500, content={'error': {'message': 'Internal server error', 'type': 'server_error'}})

# Uvicorn entrypoint convenience
if __name__ == '__main__':
    if not GITHUB_TOKEN:
        print('ERROR: GITHUB_TOKEN required')
        raise SystemExit(1)
    import uvicorn
    uvicorn.run('proxy_server.server:app', host='0.0.0.0', port=11434, log_level='info')
