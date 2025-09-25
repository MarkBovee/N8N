# Consolidated Launch Script for OpenAI Wrapper + N8N
# This script starts both the OpenAI-compatible API server and N8N

param(
    [string]$ApiHost = "127.0.0.1",
    [int]$ApiPort = 8001,
    [string]$OllamaUrl = "http://localhost:11434",
    [switch]$Reload
)

Write-Host "🚀 Starting OpenAI Wrapper + N8N Environment" -ForegroundColor Green
Write-Host "=" * 50 -ForegroundColor Gray
Write-Host ""

# Step 1: Check prerequisites
Write-Host "🔍 Checking prerequisites..." -ForegroundColor Yellow

# Check if we're in the correct directory
$currentDir = Get-Location
if (-not (Test-Path "openai_api_server.py")) {
    Write-Host "❌ openai_api_server.py not found in current directory" -ForegroundColor Red
    Write-Host "💡 Please run this script from the N8N directory" -ForegroundColor Yellow
    Write-Host "   Current directory: $currentDir" -ForegroundColor Gray
    exit 1
}

if (-not (Test-Path "docker-compose.yml")) {
    Write-Host "❌ docker-compose.yml not found in current directory" -ForegroundColor Red
    Write-Host "💡 Please ensure docker-compose.yml is in the same directory" -ForegroundColor Yellow
    exit 1
}

Write-Host "📍 Working directory: $currentDir" -ForegroundColor Cyan
Write-Host ""

# Check Python
Write-Host "🐍 Checking Python installation..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✅ Python found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Python not found or not in PATH" -ForegroundColor Red
    Write-Host "💡 Please install Python and ensure it's in your PATH" -ForegroundColor Yellow
    exit 1
}

# Check Docker
Write-Host "🐳 Checking Docker installation..." -ForegroundColor Yellow
try {
    $dockerVersion = docker --version 2>&1
    Write-Host "✅ Docker found: $dockerVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Docker not found or not running" -ForegroundColor Red
    Write-Host "💡 Please install Docker and ensure it's running" -ForegroundColor Yellow
    exit 1
}

# Check required Python packages
Write-Host "📦 Checking required Python packages..." -ForegroundColor Yellow
try {
    python -c "import fastapi, uvicorn, pydantic, requests" 2>$null
    Write-Host "✅ Required packages found" -ForegroundColor Green
} catch {
    Write-Host "❌ Required packages missing" -ForegroundColor Red
    Write-Host "💡 Installing packages..." -ForegroundColor Yellow
    
    if (Test-Path "requirements.txt") {
        pip install -r requirements.txt
    } else {
        pip install fastapi uvicorn pydantic requests
    }
    
    # Test again
    try {
        python -c "import fastapi, uvicorn, pydantic, requests" 2>$null
        Write-Host "✅ Packages installed successfully" -ForegroundColor Green
    } catch {
        Write-Host "❌ Failed to install required packages" -ForegroundColor Red
        exit 1
    }
}

# Check if Ollama is running
Write-Host "🤖 Checking if Ollama is running..." -ForegroundColor Yellow
try {
    $ollamaResponse = Invoke-RestMethod -Uri "$OllamaUrl/api/tags" -TimeoutSec 5
    Write-Host "✅ Ollama is running and accessible" -ForegroundColor Green
    
    $modelCount = $ollamaResponse.models.Count
    Write-Host "📋 Available models: $modelCount" -ForegroundColor Cyan
    
    if ($modelCount -gt 0) {
        Write-Host "🤖 Sample models:" -ForegroundColor Cyan
        foreach ($model in $ollamaResponse.models[0..2]) {
            Write-Host "   - $($model.name)" -ForegroundColor Gray
        }
        if ($modelCount -gt 3) {
            Write-Host "   ... and $($modelCount - 3) more" -ForegroundColor Gray
        }
    } else {
        Write-Host "⚠️  No models found. You may want to pull some models:" -ForegroundColor Yellow
        Write-Host "   ollama pull llama3.2:latest" -ForegroundColor Gray
        Write-Host "   ollama pull qwen2.5:7b" -ForegroundColor Gray
    }
} catch {
    Write-Host "❌ Ollama is not running or not accessible at $OllamaUrl" -ForegroundColor Red
    Write-Host "💡 Please start Ollama first:" -ForegroundColor Yellow
    Write-Host "   ollama serve" -ForegroundColor Gray
    Write-Host ""
    $continue = Read-Host "Continue anyway? (y/N)"
    if ($continue -ne "y" -and $continue -ne "Y") {
        exit 1
    }
}

Write-Host ""

# Step 2: Start OpenAI API Wrapper
Write-Host "🌐 Starting OpenAI-Compatible API Server..." -ForegroundColor Green
Write-Host "📡 API Host: $ApiHost" -ForegroundColor Cyan
Write-Host "🔌 API Port: $ApiPort" -ForegroundColor Cyan
Write-Host "🤖 Ollama URL: $OllamaUrl" -ForegroundColor Cyan
Write-Host ""

# Build command arguments for API server
$apiArgs = @("openai_api_server.py", "--host", $ApiHost, "--port", $ApiPort, "--ollama-url", $OllamaUrl)
if ($Reload) {
    $apiArgs += "--reload"
}

# Start the API server in the background
try {
    $apiJob = Start-Job -ScriptBlock {
        param($arguments)
        Set-Location $using:currentDir
        & python @arguments
    } -ArgumentList (,$apiArgs)
    
    Write-Host "✅ API server started (Job ID: $($apiJob.Id))" -ForegroundColor Green
    
    # Wait a moment for server to start
    Start-Sleep -Seconds 3
    
    # Test API server
    Write-Host "🔍 Testing API server..." -ForegroundColor Yellow
    try {
        $healthCheck = Invoke-RestMethod -Uri "http://$ApiHost`:$ApiPort/health" -TimeoutSec 5
        if ($healthCheck.status -eq "healthy") {
            Write-Host "✅ API server is healthy and ready" -ForegroundColor Green
        } else {
            Write-Host "⚠️  API server started but may have issues" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "⚠️  API server started but health check failed (may still be starting)" -ForegroundColor Yellow
    }
    
} catch {
    Write-Host "❌ Failed to start API server: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Step 3: Start N8N with Docker Compose
Write-Host "🐳 Starting N8N with Docker Compose..." -ForegroundColor Green

try {
    # Stop any existing containers first (in case they're running)
    docker compose down 2>$null
    
    # Start N8N containers
    docker compose up -d
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ N8N containers started successfully" -ForegroundColor Green
        
        # Wait a moment for N8N to start
        Write-Host "⏳ Waiting for N8N to initialize..." -ForegroundColor Yellow
        Start-Sleep -Seconds 5
        
        # Test N8N
        try {
            $n8nResponse = Invoke-WebRequest -Uri "http://localhost:5678" -TimeoutSec 10 -UseBasicParsing
            Write-Host "✅ N8N is accessible" -ForegroundColor Green
        } catch {
            Write-Host "⚠️  N8N containers started but may still be initializing" -ForegroundColor Yellow
        }
    } else {
        Write-Host "❌ Failed to start N8N containers" -ForegroundColor Red
        Write-Host "💡 Stopping API server..." -ForegroundColor Yellow
        Stop-Job -Id $apiJob.Id 2>$null
        Remove-Job -Id $apiJob.Id 2>$null
        exit 1
    }
} catch {
    Write-Host "❌ Error starting N8N: $_" -ForegroundColor Red
    Write-Host "💡 Stopping API server..." -ForegroundColor Yellow
    Stop-Job -Id $apiJob.Id 2>$null
    Remove-Job -Id $apiJob.Id 2>$null
    exit 1
}

# Step 4: Display success information
Write-Host ""
Write-Host "🎉 Environment Started Successfully!" -ForegroundColor Green
Write-Host "=" * 50 -ForegroundColor Gray
Write-Host ""

Write-Host "📋 Service URLs:" -ForegroundColor Yellow
Write-Host "   🌐 N8N Web Interface: http://localhost:5678" -ForegroundColor Cyan
Write-Host "   🤖 OpenAI API Server: http://$ApiHost`:$ApiPort" -ForegroundColor Cyan
Write-Host "   📖 API Documentation: http://$ApiHost`:$ApiPort/docs" -ForegroundColor Cyan
Write-Host "   🩺 API Health Check: http://$ApiHost`:$ApiPort/health" -ForegroundColor Cyan
Write-Host ""

Write-Host "🔐 N8N Login Credentials:" -ForegroundColor Yellow
Write-Host "   Username: admin" -ForegroundColor Gray
Write-Host "   Password: secret" -ForegroundColor Gray
Write-Host ""

Write-Host "🔧 N8N OpenAI Configuration:" -ForegroundColor Yellow
Write-Host "   Base URL: http://$ApiHost`:$ApiPort" -ForegroundColor Gray
Write-Host "   API Key: any-key-will-work" -ForegroundColor Gray
Write-Host ""

Write-Host "🛠️  Management Commands:" -ForegroundColor Yellow
Write-Host "   Stop API Server: Stop-Job -Id $($apiJob.Id); Remove-Job -Id $($apiJob.Id)" -ForegroundColor Gray
Write-Host "   Stop N8N: docker compose down" -ForegroundColor Gray
Write-Host "   View API Logs: Receive-Job -Id $($apiJob.Id) -Keep" -ForegroundColor Gray
Write-Host "   View N8N Logs: docker compose logs -f n8n" -ForegroundColor Gray
Write-Host ""

# Open N8N in browser
Write-Host "🌍 Opening N8N in your browser..." -ForegroundColor Green
Start-Process "http://localhost:5678"

# Return summary information
return @{
    Status = "Success"
    ApiJobId = $apiJob.Id
    N8NUrl = "http://localhost:5678"
    ApiUrl = "http://$ApiHost`:$ApiPort"
    ApiDocs = "http://$ApiHost`:$ApiPort/docs"
    ApiHealth = "http://$ApiHost`:$ApiPort/health"
}