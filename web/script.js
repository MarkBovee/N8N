class ChatInterface {
    constructor() {
        // Use relative URL since we're proxying through nginx
        this.apiBaseUrl = window.location.origin;
        this.messages = [];
        this.isTyping = false;
        this.models = [];
        this.selectedModel = null;
        
        this.initializeElements();
        this.setupEventListeners();
        this.setupAutoResize();
        // Wait a bit for DOM to be fully ready
        setTimeout(() => this.loadAvailableModels(), 100);
    }

    initializeElements() {
        // Core elements
        this.welcomeScreen = document.getElementById('welcomeScreen');
        this.chatContainer = document.getElementById('chatContainer');
        this.messagesArea = document.getElementById('messagesArea');
        this.messageInput = document.getElementById('messageInput');
        this.sendBtn = document.getElementById('sendBtn');

        this.newChatBtn = document.getElementById('newChatBtn');

        // Model selector
        this.modelSelector = document.getElementById('modelSelector');
        this.modelDropdown = document.getElementById('modelDropdown');

        // Chat model selector
        this.modelSelector2 = document.getElementById('modelSelector2');
        this.modelDropdown2 = document.getElementById('modelDropdown2');
        this.currentModel2 = document.getElementById('currentModel2');

        // Inner elements for click events
        this.modelSelectorInner = document.getElementById('modelSelectorInner');
        this.modelSelectorInner2 = document.getElementById('modelSelectorInner2');

        // Chat-area input & send button
        this.messageInput2 = document.getElementById('messageInput2');
        this.sendBtn2 = document.getElementById('sendBtn2');
    }

    setupEventListeners() {
        // Send button
        this.sendBtn.addEventListener('click', () => this.sendMessage());

        // Enter key (with Shift+Enter for new line) for primary input
        this.messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        // Enter key for chat-area input when visible
        if (this.messageInput2) {
            this.messageInput2.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage(true);
                }
            });
        }

        // Input changes
        this.messageInput.addEventListener('input', () => {
            this.updateSendButton();
        });
        if (this.messageInput2) {
            this.messageInput2.addEventListener('input', () => {
                this.updateSendButton();
            });
        }

    // New chat button
    this.newChatBtn.addEventListener('click', () => this.startNewChat());

        // Model selector dropdown
        this.modelSelectorInner.addEventListener('click', (e) => {
            e.stopPropagation();
            console.log('Model selector clicked');
            console.log('Models available:', this.models.length);
            console.log('Dropdown element:', this.modelDropdown);
            this.toggleModelDropdown();
        });

        // Chat model selector dropdown
        this.modelSelectorInner2.addEventListener('click', (e) => {
            e.stopPropagation();
            this.toggleModelDropdown2();
        });

        // Close dropdown when clicking outside
        document.addEventListener('click', () => {
            this.modelDropdown.classList.add('hidden');
            if (this.modelDropdown2) this.modelDropdown2.classList.add('hidden');
        });

        // Focus input on load
        this.messageInput.focus();

        // wire chat-area send button
        if (this.sendBtn2) {
            this.sendBtn2.addEventListener('click', () => this.sendMessage(true));
        }
    }

    setupAutoResize() {
        this.messageInput.addEventListener('input', () => {
            // Reset height to auto to get the correct scrollHeight
            this.messageInput.style.height = 'auto';
            // Set height to scrollHeight (content height)
            this.messageInput.style.height = Math.min(this.messageInput.scrollHeight, 120) + 'px';
        });
    }

    async loadAvailableModels() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/v1/models`);
            if (response.ok) {
                const data = await response.json();
                this.models = data.data || data || [];
                
                // Filter for chat models only (exclude embeddings)
                this.models = this.models.filter(model => 
                    !model.id.includes('embedding') && 
                    model.supported_output_modalities?.includes('text')
                );
                
                // If we got models, populate dropdown and set default
                if (this.models.length > 0) {
                    this.populateModelDropdown();
                    if (this.modelDropdown2) this.populateModelDropdown2();
                    
                    // Set default model to a popular one
                    const defaultModel = this.models.find(m => m.id === 'openai/gpt-4o') || 
                                       this.models.find(m => m.id === 'openai/gpt-4.1') ||
                                       this.models[0];
                    if (defaultModel) {
                        this.selectedModel = defaultModel.id;
                        this.updateSelectedModel();
                    }
                } else {
                    this.setFallbackModels();
                }
            } else {
                this.setFallbackModels();
            }
        } catch (error) {
            console.error('Error loading models:', error);
            this.setFallbackModels();
        }
    }

    setFallbackModels() {
        this.models = [
            { id: 'openai/gpt-4o', name: 'GPT-4o', description: 'Smart, efficient model for everyday use' },
            { id: 'openai/gpt-4o-mini', name: 'GPT-4o Mini', description: 'Fast, lightweight model for simple tasks' }
        ];
        this.selectedModel = this.models[0].id;
        this.populateModelDropdown();
        if (this.modelDropdown2) this.populateModelDropdown2();
        this.updateSelectedModel();
    }
    


    populateModelDropdown() {
        if (!this.modelDropdown) {
            console.error('modelDropdown element not found!');
            return;
        }
        
        console.log('Starting to populate dropdown with', this.models.length, 'models');
        this.modelDropdown.innerHTML = '';
        
        // Map popular models with proper names and descriptions
        const modelMapping = {
            'openai/gpt-4.1': { friendlyName: 'GPT-4.1', desc: 'Powerful, large model for complex challenges' },
            'openai/gpt-4.1-mini': { friendlyName: 'GPT-4.1 Mini', desc: 'Efficient version of GPT-4.1' },
            'openai/gpt-4o': { friendlyName: 'GPT-4o', desc: 'Smart, multimodal model for everyday use' },
            'openai/gpt-4o-mini': { friendlyName: 'GPT-4o Mini', desc: 'Fast, lightweight model for simple tasks' },
            'openai/gpt-5': { friendlyName: 'GPT-5', desc: 'Advanced reasoning and logic capabilities' },
            'openai/gpt-5-chat': { friendlyName: 'GPT-5 Chat', desc: 'Optimized for conversational interactions' },
            'openai/gpt-5-mini': { friendlyName: 'GPT-5 Mini', desc: 'Lightweight version of GPT-5' },
            'openai/o1': { friendlyName: 'o1', desc: 'Advanced reasoning for complex problems' },
            'openai/o1-mini': { friendlyName: 'o1-mini', desc: 'Compact reasoning model' },
            'openai/o1-preview': { friendlyName: 'o1-preview', desc: 'Preview of advanced reasoning capabilities' },
            'openai/o3': { friendlyName: 'o3', desc: 'Latest reasoning model with improved safety' },
            'openai/o3-mini': { friendlyName: 'o3-mini', desc: 'Efficient reasoning model' },
            'microsoft/phi-4': { friendlyName: 'Phi-4', desc: 'Microsoft\'s capable model for low latency' }
        };
        
        // Show popular models first with friendly names
        const popularModels = this.models.filter(m => modelMapping[m.id]);
        console.log('Popular models found:', popularModels.length, popularModels.map(m => m.id));
        
        popularModels.forEach(model => {
            const mapping = modelMapping[model.id];
            const option = document.createElement('div');
            option.className = 'flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-claude-secondary transition-colors duration-200';
            option.dataset.modelId = model.id;
            
            option.innerHTML = `
                <div class="w-4 h-4 bg-claude-accent rounded-full flex-shrink-0"></div>
                <div class="flex-1">
                    <div class="text-claude-text font-medium text-sm">${mapping.friendlyName}</div>
                    <div class="text-claude-text-muted text-xs mt-0.5">${mapping.desc}</div>
                </div>
            `;
            
            option.addEventListener('click', () => {
                console.log('Popular model clicked:', model.id);
                this.selectedModel = model.id;
                this.updateSelectedModel();
                this.toggleModelDropdown();
                console.log('Model updated to:', this.selectedModel);
            });
            
            this.modelDropdown.appendChild(option);
        });
        
        console.log('Added', popularModels.length, 'popular models to dropdown');
        
        // If we have models but none are popular, show the first few anyway
        if (popularModels.length === 0 && this.models.length > 0) {
            console.log('No popular models found, showing fallback models');
            const fallbackModels = this.models.slice(0, 5);
            fallbackModels.forEach(model => {
                const option = document.createElement('div');
                option.className = 'flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-claude-secondary transition-colors duration-200';
                option.dataset.modelId = model.id;
                
                option.innerHTML = `
                    <div class="w-4 h-4 bg-gray-400 rounded-full flex-shrink-0"></div>
                    <div class="flex-1">
                        <div class="text-claude-text font-medium text-sm">${model.name || model.id}</div>
                        <div class="text-claude-text-muted text-xs mt-0.5">${model.id}</div>
                    </div>
                `;
                
                option.addEventListener('click', () => {
                    this.selectedModel = model.id;
                    this.updateSelectedModel();
                    this.toggleModelDropdown();
                });
                
                this.modelDropdown.appendChild(option);
            });
        }
        
        // Add "More models" option if we have more models than shown
        if (this.models.length > popularModels.length) {
            const moreOption = document.createElement('div');
            moreOption.className = 'flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-claude-secondary transition-colors duration-200 border-t border-claude-border-light mt-2 pt-4';
            moreOption.innerHTML = `
                <div class="text-claude-text font-medium text-sm">More models (${this.models.length} total)</div>
                <i class="fas fa-chevron-right text-claude-text-secondary text-xs"></i>
            `;
            moreOption.addEventListener('click', () => {
                this.showAllModels();
            });
            this.modelDropdown.appendChild(moreOption);
        }
    }
    
    populateModelDropdown2() {
        if (!this.modelDropdown2) return;
        
        this.modelDropdown2.innerHTML = '';
        
        // Map popular models with proper names and descriptions
        const modelMapping = {
            'openai/gpt-4.1': { friendlyName: 'GPT-4.1', desc: 'Powerful, large model for complex challenges' },
            'openai/gpt-4.1-mini': { friendlyName: 'GPT-4.1 Mini', desc: 'Efficient version of GPT-4.1' },
            'openai/gpt-4o': { friendlyName: 'GPT-4o', desc: 'Smart, multimodal model for everyday use' },
            'openai/gpt-4o-mini': { friendlyName: 'GPT-4o Mini', desc: 'Fast, lightweight model for simple tasks' },
            'openai/gpt-5': { friendlyName: 'GPT-5', desc: 'Advanced reasoning and logic capabilities' },
            'openai/gpt-5-chat': { friendlyName: 'GPT-5 Chat', desc: 'Optimized for conversational interactions' },
            'openai/gpt-5-mini': { friendlyName: 'GPT-5 Mini', desc: 'Lightweight version of GPT-5' },
            'openai/o1': { friendlyName: 'o1', desc: 'Advanced reasoning for complex problems' },
            'openai/o1-mini': { friendlyName: 'o1-mini', desc: 'Compact reasoning model' },
            'openai/o1-preview': { friendlyName: 'o1-preview', desc: 'Preview of advanced reasoning capabilities' },
            'openai/o3': { friendlyName: 'o3', desc: 'Latest reasoning model with improved safety' },
            'openai/o3-mini': { friendlyName: 'o3-mini', desc: 'Efficient reasoning model' },
            'microsoft/phi-4': { friendlyName: 'Phi-4', desc: 'Microsoft\'s capable model for low latency' }
        };
        
        // Show popular models first with friendly names
        const popularModels = this.models.filter(m => modelMapping[m.id]);
        
        popularModels.forEach(model => {
            const mapping = modelMapping[model.id];
            const option = document.createElement('div');
            option.className = 'flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-claude-secondary transition-colors duration-200';
            option.dataset.modelId = model.id;
            
            option.innerHTML = `
                <div class="w-4 h-4 bg-claude-accent rounded-full flex-shrink-0"></div>
                <div class="flex-1">
                    <div class="text-claude-text font-medium text-sm">${mapping.friendlyName}</div>
                    <div class="text-claude-text-muted text-xs mt-0.5">${mapping.desc}</div>
                </div>
            `;
            
            option.addEventListener('click', () => {
                this.selectedModel = model.id;
                this.updateSelectedModel();
                this.toggleModelDropdown2();
            });
            
            this.modelDropdown2.appendChild(option);
        });
        
        // If we have models but none are popular, show the first few anyway
        if (popularModels.length === 0 && this.models.length > 0) {
            const fallbackModels = this.models.slice(0, 5);
            fallbackModels.forEach(model => {
                const option = document.createElement('div');
                option.className = 'flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-claude-secondary transition-colors duration-200';
                option.dataset.modelId = model.id;
                
                option.innerHTML = `
                    <div class="w-4 h-4 bg-gray-400 rounded-full flex-shrink-0"></div>
                    <div class="flex-1">
                        <div class="text-claude-text font-medium text-sm">${model.name || model.id}</div>
                        <div class="text-claude-text-muted text-xs mt-0.5">${model.id}</div>
                    </div>
                `;
                
                option.addEventListener('click', () => {
                    this.selectedModel = model.id;
                    this.updateSelectedModel();
                    this.toggleModelDropdown2();
                });
                
                this.modelDropdown2.appendChild(option);
            });
        }
        
        // Add "More models" option if we have more models than shown
        if (this.models.length > popularModels.length) {
            const moreOption = document.createElement('div');
            moreOption.className = 'flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-claude-secondary transition-colors duration-200 border-t border-claude-border-light mt-2 pt-4';
            moreOption.innerHTML = `
                <div class="text-claude-text font-medium text-sm">More models (${this.models.length} total)</div>
                <i class="fas fa-chevron-right text-claude-text-secondary text-xs"></i>
            `;
            moreOption.addEventListener('click', () => {
                this.showAllModels2();
            });
            this.modelDropdown2.appendChild(moreOption);
        }
    }
    
    showAllModels2() {
        // Clear dropdown and show all models
        this.modelDropdown2.innerHTML = '';
        
        this.models.forEach(model => {
            const option = document.createElement('div');
            option.className = 'flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-claude-secondary transition-colors duration-200';
            option.dataset.modelId = model.id;
            
            option.innerHTML = `
                <div class="w-4 h-4 bg-claude-accent rounded-full flex-shrink-0"></div>
                <div class="flex-1">
                    <div class="text-claude-text font-medium text-sm">${model.name || model.id}</div>
                    <div class="text-claude-text-muted text-xs mt-0.5 line-clamp-2">${(model.summary || model.description || '').substring(0, 100)}${(model.summary || model.description || '').length > 100 ? '...' : ''}</div>
                </div>
            `;
            
            option.addEventListener('click', () => {
                this.selectedModel = model.id;
                this.updateSelectedModel();
                this.toggleModelDropdown2();
            });
            
            this.modelDropdown2.appendChild(option);
        });
        
        // Add back button
        const backOption = document.createElement('div');
        backOption.className = 'flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-claude-secondary transition-colors duration-200 border-b border-claude-border-light mb-2 pb-4';
        backOption.innerHTML = `
            <i class="fas fa-arrow-left text-claude-text-secondary text-sm"></i>
            <div class="text-claude-text font-medium text-sm">Back to popular models</div>
        `;
        backOption.addEventListener('click', () => {
            this.populateModelDropdown2();
        });
        this.modelDropdown2.insertBefore(backOption, this.modelDropdown2.firstChild);
    }
    
    showAllModels() {
        // Clear dropdown and show all models
        this.modelDropdown.innerHTML = '';
        
        this.models.forEach(model => {
            const option = document.createElement('div');
            option.className = 'flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-claude-secondary transition-colors duration-200';
            option.dataset.modelId = model.id;
            
            option.innerHTML = `
                <div class="w-4 h-4 bg-claude-accent rounded-full flex-shrink-0"></div>
                <div class="flex-1">
                    <div class="text-claude-text font-medium text-sm">${model.name || model.id}</div>
                    <div class="text-claude-text-muted text-xs mt-0.5 line-clamp-2">${(model.summary || model.description || '').substring(0, 100)}${(model.summary || model.description || '').length > 100 ? '...' : ''}</div>
                </div>
            `;
            
            option.addEventListener('click', () => {
                this.selectedModel = model.id;
                this.updateSelectedModel();
                this.toggleModelDropdown();
            });
            
            this.modelDropdown.appendChild(option);
        });
        
        // Add back button
        const backOption = document.createElement('div');
        backOption.className = 'flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-claude-secondary transition-colors duration-200 border-b border-claude-border-light mb-2 pb-4';
        backOption.innerHTML = `
            <i class="fas fa-arrow-left text-claude-text-secondary text-sm"></i>
            <div class="text-claude-text font-medium text-sm">Back to popular models</div>
        `;
        backOption.addEventListener('click', () => {
            this.populateModelDropdown();
        });
        this.modelDropdown.insertBefore(backOption, this.modelDropdown.firstChild);
    }

    updateSelectedModel() {
        const modelMapping = {
            'openai/gpt-4.1': 'GPT-4.1',
            'openai/gpt-4.1-mini': 'GPT-4.1 Mini',
            'openai/gpt-4o': 'GPT-4o',
            'openai/gpt-4o-mini': 'GPT-4o Mini',
            'openai/gpt-5': 'GPT-5',
            'openai/gpt-5-chat': 'GPT-5 Chat',
            'openai/gpt-5-mini': 'GPT-5 Mini',
            'openai/o1': 'o1',
            'openai/o1-mini': 'o1-mini',
            'openai/o3': 'o3',
            'openai/o3-mini': 'o3-mini',
            'microsoft/phi-4': 'Phi-4'
        };
        
        const selectedModelData = this.models.find(m => m.id === this.selectedModel);
        if (selectedModelData) {
            const displayName = modelMapping[this.selectedModel] || selectedModelData.name || this.selectedModel;
            document.getElementById('currentModel').textContent = displayName;
            if (this.currentModel2) {
                this.currentModel2.textContent = displayName;
            }
        }
        
        // Update selected state in dropdown
        const options = this.modelDropdown.querySelectorAll('[data-model-id]');
        options.forEach(option => {
            if (option.dataset.modelId === this.selectedModel) {
                option.classList.add('bg-claude-secondary');
                option.querySelector('.text-claude-text')?.classList.add('text-claude-accent');
            } else {
                option.classList.remove('bg-claude-secondary');
                option.querySelector('.text-claude-accent')?.classList.remove('text-claude-accent');
                option.querySelector('.text-claude-text')?.classList.add('text-claude-text');
            }
        });
    }

    toggleModelDropdown() {
        const wasHidden = this.modelDropdown.classList.contains('hidden');
        
        // If dropdown is empty but we have models, populate it
        if (this.modelDropdown.children.length === 0 && this.models.length > 0) {
            console.log('Dropdown is empty, repopulating with', this.models.length, 'models');
            this.populateModelDropdown();
        }
        
        // Decide whether to open up or down depending on space in viewport
        try {
            const rect = this.modelSelector.getBoundingClientRect();
            const spaceBelow = window.innerHeight - rect.bottom;
            const spaceAbove = rect.top;
            const preferredHeight = Math.min(window.innerHeight * 0.48, this.modelDropdown.scrollHeight || 400);
            if (spaceBelow < preferredHeight && spaceAbove > spaceBelow) {
                this.modelDropdown.classList.remove('drop-down');
                this.modelDropdown.classList.add('drop-up');
            } else {
                this.modelDropdown.classList.remove('drop-up');
                this.modelDropdown.classList.add('drop-down');
            }
            // set max height to fit in available space with margin
            const maxH = Math.max(160, Math.floor(Math.max(spaceBelow, spaceAbove) - 48));
            this.modelDropdown.style.maxHeight = `${maxH}px`;
        } catch (err) {
            // ignore and let CSS defaults apply
            console.warn('Could not compute dropdown direction', err);
        }

        this.modelDropdown.classList.toggle('hidden');
        const isNowHidden = this.modelDropdown.classList.contains('hidden');
        console.log('Dropdown toggled:', wasHidden ? 'shown' : 'hidden', '-> now', isNowHidden ? 'hidden' : 'shown');
        console.log('Dropdown children count:', this.modelDropdown.children.length);
    }

    toggleModelDropdown2() {
        // If dropdown is empty but we have models, populate it
        if (this.modelDropdown2.children.length === 0 && this.models.length > 0) {
            this.populateModelDropdown2();
        }
        
        try {
            const rect = this.modelSelector2.getBoundingClientRect();
            const spaceBelow = window.innerHeight - rect.bottom;
            const spaceAbove = rect.top;
            const preferredHeight = Math.min(window.innerHeight * 0.48, this.modelDropdown2.scrollHeight || 400);
            if (spaceBelow < preferredHeight && spaceAbove > spaceBelow) {
                this.modelDropdown2.classList.remove('drop-down');
                this.modelDropdown2.classList.add('drop-up');
            } else {
                this.modelDropdown2.classList.remove('drop-up');
                this.modelDropdown2.classList.add('drop-down');
            }
            const maxH = Math.max(160, Math.floor(Math.max(spaceBelow, spaceAbove) - 48));
            this.modelDropdown2.style.maxHeight = `${maxH}px`;
        } catch (err) {
            console.warn('Could not compute dropdown2 direction', err);
        }

        this.modelDropdown2.classList.toggle('hidden');
    }

    updateSendButton() {
        // Prefer the input that is actually visible in the DOM (handles CSS/display vs inline style)
        const isElementVisible = (el) => {
            if (!el) return false;
            // offsetParent is null for display:none; getClientRects covers more cases
            return !!(el.offsetParent || el.getClientRects().length);
        };
        // If the user is currently focused in one of the inputs, prefer that (covers edge-cases)
        const focused = document.activeElement;
        const activeInput = (focused === this.messageInput2 || focused === this.messageInput) ? focused : (isElementVisible(this.messageInput2) ? this.messageInput2 : this.messageInput);
        const hasContent = activeInput && activeInput.value && activeInput.value.trim().length > 0;

        console.debug('updateSendButton', { activeInputId: activeInput?.id, valueLen: activeInput?.value?.length || 0, isTyping: this.isTyping });
        // Update both send buttons if present
        this.sendBtn.disabled = !hasContent || this.isTyping;
        this.sendBtn.setAttribute('aria-disabled', this.sendBtn.disabled ? 'true' : 'false');
        if (this.sendBtn2) {
            this.sendBtn2.disabled = !hasContent || this.isTyping;
            this.sendBtn2.setAttribute('aria-disabled', this.sendBtn2.disabled ? 'true' : 'false');
        }
    }

    async sendMessage(useChatInput = false) {
        // Determine which input to use. Prefer whichever input is actually visible to the user
        const isElementVisible = (el) => {
            if (!el) return false;
            return !!(el.offsetParent || el.getClientRects().length);
        };

        const input = (useChatInput ? (this.messageInput2 || this.messageInput) : (isElementVisible(this.messageInput2) ? this.messageInput2 : this.messageInput));
    const content = input ? input.value.trim() : '';
    console.debug('sendMessage start', { useChatInput, chosenInputId: input?.id, visibleChat: this.chatContainer && this.chatContainer.style.display !== 'none', contentSnippet: content.slice(0,120), isTyping: this.isTyping });
        if (!content || this.isTyping) return;

        // Hide welcome screen and show chat
        this.showChatInterface();

        // Add user message
        this.addMessage('user', content);

        // Clear input
        if (input) {
            input.value = '';
            input.style.height = 'auto';
        }
        this.updateSendButton();

        // Show typing indicator
        this.showTypingIndicator();

        // Add visual sending state to both send buttons if present
        try {
            if (this.sendBtn) this.sendBtn.classList.add('sending');
            if (this.sendBtn2) this.sendBtn2.classList.add('sending');
        } catch (err) {
            console.warn('Failed to add sending class to send buttons', err);
        }

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
        } finally {
            // Ensure sending visual state is removed even on unexpected failures
            try {
                if (this.sendBtn) this.sendBtn.classList.remove('sending');
                if (this.sendBtn2) this.sendBtn2.classList.remove('sending');
            } catch (err) {
                console.warn('Failed to remove sending class from send buttons', err);
            }
        }

        // Scroll to bottom
        this.scrollToBottom();
    }

    async callAPI(message) {
        const requestData = {
            model: this.selectedModel || "gpt-4o",
            messages: [
                {
                    role: "system",
                    content: "You are Mark's Personal AI Assistant, powered by GitHub Models. Provide clear, concise, and helpful responses."
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
            // Custom AI icon (sparkle + circuit) - inline SVG for crisp rendering
            avatar.innerHTML = `
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                    <defs>
                        <linearGradient id="g1" x1="0" x2="1" y1="0" y2="1">
                            <stop offset="0" stop-color="#ffd19a" />
                            <stop offset="1" stop-color="#cd7f32" />
                        </linearGradient>
                    </defs>
                    <path d="M12 2c1.1 0 2 .9 2 2v1.2a6 6 0 013.9 3.9H19c1.1 0 2 .9 2 2v2a2 2 0 01-2 2h-1.1a6 6 0 01-3.9 3.9V20c0 1.1-.9 2-2 2s-2-.9-2-2v-1.1a6 6 0 01-3.9-3.9H5c-1.1 0-2-.9-2-2v-2c0-1.1.9-2 2-2h1.1a6 6 0 013.9-3.9V4c0-1.1.9-2 2-2z" fill="url(#g1)"/>
                    <circle cx="12" cy="12" r="2" fill="#fff" opacity="0.12" />
                </svg>
            `;
            avatar.classList.add('ai-avatar');
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