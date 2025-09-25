# Chat UI for N8N GitHub Models Proxy

A modern, Claude.ai-inspired chat interface for interacting with GitHub Models through the N8N proxy server.

## Features

- 🎨 **Modern Design**: Dark theme inspired by Claude.ai with smooth animations
- 💬 **Real-time Chat**: Interactive chat interface with typing indicators
- 📱 **Responsive**: Works great on desktop, tablet, and mobile devices
- ⌨️ **Keyboard Shortcuts**: 
  - `Ctrl/Cmd + K` - Focus input field
  - `Ctrl/Cmd + N` - Start new chat
  - `Enter` - Send message
  - `Shift + Enter` - New line in input
- 🔄 **Auto-resize Input**: Text area automatically adjusts to content
- 📋 **Copy Code**: Easy copy functionality for code blocks
- 🔍 **Suggested Prompts**: Quick-start prompts for common tasks

## Architecture

```
┌─────────────────┐    ┌────────────────┐    ┌─────────────────────┐
│   Chat UI       │    │  Nginx Proxy   │    │ GitHub Models Proxy │
│  (Port 8080)    │◄──►│                │◄──►│   (Port 11434)      │
│                 │    │                │    │                     │
└─────────────────┘    └────────────────┘    └─────────────────────┘
```

## API Integration

The chat UI communicates with the GitHub Models proxy through these endpoints:

- `GET /health` - Health check
- `POST /v1/chat/completions` - Chat completions (OpenAI-compatible)
- `GET /v1/models` - List available models

## Development

### File Structure

```
web/
├── index.html      # Main HTML structure
├── styles.css      # Modern CSS with dark theme
├── script.js       # Chat functionality and API calls
├── nginx.conf      # Nginx configuration for routing
└── README.md       # This file
```

### Local Development

To run the chat UI locally:

1. Start the containers: `docker-compose up -d`
2. Open browser to: `http://localhost:8080`
3. The API proxy runs on: `http://localhost:11434`

### Styling

The interface uses CSS custom properties for easy theming:

```css
:root {
    --bg-primary: #1a1a1a;      /* Main background */
    --bg-secondary: #2a2a2a;    /* Card backgrounds */
    --text-primary: #e5e5e5;    /* Primary text */
    --accent-primary: #f97316;   /* Orange accent */
}
```

## Usage

1. **Start a conversation**: Type a message or click a suggested prompt
2. **Format messages**: Supports basic markdown (bold, italic, code)
3. **Copy code**: Click the copy button on code blocks
4. **New chat**: Click "New Chat" or use `Ctrl/Cmd + N`
5. **Navigate**: Use keyboard shortcuts for efficiency

## Browser Support

- ✅ Chrome 70+
- ✅ Firefox 65+
- ✅ Safari 12+
- ✅ Edge 79+

## Security

- CORS headers configured for safe cross-origin requests
- Content Security Policy headers for XSS protection
- No authentication required (relies on GitHub token in proxy)

## Customization

To customize the interface:

1. **Colors**: Modify CSS custom properties in `styles.css`
2. **Layout**: Adjust the flexbox layout in the main container
3. **API**: Change the `apiBaseUrl` in `script.js` for different endpoints
4. **Prompts**: Update the suggested prompts in `index.html`