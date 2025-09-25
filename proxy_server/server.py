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

class OpenAIMessage(BaseModel):
    role: str
    content: str
    name: Optional[str] = None

class OpenAIChatRequest(BaseModel):
    model: str
    messages: List[OpenAIMessage]
    temperature: Optional[float] = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1, le=4096)
    stream: Optional[bool] = False
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Any] = None

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
    try:
        validated_model = validate_model(request.model)
        if PROXY_TOOL_PASSTHROUGH:
            logger.info('pass_through.forwarding', tools=bool(request.tools), stream=request.stream)
            passthrough_messages = []
            for m in request.messages:
                md = {'role': m.role, 'content': m.content}
                if getattr(m, 'name', None):
                    md['name'] = m.name
                passthrough_messages.append(md)
            github_request = {
                'model': validated_model,
                'messages': passthrough_messages,
                'temperature': request.temperature,
                'stream': request.stream
            }
            # Debug: log the exact JSON payload we will send upstream (sanitized; no auth)
            try:
                outbound = dict(github_request)
                logger.info('outbound_payload_debug', payload=json.dumps(outbound)[:20000], size=len(json.dumps(outbound).encode('utf-8')))
            except Exception:
                logger.exception('outbound_payload_debug_failed')
            if request.max_tokens is not None:
                github_request['max_tokens'] = request.max_tokens
            # The GitHub inference endpoint may not accept arbitrary 'tools' or
            # 'tool_choice' pass-through fields. Remove them for passthrough
            # requests to avoid upstream 400/413 and log the removal for
            # diagnostics.
            if request.tools is not None:
                if ALLOW_PASSTHROUGH_TOOLS:
                    github_request['tools'] = request.tools
                    logger.info('passthrough.include_tools', note='including tools for passthrough', tools_count=len(request.tools) if isinstance(request.tools, list) else None)
                else:
                    logger.info('passthrough.drop_tools', note='dropping tools for passthrough', tools_count=len(request.tools) if isinstance(request.tools, list) else None)
            if request.tool_choice is not None:
                if ALLOW_PASSTHROUGH_TOOLS:
                    github_request['tool_choice'] = request.tool_choice
                    logger.info('passthrough.include_tool_choice', note='including tool_choice for passthrough')
                else:
                    logger.info('passthrough.drop_tool_choice', note='dropping tool_choice for passthrough')
            async with httpx.AsyncClient() as client:
                # Diagnostics: measure payload size and log; if too large attempt trimming
                raw_bytes = json.dumps(github_request).encode('utf-8')
                size = len(raw_bytes)
                if size > MAX_UPSTREAM_PAYLOAD_BYTES:
                    logger.warning('payload.too_large', size=size, max=MAX_UPSTREAM_PAYLOAD_BYTES, strategy=TRIM_MESSAGES_STRATEGY)
                    if TRIM_MESSAGES_STRATEGY == 'drop_oldest':
                        original_non_system = [m for m in github_request['messages'] if m.get('role') != 'system']
                        preserved_system = [m for m in github_request['messages'] if m.get('role') == 'system']
                        non_system = list(original_non_system)
                        while non_system and len(json.dumps({**github_request, 'messages': preserved_system + non_system}).encode('utf-8')) > MAX_UPSTREAM_PAYLOAD_BYTES:
                            non_system.pop(0)
                        if not non_system and original_non_system:
                            last = dict(original_non_system[-1])
                            if isinstance(last.get('content'), str):
                                last['content'] = (last['content'][:120] + '...') if len(last['content']) > 120 else last['content']
                            non_system = [last]
                        github_request['messages'] = preserved_system + non_system
                        size = len(json.dumps(github_request).encode('utf-8'))
                        logger.info('payload.trimmed', new_size=size, message_count=len(github_request['messages']))

                # Attempt the upstream call, and if 413 happens, try aggressive trims and retry once
                upstream_resp = await client.post(f'{GITHUB_BASE_URL}/chat/completions', json=github_request, headers={'Authorization': f'Bearer {GITHUB_TOKEN}'}, timeout=120)
                if upstream_resp.status_code >= 400:
                    # Safe summary: model, message count, first message role and length, payload bytes
                    msgs = github_request.get('messages', [])
                    first = msgs[0] if msgs else {}
                    logger.error('upstream.reject.summary', status=upstream_resp.status_code, model=github_request.get('model'), message_count=len(msgs), first_role=first.get('role'), first_len=(len(first.get('content') or '') if isinstance(first.get('content'), str) else None), payload_bytes=len(json.dumps(github_request).encode('utf-8')))
                    try:
                        body_text = upstream_resp.text
                        logger.error('upstream.reject.body', body=body_text[:1000])
                    except Exception:
                        logger.exception('upstream.reject.body.failed')
                if upstream_resp.status_code == 413:
                    logger.warning('upstream.413_received', initial_size=len(json.dumps(github_request).encode('utf-8')))
                    trimmed = _aggressive_trim_request(github_request, MAX_UPSTREAM_PAYLOAD_BYTES)
                    try:
                        upstream_resp = await client.post(f'{GITHUB_BASE_URL}/chat/completions', json=trimmed, headers={'Authorization': f'Bearer {GITHUB_TOKEN}'}, timeout=120)
                        logger.info('upstream.retry_after_trim', status=upstream_resp.status_code, new_size=len(json.dumps(trimmed).encode('utf-8')))
                        if upstream_resp.status_code >= 400:
                            msgs = trimmed.get('messages', [])
                            first = msgs[0] if msgs else {}
                            logger.error('upstream.reject.summary', status=upstream_resp.status_code, model=trimmed.get('model'), message_count=len(msgs), first_role=first.get('role'), first_len=(len(first.get('content') or '') if isinstance(first.get('content'), str) else None), payload_bytes=len(json.dumps(trimmed).encode('utf-8')))
                            try:
                                logger.error('upstream.reject.body', body=upstream_resp.text[:1000])
                            except Exception:
                                logger.exception('upstream.reject.body.failed')
                    except Exception as e:
                        logger.exception('upstream.retry_failed')
                        raise
            # Log successful upstream response body for diagnostics (truncated)
            try:
                upstream_body_text = upstream_resp.text
                logger.info('upstream.response.body', body=upstream_body_text[:2000], status=upstream_resp.status_code, payload_bytes=len(json.dumps(github_request).encode('utf-8')))
            except Exception:
                logger.exception('upstream.response.body.failed')

            if request.stream:
                async def passthrough_stream():
                    logger.info('stream.pass_through.start')
                    async with httpx.AsyncClient(timeout=None) as client2:
                        async with client2.stream('POST', f'{GITHUB_BASE_URL}/chat/completions', json=github_request, headers={'Authorization': f'Bearer {GITHUB_TOKEN}'}) as stream_resp:
                            stream_resp.raise_for_status()
                            async for line in stream_resp.aiter_lines():
                                if line:
                                    yield line + '\n'
                    logger.info('stream.pass_through.end')
                media_type = upstream_resp.headers.get('Content-Type', 'text/event-stream')
                return StreamingResponse(passthrough_stream(), media_type=media_type)
            else:
                try:
                    upstream_resp.raise_for_status()
                except httpx.RequestError as e:
                    raise HTTPException(status_code=502, detail=str(e))
                try:
                    body = upstream_resp.json()
                    # Log the downstream JSON response (truncated)
                    try:
                        logger.info('upstream.response.json', body=json.dumps(body)[:20000], status=upstream_resp.status_code)
                    except Exception:
                        logger.exception('upstream.response.json.failed')
                    return JSONResponse(content=body, headers=build_headers())
                except Exception:
                    text_body = upstream_resp.text
                    logger.info('upstream.response.text', body=text_body[:2000], status=upstream_resp.status_code)
                    return JSONResponse(content={'choices': [{'message': {'role': 'assistant', 'content': text_body}}]}, headers=build_headers())

        raw_messages = []
        for m in request.messages:
            d = {'role': m.role, 'content': m.content}
            if getattr(m, 'name', None):
                d['name'] = m.name
            raw_messages.append(d)
        prepared_messages = prepare_messages_for_local_ai(raw_messages)
        github_request = {
            'model': validated_model,
            'messages': prepared_messages,
            'temperature': request.temperature,
            'stream': request.stream
        }
        if request.max_tokens:
            github_request['max_tokens'] = request.max_tokens
        if getattr(request, 'tools', None):
            try:
                local_tools = transform_tools_for_local_ai(request.tools)
                tool_lines = [f"- {t['name']}: {t.get('description','(no description)')}" for t in local_tools]
                tool_list_text = "\n".join(tool_lines)
                instruction = (
                    'The following tools are available to you:\n'
                    f"{tool_list_text}\n\n"
                    'If you decide to call a tool, respond with a single-line JSON object exactly in this form:'
                    ' {"tool_call": {"name": "<tool_name>", "arguments": { ... } } }'
                    ' Do not add any extra text on the same line.'
                )
                # Debug: log the instruction so we can inspect its size/content (truncated)
                try:
                    logger.info('tool_instruction.debug', length=len(instruction), instruction=instruction[:3000])
                except Exception:
                    logger.exception('tool_instruction.debug_failed')
                # Also include the structured tools declaration so upstream may use
                # function/tool calling if it supports it.
                try:
                    github_request['tools'] = local_tools
                    logger.info('local_tools.attached', count=len(local_tools))
                except Exception:
                    logger.exception('attach_local_tools_failed')
                github_request['messages'] = [{'role': 'system', 'content': instruction}] + github_request['messages']
                # Include the original tools definition in the outgoing request so
                # upstream or local model can be aware of the tool signatures.
                try:
                    github_request['tools'] = request.tools
                    logger.info('local.include_tools', note='including tools in outgoing github_request', tools_count=len(request.tools) if isinstance(request.tools, list) else None)
                except Exception:
                    logger.exception('include_tools_failed')
            except Exception:
                logger.exception('tools.parse_failed')

        # Pre-flight payload diagnostics & trimming for local tool orchestration path
        raw_bytes = json.dumps(github_request).encode('utf-8')
        size = len(raw_bytes)
        if size > MAX_UPSTREAM_PAYLOAD_BYTES:
            logger.warning('payload.too_large', size=size, max=MAX_UPSTREAM_PAYLOAD_BYTES, strategy=TRIM_MESSAGES_STRATEGY)
            if TRIM_MESSAGES_STRATEGY == 'drop_oldest':
                preserved_system = [m for m in github_request['messages'] if m.get('role') == 'system']
                non_system = [m for m in github_request['messages'] if m.get('role') != 'system']
                while non_system and len(json.dumps({**github_request, 'messages': preserved_system + non_system}).encode('utf-8')) > MAX_UPSTREAM_PAYLOAD_BYTES:
                    non_system.pop(0)
                github_request['messages'] = preserved_system + non_system
                size = len(json.dumps(github_request).encode('utf-8'))
                logger.info('payload.trimmed', new_size=size, message_count=len(github_request['messages']))
        async with httpx.AsyncClient() as client:
            response = await client.post(f'{GITHUB_BASE_URL}/chat/completions', json=github_request, headers={'Authorization': f'Bearer {GITHUB_TOKEN}'}, timeout=120)
            if response.status_code >= 400:
                msgs = github_request.get('messages', [])
                first = msgs[0] if msgs else {}
                logger.error('upstream.reject.summary', status=response.status_code, model=github_request.get('model'), message_count=len(msgs), first_role=first.get('role'), first_len=(len(first.get('content') or '') if isinstance(first.get('content'), str) else None), payload_bytes=len(json.dumps(github_request).encode('utf-8')))
                try:
                    logger.error('upstream.reject.body', body=response.text[:1000])
                except Exception:
                    logger.exception('upstream.reject.body.failed')
            if response.status_code == 413:
                logger.warning('upstream.413_received', initial_size=len(json.dumps(github_request).encode('utf-8')))
                trimmed = _aggressive_trim_request(github_request, MAX_UPSTREAM_PAYLOAD_BYTES)
                try:
                    response = await client.post(f'{GITHUB_BASE_URL}/chat/completions', json=trimmed, headers={'Authorization': f'Bearer {GITHUB_TOKEN}'}, timeout=120)
                    logger.info('upstream.retry_after_trim', status=response.status_code, new_size=len(json.dumps(trimmed).encode('utf-8')))
                    if response.status_code >= 400:
                        msgs = trimmed.get('messages', [])
                        first = msgs[0] if msgs else {}
                        logger.error('upstream.reject.summary', status=response.status_code, model=trimmed.get('model'), message_count=len(msgs), first_role=first.get('role'), first_len=(len(first.get('content') or '') if isinstance(first.get('content'), str) else None), payload_bytes=len(json.dumps(trimmed).encode('utf-8')))
                except Exception:
                    logger.exception('upstream.retry_failed')
                    raise
        # Log the upstream response body for diagnostics (truncated) in the
        # local orchestration path so we can inspect why the assistant returned
        # an empty content field.
        try:
            upstream_body_text = response.text
            logger.info('upstream.response.body', body=upstream_body_text[:20000], status=response.status_code, payload_bytes=len(json.dumps(github_request).encode('utf-8')))
        except Exception:
            logger.exception('upstream.response.body.failed')
        try:
            response.raise_for_status()
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=str(e))

        if request.stream:
            async def generate():
                prefix_mode = None
                first = True
                async with httpx.AsyncClient(timeout=None) as client2:
                    async with client2.stream('POST', f'{GITHUB_BASE_URL}/chat/completions', json=github_request, headers={'Authorization': f'Bearer {GITHUB_TOKEN}'}) as stream_resp:
                        async for line in stream_resp.aiter_lines():
                            if not line:
                                continue
                            if first:
                                first = False
                                prefix_mode = 'sse' if line.strip().startswith('data:') else 'raw'
                            payload = None
                            if prefix_mode == 'sse' and line.strip().startswith('data:'):
                                payload_txt = line.strip()[len('data:'):].strip()
                                if payload_txt == '[DONE]':
                                    yield 'data: [DONE]\n\n'
                                    break
                                try:
                                    payload = json.loads(payload_txt)
                                except Exception:
                                    payload = None
                            else:
                                try:
                                    payload = json.loads(line.strip())
                                except Exception:
                                    payload = None
                            tool_calls = []
                            if payload:
                                try:
                                    for ch in payload.get('choices', []) if isinstance(payload.get('choices', []), list) else []:
                                        msg = ch.get('message', {})
                                        if isinstance(msg, dict) and msg.get('tool_calls'):
                                            tool_calls.extend(msg.get('tool_calls'))
                                        content = msg.get('content') if isinstance(msg, dict) else None
                                        if isinstance(content, str):
                                            tool_calls.extend(extract_tool_calls(content))
                                except Exception:
                                    tool_calls = []
                                if 'extracted_tool_calls' in payload:
                                    tool_calls.extend(payload['extracted_tool_calls'])
                            if tool_calls and not PROXY_TOOL_PASSTHROUGH:
                                try:
                                    tool_results = await run_tool_calls_async(tool_handler, tool_calls)
                                    messages_for_rerun = list(prepared_messages) + tool_results
                                    async with httpx.AsyncClient() as client3:
                                        follow_payload = {**github_request, 'messages': messages_for_rerun, 'stream': False}
                                        # Remove tools/tool_choice from follow-ups to avoid upstream rejects
                                        follow_payload.pop('tools', None)
                                        follow_payload.pop('tool_choice', None)
                                        try:
                                            logger.info('outbound_followup_payload_debug', payload=json.dumps(follow_payload)[:20000], size=len(json.dumps(follow_payload).encode('utf-8')))
                                        except Exception:
                                            logger.exception('outbound_followup_payload_debug_failed')
                                        follow_resp = await client3.post(f'{GITHUB_BASE_URL}/chat/completions', json=follow_payload, headers={'Authorization': f'Bearer {GITHUB_TOKEN}'}, timeout=120)
                                        follow_resp.raise_for_status()
                                        local_follow = follow_resp.json()
                                    transformed_follow = transform_local_response(local_follow)
                                    serialized = json.dumps(transformed_follow)
                                    yield f'data: {serialized}\n\n' if prefix_mode == 'sse' else serialized + '\n'
                                except Exception:
                                    err_payload = json.dumps({'choices': [{'message': {'role': 'assistant', 'content': '[tool execution failed]'}}]})
                                    yield f'data: {err_payload}\n\n' if prefix_mode == 'sse' else err_payload + '\n'
                                break
                            else:
                                yield line + ('\n' if prefix_mode != 'sse' else '\n\n')
                
            media_type = response.headers.get('Content-Type', 'text/event-stream')
            return StreamingResponse(generate(), media_type=media_type)
        else:
            messages_loop = list(prepared_messages)
            local_resp = response.json()
            if PROXY_TOOL_PASSTHROUGH:
                return JSONResponse(content=transform_local_response(local_resp), headers=build_headers())
            for _ in range(MAX_TOOL_ITERATIONS):
                transformed = transform_local_response(local_resp)
                try:
                    choices = transformed.get('choices', [])
                    tool_calls = []
                    for ch in choices:
                        m = ch.get('message', {})
                        if m.get('tool_calls'):
                            tool_calls.extend(m.get('tool_calls'))
                        content = m.get('content')
                        if isinstance(content, str):
                            tool_calls.extend([
                                {'name': tc.get('name'), 'args': tc.get('arguments', {})} for tc in extract_tool_calls(content)
                            ])
                    if tool_calls:
                        tool_results = await run_tool_calls_async(tool_handler, tool_calls)
                        messages_loop.extend(tool_results)
                        github_request['messages'] = messages_loop
                        # Re-run size check before follow-up call
                        follow_raw = json.dumps(github_request).encode('utf-8')
                        follow_size = len(follow_raw)
                        if follow_size > MAX_UPSTREAM_PAYLOAD_BYTES and TRIM_MESSAGES_STRATEGY == 'drop_oldest':
                            preserved_system = [m for m in github_request['messages'] if m.get('role') == 'system']
                            non_system = [m for m in github_request['messages'] if m.get('role') != 'system']
                            while non_system and len(json.dumps({**github_request, 'messages': preserved_system + non_system}).encode('utf-8')) > MAX_UPSTREAM_PAYLOAD_BYTES:
                                non_system.pop(0)
                            github_request['messages'] = preserved_system + non_system
                            logger.info('payload.trimmed.follow_up', new_size=len(json.dumps(github_request).encode('utf-8')), message_count=len(github_request['messages']))
                        async with httpx.AsyncClient() as client4:
                            try:
                                follow_payload2 = dict(github_request)
                                follow_payload2.pop('tools', None)
                                follow_payload2.pop('tool_choice', None)
                                logger.info('outbound_followup_payload_debug', payload=json.dumps(follow_payload2)[:20000], size=len(json.dumps(follow_payload2).encode('utf-8')))
                            except Exception:
                                logger.exception('outbound_followup_payload_debug_failed')
                            resp2 = await client4.post(f'{GITHUB_BASE_URL}/chat/completions', json=follow_payload2, headers={'Authorization': f'Bearer {GITHUB_TOKEN}'}, timeout=120)
                            if resp2.status_code == 413:
                                logger.warning('upstream.413_on_followup', size=len(json.dumps(github_request).encode('utf-8')))
                                trimmed_follow = _aggressive_trim_request(github_request, MAX_UPSTREAM_PAYLOAD_BYTES)
                                resp2 = await client4.post(f'{GITHUB_BASE_URL}/chat/completions', json=trimmed_follow, headers={'Authorization': f'Bearer {GITHUB_TOKEN}'}, timeout=120)
                                logger.info('upstream.retry_after_trim_followup', status=resp2.status_code, new_size=len(json.dumps(trimmed_follow).encode('utf-8')))
                            resp2.raise_for_status()
                            local_resp = resp2.json()
                        continue
                    return JSONResponse(content=transformed, headers=build_headers())
                except HTTPException:
                    raise
                except Exception as e:
                    logger.error('tool.loop.error', error=str(e))
                    return JSONResponse(content=local_resp, headers=build_headers())
            return JSONResponse(content=transform_local_response(local_resp), headers=build_headers())
    except Exception as e:
        logger.error('chat.endpoint.error', error=str(e))
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
