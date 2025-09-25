#!/usr/bin/env python3
"""
GitHub Models Proxy for N8N
Provides OpenAI-compatible API endpoints that proxy to GitHub Models
"""
import os
import requests
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

class OpenAIMessage(BaseModel):
    role: str
    content: str

class OpenAIChatRequest(BaseModel):
    model: str
    messages: List[OpenAIMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False

class OpenAIModel(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str = "github-models"

class OpenAIModelsResponse(BaseModel):
    object: str = "list"
    data: List[OpenAIModel]

GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_BASE_URL = "https://models.github.ai/inference"

app = FastAPI(title="GitHub Models Proxy")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def validate_model(model: str) -> str:
    model_mapping = {
        "gpt-4o": "openai/gpt-4.1",
        "gpt-4o-mini": "openai/gpt-4.1-mini", 
        "gpt-4": "openai/gpt-4.1",
        "gpt-3.5-turbo": "openai/gpt-4.1-mini"
    }
    return model_mapping.get(model, "openai/gpt-4.1-mini")

@app.get("/")
def root():
    return {"message": "GitHub Models Proxy"}

@app.get("/health")
def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/v1/models")
def list_models():
    """List available GitHub Models in OpenAI format"""
    try:
        response = requests.get(
            "https://models.github.ai/v1/models",
            headers={"Authorization": f"Bearer {GITHUB_TOKEN}"},
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    except Exception:
        # Fallback response if GitHub Models API is unavailable
        created_time = int(datetime.now().timestamp())
        models = [OpenAIModel(id=m, created=created_time) for m in ["gpt-4o", "gpt-4o-mini"]]
        return OpenAIModelsResponse(data=models).model_dump()

@app.post("/v1/chat/completions")
def chat_completions(request: OpenAIChatRequest):
    """Handle chat completions using GitHub Models"""
    try:
        validated_model = validate_model(request.model)
        
        github_request = {
            "model": validated_model,
            "messages": [{"role": msg.role, "content": msg.content} for msg in request.messages],
            "temperature": request.temperature,
            "stream": request.stream
        }
        
        if request.max_tokens:
            github_request["max_tokens"] = request.max_tokens
        
        response = requests.post(
            f"{GITHUB_BASE_URL}/chat/completions",
            json=github_request,
            headers={"Authorization": f"Bearer {GITHUB_TOKEN}"},
            timeout=120,
            stream=request.stream
        )
        response.raise_for_status()
        
        if request.stream:
            def generate():
                for line in response.iter_lines():
                    if line:
                        yield line.decode('utf-8') + '\n'
            return StreamingResponse(generate(), media_type="text/event-stream")
        else:
            return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    if not GITHUB_TOKEN:
        print("ERROR: GITHUB_TOKEN required")
        exit(1)
    
    print("Starting GitHub Models Proxy on port 11434")
    uvicorn.run("openai_api_server:app", host="0.0.0.0", port=11434, log_level="info")
