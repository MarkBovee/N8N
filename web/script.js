class ChatInterface {
    constructor() {
        // Use relative URL since we're proxying through nginx
        this.apiBaseUrl = window.location.origin;
        this.messages = [];
        this.isTyping = false;
        
        this.initializeElements();
        this.setupEventListeners();
        this.setupAutoResize();
    }

    initializeElements() {
        // Core elements
        this.welcomeScreen = document.getElementById('welcomeScreen');
        this.chatContainer = document.getElementById('chatContainer');
        this.messagesArea = document.getElementById('messagesArea');
        this.messageInput = document.getElementById('messageInput');
        this.sendBtn = document.getElementById('sendBtn');

        this.newChatBtn = document.getElementById('newChatBtn');
        this.loadingOverlay = document.getElementById('loadingOverlay');

        // Model selector
        this.modelSelector = document.getElementById('modelSelector');
        this.modelDropdown = document.getElementById('modelDropdown');
    }

    setupEventListeners() {
        // Send button
        this.sendBtn.addEventListener('click', () => this.sendMessage());

        // Enter key (with Shift+Enter for new line)
        this.messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        // Input changes
        this.messageInput.addEventListener('input', () => {
            this.updateSendButton();
        });

        // New chat button
        this.newChatBtn.addEventListener('click', () => this.startNewChat());

        // Model selector dropdown
        this.modelSelector.addEventListener('click', (e) => {
            e.stopPropagation();
            this.toggleModelDropdown();
        });

        // Close dropdown when clicking outside
        document.addEventListener('click', () => {
            this.modelDropdown.classList.remove('show');
        });

        // Focus input on load
        this.messageInput.focus();
    }

    setupAutoResize() {
        this.messageInput.addEventListener('input', () => {
            // Reset height to auto to get the correct scrollHeight
            this.messageInput.style.height = 'auto';
            // Set height to scrollHeight (content height)
            this.messageInput.style.height = Math.min(this.messageInput.scrollHeight, 120) + 'px';
        });
    }



    updateSendButton() {
        const hasContent = this.messageInput.value.trim().length > 0;
        this.sendBtn.disabled = !hasContent || this.isTyping;
    }

    async sendMessage() {
        const content = this.messageInput.value.trim();
        if (!content || this.isTyping) return;

        // Hide welcome screen and show chat
        this.showChatInterface();

        // Add user message
        this.addMessage('user', content);

        // Clear input
        this.messageInput.value = '';
        this.messageInput.style.height = 'auto';
        this.updateSendButton();

        // Show typing indicator
        this.showTypingIndicator();

        try {
            // Send to API
            const response = await this.callAPI(content);
            
            // Remove typing indicator
            this.hideTypingIndicator();
            
            // Add assistant response
            this.addMessage('assistant', response);
            
        } catch (error) {
            console.error('Error calling API:', error);
            this.hideTypingIndicator();
            this.addMessage('assistant', 'I apologize, but I encountered an error while processing your request. Please try again.');
        }

        // Scroll to bottom
        this.scrollToBottom();
    }

    async callAPI(message) {
        const requestData = {
            model: "gpt-4",
            messages: [
                {
                    role: "system",
                    content: "You are N8N AI, a helpful assistant powered by GitHub Models. You provide clear, concise, and helpful responses to user queries."
                },
                ...this.messages.map(msg => ({
                    role: msg.role,
                    content: msg.content
                })),
                {
                    role: "user",
                    content: message
                }
            ],
            temperature: 0.7,
            max_tokens: 2000,
            stream: false
        };

        const response = await fetch(`${this.apiBaseUrl}/v1/chat/completions`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestData)
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        
        if (data.choices && data.choices.length > 0) {
            return data.choices[0].message.content;
        } else {
            throw new Error('No response from API');
        }
    }

    showChatInterface() {
        this.welcomeScreen.style.display = 'none';
        this.chatContainer.style.display = 'flex';
    }

    addMessage(role, content) {
        const message = { role, content, timestamp: new Date() };
        this.messages.push(message);

        const messageElement = this.createMessageElement(message);
        this.messagesArea.appendChild(messageElement);
        
        this.scrollToBottom();
    }

    createMessageElement(message) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${message.role}`;

        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        
        if (message.role === 'user') {
            avatar.innerHTML = '<i class="fas fa-user"></i>';
        } else {
            avatar.innerHTML = '<i class="fas fa-sparkles"></i>';
        }

        const content = document.createElement('div');
        content.className = 'message-content';
        content.innerHTML = this.formatMessageContent(message.content);

        messageDiv.appendChild(avatar);
        messageDiv.appendChild(content);

        return messageDiv;
    }

    formatMessageContent(content) {
        // Basic markdown-like formatting
        let formatted = content
            // Code blocks
            .replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
            // Inline code
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            // Bold
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            // Italic
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            // Line breaks
            .replace(/\n/g, '<br>');

        return formatted;
    }

    showTypingIndicator() {
        this.isTyping = true;
        this.updateSendButton();

        const typingDiv = document.createElement('div');
        typingDiv.className = 'message assistant';
        typingDiv.id = 'typingIndicator';

        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.innerHTML = '<i class="fas fa-sparkles"></i>';

        const content = document.createElement('div');
        content.className = 'message-content';
        content.innerHTML = `
            <div class="typing-indicator">
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
            </div>
        `;

        typingDiv.appendChild(avatar);
        typingDiv.appendChild(content);
        this.messagesArea.appendChild(typingDiv);
        
        this.scrollToBottom();
    }

    hideTypingIndicator() {
        this.isTyping = false;
        this.updateSendButton();

        const typingIndicator = document.getElementById('typingIndicator');
        if (typingIndicator) {
            typingIndicator.remove();
        }
    }

    scrollToBottom() {
        setTimeout(() => {
            this.messagesArea.scrollTop = this.messagesArea.scrollHeight;
        }, 100);
    }

    startNewChat() {
        this.messages = [];
        this.messagesArea.innerHTML = '';
        this.welcomeScreen.style.display = 'flex';
        this.chatContainer.style.display = 'none';
        this.messageInput.focus();
    }

    toggleModelDropdown() {
        this.modelDropdown.classList.toggle('show');
    }

    // Utility method to check API health
    async checkAPIHealth() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/health`);
            return response.ok;
        } catch (error) {
            console.warn('API health check failed:', error);
            return false;
        }
    }
}

// Enhanced clipboard functionality
function copyToClipboard(text) {
    if (navigator.clipboard && window.isSecureContext) {
        return navigator.clipboard.writeText(text);
    } else {
        // Fallback for older browsers
        const textArea = document.createElement('textarea');
        textArea.value = text;
        textArea.style.position = 'fixed';
        textArea.style.left = '-999999px';
        textArea.style.top = '-999999px';
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        return new Promise((resolve, reject) => {
            document.execCommand('copy') ? resolve() : reject();
            textArea.remove();
        });
    }
}

// Add copy functionality to code blocks
function addCopyButtons() {
    const codeBlocks = document.querySelectorAll('pre code');
    codeBlocks.forEach(block => {
        const button = document.createElement('button');
        button.className = 'copy-btn';
        button.innerHTML = '<i class="fas fa-copy"></i>';
        button.title = 'Copy to clipboard';
        
        button.addEventListener('click', async () => {
            try {
                await copyToClipboard(block.textContent);
                button.innerHTML = '<i class="fas fa-check"></i>';
                setTimeout(() => {
                    button.innerHTML = '<i class="fas fa-copy"></i>';
                }, 2000);
            } catch (err) {
                console.error('Failed to copy text: ', err);
            }
        });

        const pre = block.parentElement;
        if (pre.tagName === 'PRE') {
            pre.style.position = 'relative';
            pre.appendChild(button);
        }
    });
}

// Theme switching functionality (for future enhancement)
function toggleTheme() {
    document.body.classList.toggle('light-theme');
    localStorage.setItem('theme', document.body.classList.contains('light-theme') ? 'light' : 'dark');
}

// Load saved theme preference
function loadTheme() {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'light') {
        document.body.classList.add('light-theme');
    }
}

// Initialize the chat interface when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    loadTheme();
    window.chatInterface = new ChatInterface();
    
    // Check API health on startup
    window.chatInterface.checkAPIHealth().then(isHealthy => {
        if (!isHealthy) {
            console.warn('API server might not be running on http://localhost:11434');
        }
    });
});

// Add keyboard shortcuts
document.addEventListener('keydown', (e) => {
    // Ctrl/Cmd + K to focus input
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        window.chatInterface.messageInput.focus();
    }
    
    // Ctrl/Cmd + N for new chat
    if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
        e.preventDefault();
        window.chatInterface.startNewChat();
    }
});

// Handle online/offline status
window.addEventListener('online', () => {
    console.log('Connection restored');
});

window.addEventListener('offline', () => {
    console.log('Connection lost');
});