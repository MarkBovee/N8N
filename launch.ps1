# Launch Script for GitHub Models + N8N
# This script starts N8N with GitHub Models integration

Write-Host "🚀 Starting N8N with GitHub Models Integration" -ForegroundColor Green
Write-Host "=" * 50 -ForegroundColor Gray
Write-Host ""

# Check prerequisites
Write-Host "🔍 Checking prerequisites..." -ForegroundColor Yellow

# Check if we're in the correct directory
$currentDir = Get-Location
if (-not (Test-Path "docker-compose.yml")) {
    Write-Host "❌ docker-compose.yml not found in current directory" -ForegroundColor Red
    Write-Host "💡 Please run this script from the N8N directory" -ForegroundColor Yellow
    exit 1
}

# Check for .env file with GitHub token
if (-not (Test-Path ".env")) {
    Write-Host "❌ .env file not found" -ForegroundColor Red
    Write-Host "💡 Please create .env file with your GITHUB_TOKEN" -ForegroundColor Yellow
    exit 1
}

Write-Host "📍 Working directory: $currentDir" -ForegroundColor Cyan
Write-Host ""

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

Write-Host ""

# Start N8N with Docker Compose
Write-Host "🐳 Starting N8N with GitHub Models..." -ForegroundColor Green

try {
    # Stop any existing containers first
    docker compose down 2>$null
    
    # Build and start containers
    Write-Host "📦 Building GitHub Models proxy..." -ForegroundColor Yellow
    docker compose build
    
    Write-Host "🚀 Starting containers..." -ForegroundColor Yellow
    docker compose up -d
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ N8N containers started successfully" -ForegroundColor Green
        
        # Wait for services to start
        Write-Host "⏳ Waiting for services to initialize..." -ForegroundColor Yellow
        Start-Sleep -Seconds 10
        
        # Test GitHub Models proxy
        try {
            $proxyHealth = Invoke-RestMethod -Uri "http://localhost:11434/health" -TimeoutSec 10
            Write-Host "✅ GitHub Models proxy is healthy" -ForegroundColor Green
        } catch {
            Write-Host "⚠️  GitHub Models proxy may still be starting..." -ForegroundColor Yellow
        }
        
        # Test N8N
        try {
            $n8nResponse = Invoke-WebRequest -Uri "http://localhost:5678" -TimeoutSec 10 -UseBasicParsing
            Write-Host "✅ N8N is accessible" -ForegroundColor Green
        } catch {
            Write-Host "⚠️  N8N may still be initializing..." -ForegroundColor Yellow
        }
    } else {
        Write-Host "❌ Failed to start containers" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "❌ Error starting services: $_" -ForegroundColor Red
    exit 1
}

# Display success information
Write-Host ""
Write-Host "🎉 N8N with GitHub Models Started Successfully!" -ForegroundColor Green
Write-Host "=" * 50 -ForegroundColor Gray
Write-Host ""

Write-Host "📋 Service URLs:" -ForegroundColor Yellow
Write-Host "   🌐 N8N Web Interface: http://localhost:5678" -ForegroundColor Cyan
Write-Host "   🤖 GitHub Models Proxy: http://localhost:11434" -ForegroundColor Cyan
Write-Host "   📖 API Documentation: http://localhost:11434/docs" -ForegroundColor Cyan
Write-Host "   🩺 Health Check: http://localhost:11434/health" -ForegroundColor Cyan
Write-Host ""

Write-Host "🔐 N8N Login Credentials:" -ForegroundColor Yellow
Write-Host "   Username: admin" -ForegroundColor Gray
Write-Host "   Password: secret" -ForegroundColor Gray
Write-Host ""

Write-Host "🔧 N8N LLM Configuration:" -ForegroundColor Yellow
Write-Host "   Base URL: http://localhost:11434/v1" -ForegroundColor Gray
Write-Host "   API Key: any-key-will-work" -ForegroundColor Gray
Write-Host "   Available Models: gpt-4o, gpt-4o-mini, and 50+ GitHub Models" -ForegroundColor Gray
Write-Host ""

Write-Host "🛠️  Management Commands:" -ForegroundColor Yellow
Write-Host "   Stop All: docker compose down" -ForegroundColor Gray
Write-Host "   View Logs: docker compose logs -f" -ForegroundColor Gray
Write-Host "   Rebuild: docker compose build --no-cache" -ForegroundColor Gray
Write-Host ""

# Open N8N in browser
Write-Host "🌍 Opening N8N in your browser..." -ForegroundColor Green
Start-Process "http://localhost:5678"

Write-Host "✅ Setup complete! N8N is now using GitHub Models instead of Ollama." -ForegroundColor Green