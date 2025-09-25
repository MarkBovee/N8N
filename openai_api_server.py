#!/usr/bin/env python3
"""
OpenAI-Compatible API Server for n8n Integration (Standalone Version)
Provides OpenAI API endpoints that use local Ollama models
"""

import os
import json
import asyncio
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn
import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# OpenAI API Models
class OpenAIMessage(BaseModel):
    role: str = Field(..., description="The role of the message author")
    content: str = Field(..., description="The content of the message")

class OpenAIChoice(BaseModel):
    index: int
    message: OpenAIMessage
    finish_reason: Optional[str] = "stop"

class OpenAIUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class OpenAIChatResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[OpenAIChoice]
    usage: OpenAIUsage

class OpenAIChatRequest(BaseModel):
    model: str = Field(..., description="The model to use")
    messages: List[OpenAIMessage] = Field(..., description="List of messages")
    temperature: Optional[float] = Field(0.7, ge=0, le=2)
    max_tokens: Optional[int] = Field(None, ge=1)
    stream: Optional[bool] = Field(False, description="Whether to stream responses")
    top_p: Optional[float] = Field(1.0, ge=0, le=1)

class OpenAIModel(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str = "ollama"

class OpenAIModelsResponse(BaseModel):
    object: str = "list"
    data: List[OpenAIModel]

class OpenAIErrorDetail(BaseModel):
    message: str
    type: str
    code: str

class OpenAIError(BaseModel):
    error: OpenAIErrorDetail

# Streaming response models
class OpenAIDelta(BaseModel):
    role: Optional[str] = None
    content: Optional[str] = None

class OpenAIStreamChoice(BaseModel):
    index: int
    delta: OpenAIDelta
    finish_reason: Optional[str] = None

class OpenAIStreamResponse(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: List[OpenAIStreamChoice]

class OpenAICompatibleAPI:
    """OpenAI-compatible API wrapper for local Ollama models"""
    
    def __init__(self, ollama_base_url: str = "http://localhost:11434"):
        self.ollama_base_url = ollama_base_url.rstrip('/')
        
    def get_available_models(self) -> List[str]:
        """Get list of available Ollama models"""
        try:
            response = requests.get(f"{self.ollama_base_url}/api/tags", timeout=5)
            response.raise_for_status()
            models_data = response.json()
            return [model["name"] for model in models_data.get("models", [])]
        except Exception as e:
            logger.error(f"Failed to get Ollama models: {e}")
            return ["llama3.2:latest", "llama3.1:8b", "qwen2.5:7b"]  # Fallback models
    
    def map_openai_to_ollama_model(self, openai_model: str) -> str:
        """Map OpenAI model names to available Ollama models"""
        model_mapping = {
            "gpt-3.5-turbo": "llama3.2:latest",
            "gpt-4": "llama3.1:8b", 
            "gpt-4o": "qwen2.5:7b",
            "gpt-4o-mini": "llama3.2:latest",
            "gpt-4-turbo": "llama3.1:8b",
        }
        
        # If exact match exists, use it
        if openai_model in model_mapping:
            return model_mapping[openai_model]
        
        # Otherwise, try to find the requested model in available models
        available_models = self.get_available_models()
        if openai_model in available_models:
            return openai_model
        
        # Default fallback
        return available_models[0] if available_models else "llama3.2:latest"
    
    async def chat_completion(self, request: OpenAIChatRequest) -> OpenAIChatResponse:
        """Handle non-streaming chat completion"""
        try:
            # Map model
            ollama_model = self.map_openai_to_ollama_model(request.model)
            
            # Format messages for Ollama
            prompt = self._format_messages_for_ollama(request.messages)
            
            # Make request to Ollama
            ollama_request = {
                "model": ollama_model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": request.temperature or 0.7,
                    "top_p": request.top_p or 1.0,
                }
            }
            
            if request.max_tokens:
                ollama_request["options"]["num_predict"] = request.max_tokens
            
            response = requests.post(
                f"{self.ollama_base_url}/api/generate",
                json=ollama_request,
                timeout=120
            )
            response.raise_for_status()
            
            ollama_response = response.json()
            
            # Convert to OpenAI format
            return self._convert_to_openai_response(
                ollama_response, 
                request.model, 
                request.messages[-1].content if request.messages else "",
                ollama_response.get("response", "")
            )
            
        except Exception as e:
            logger.error(f"Chat completion error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def stream_chat_completion(self, request: OpenAIChatRequest) -> AsyncGenerator[str, None]:
        """Handle streaming chat completion"""
        try:
            # Map model
            ollama_model = self.map_openai_to_ollama_model(request.model)
            
            # Format messages for Ollama
            prompt = self._format_messages_for_ollama(request.messages)
            
            # Make streaming request to Ollama
            ollama_request = {
                "model": ollama_model,
                "prompt": prompt,
                "stream": True,
                "options": {
                    "temperature": request.temperature or 0.7,
                    "top_p": request.top_p or 1.0,
                }
            }
            
            if request.max_tokens:
                ollama_request["options"]["num_predict"] = request.max_tokens
            
            response = requests.post(
                f"{self.ollama_base_url}/api/generate",
                json=ollama_request,
                stream=True,
                timeout=120
            )
            response.raise_for_status()
            
            response_id = f"chatcmpl-{uuid.uuid4().hex}"
            created = int(datetime.now().timestamp())
            
            # Stream the response
            for line in response.iter_lines():
                if line:
                    try:
                        chunk_data = json.loads(line.decode('utf-8'))
                        
                        if chunk_data.get("response"):
                            # Convert to OpenAI streaming format
                            stream_chunk = OpenAIStreamResponse(
                                id=response_id,
                                created=created,
                                model=request.model,
                                choices=[OpenAIStreamChoice(
                                    index=0,
                                    delta=OpenAIDelta(content=chunk_data["response"]),
                                    finish_reason=None
                                )]
                            )
                            
                            yield f"data: {stream_chunk.model_dump_json()}\n\n"
                        
                        if chunk_data.get("done", False):
                            # Send final chunk
                            final_chunk = OpenAIStreamResponse(
                                id=response_id,
                                created=created,
                                model=request.model,
                                choices=[OpenAIStreamChoice(
                                    index=0,
                                    delta=OpenAIDelta(),
                                    finish_reason="stop"
                                )]
                            )
                            yield f"data: {final_chunk.model_dump_json()}\n\n"
                            yield "data: [DONE]\n\n"
                            break
                            
                    except json.JSONDecodeError:
                        continue
                        
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            error_chunk = {
                "error": {
                    "message": str(e),
                    "type": "server_error",
                    "code": "internal_error"
                }
            }
            yield f"data: {json.dumps(error_chunk)}\n\n"
    
    def _format_messages_for_ollama(self, messages: List[OpenAIMessage]) -> str:
        """Convert OpenAI messages to a single prompt for Ollama"""
        formatted_parts = []
        
        for msg in messages:
            if msg.role == "system":
                formatted_parts.append(f"System: {msg.content}")
            elif msg.role == "user":
                formatted_parts.append(f"User: {msg.content}")
            elif msg.role == "assistant":
                formatted_parts.append(f"Assistant: {msg.content}")
        
        formatted_parts.append("Assistant:")
        return "\n\n".join(formatted_parts)
    
    def _convert_to_openai_response(
        self, 
        ollama_response: Dict[str, Any], 
        model: str,
        prompt: str,
        completion: str
    ) -> OpenAIChatResponse:
        """Convert Ollama response to OpenAI format"""
        
        # Estimate token usage (rough approximation)
        prompt_tokens = len(prompt.split())
        completion_tokens = len(completion.split())
        
        return OpenAIChatResponse(
            id=f"chatcmpl-{uuid.uuid4().hex}",
            created=int(datetime.now().timestamp()),
            model=model,
            choices=[OpenAIChoice(
                index=0,
                message=OpenAIMessage(
                    role="assistant",
                    content=completion
                ),
                finish_reason="stop"
            )],
            usage=OpenAIUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens
            )
        )

# Global API instance
api = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global api
    
    # Get Ollama URL from environment or use default
    ollama_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
    api = OpenAICompatibleAPI(ollama_url)
    
    logger.info("🚀 Starting OpenAI-Compatible API Server for n8n")
    logger.info(f"📡 Ollama Base URL: {api.ollama_base_url}")
    
    # Test Ollama connection
    try:
        models = api.get_available_models()
        logger.info(f"✅ Connected to Ollama. Available models: {', '.join(models[:3])}{'...' if len(models) > 3 else ''}")
    except Exception as e:
        logger.warning(f"⚠️  Could not connect to Ollama: {e}")
    
    yield
    logger.info("🛑 Shutting down OpenAI-Compatible API Server")

# Create FastAPI app
app = FastAPI(
    title="OpenAI-Compatible API for n8n",
    description="Provides OpenAI API endpoints using local Ollama models",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "OpenAI-Compatible API Server for n8n",
        "version": "1.0.0",
        "endpoints": [
            "/v1/models",
            "/v1/chat/completions"
        ],
        "ollama_url": api.ollama_base_url if api else "not initialized"
    }

@app.get("/v1/models")
async def list_models() -> OpenAIModelsResponse:
    """List available models (OpenAI API compatible)"""
    try:
        available_models = api.get_available_models()
        
        models = []
        created_time = int(datetime.now().timestamp())
        
        # Add standard OpenAI model mappings
        openai_models = ["gpt-3.5-turbo", "gpt-4", "gpt-4o", "gpt-4o-mini", "gpt-4-turbo"]
        for model_name in openai_models:
            models.append(OpenAIModel(
                id=model_name,
                created=created_time,
                owned_by="ollama"
            ))
        
        # Add actual Ollama models
        for model_name in available_models:
            if model_name not in openai_models:
                models.append(OpenAIModel(
                    id=model_name,
                    created=created_time,
                    owned_by="ollama"
                ))
        
        return OpenAIModelsResponse(data=models)
        
    except Exception as e:
        logger.error(f"Error listing models: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/v1/chat/completions")
async def chat_completions(request: OpenAIChatRequest):
    """Chat completions endpoint (OpenAI API compatible)"""
    try:
        if request.stream:
            # Return streaming response
            return StreamingResponse(
                api.stream_chat_completion(request),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                }
            )
        else:
            # Return regular response
            response = await api.chat_completion(request)
            return JSONResponse(content=response.model_dump())
            
    except Exception as e:
        logger.error(f"Error in chat completions: {e}")
        error_response = OpenAIError(
            error=OpenAIErrorDetail(
                message=str(e),
                type="server_error",
                code="internal_error"
            )
        )
        return JSONResponse(
            content=error_response.model_dump(),
            status_code=500
        )

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check Ollama connection
        models = api.get_available_models()
        return {
            "status": "healthy",
            "ollama_connected": True,
            "available_models": len(models),
            "timestamp": datetime.now().isoformat(),
            "ollama_url": api.ollama_base_url
        }
    except Exception as e:
        return JSONResponse(
            content={
                "status": "unhealthy", 
                "ollama_connected": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
                "ollama_url": api.ollama_base_url if api else "not initialized"
            },
            status_code=503
        )

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="OpenAI-Compatible API Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8001, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    parser.add_argument("--ollama-url", default="http://localhost:11434", help="Ollama base URL")
    
    args = parser.parse_args()
    
    # Set Ollama URL as environment variable
    os.environ['OLLAMA_BASE_URL'] = args.ollama_url
    
    print(f"🚀 Starting OpenAI-Compatible API Server on {args.host}:{args.port}")
    print(f"📡 Ollama URL: {args.ollama_url}")
    print(f"📖 API Documentation: http://{args.host}:{args.port}/docs")
    print(f"🔗 n8n Base URL: http://{args.host}:{args.port}")
    
    uvicorn.run(
        "openai_api_server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info"
    )