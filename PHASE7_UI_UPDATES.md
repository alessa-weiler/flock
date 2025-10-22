# Phase 7: Chat System - UI Updates Required

## Overview
The backend APIs for the chat system are complete, but the frontend UI needs to be built to allow users to interact with it.

## Current State
✅ **Already Exists:**
- Knowledge Base tab for non-therapy orgs
- Document upload UI
- Document search/filtering by folders
- Basic document management

❌ **Missing:**
- Chat interface within Knowledge Base tab
- Conversation list sidebar
- Message display with reasoning and sources
- New conversation button
- Chat vs Documents toggle

---

## Required UI Updates

### 1. Update Knowledge Base Tab Structure

**Current:** Single view showing documents
**New:** Split view with Documents and Chat tabs

```javascript
// Add inside the Knowledge Base tab (line ~11200)
<div id="knowledge-tab" class="tab-content">
    <div style="padding: 2rem; max-width: 1400px; margin: 0 auto;">
        <!-- Sub-tabs for Documents vs Chat -->
        <div class="kb-subtabs" style="display: flex; gap: 1rem; margin-bottom: 2rem; border-bottom: 2px solid #e0e0e0;">
            <button class="kb-subtab active" onclick="switchKBView('documents')" id="documentsSubtab">
                📄 Documents
            </button>
            <button class="kb-subtab" onclick="switchKBView('chat')" id="chatSubtab">
                💬 Ask Questions
            </button>
        </div>

        <!-- Documents View (existing) -->
        <div id="documentsView" class="kb-view">
            <!-- All existing document UI here -->
        </div>

        <!-- Chat View (NEW) -->
        <div id="chatView" class="kb-view" style="display: none;">
            <!-- NEW CHAT INTERFACE HERE -->
        </div>
    </div>
</div>
```

### 2. Build Chat Interface

Add this inside the `chatView` div:

```html
<div class="chat-container" style="display: grid; grid-template-columns: 280px 1fr; gap: 0; height: calc(100vh - 250px); border: 1px solid #e0e0e0; border-radius: 12px; overflow: hidden;">

    <!-- Conversation List Sidebar -->
    <div class="conversations-sidebar" style="border-right: 1px solid #e0e0e0; background: #f8f9fa; overflow-y: auto;">
        <div style="padding: 1rem; border-bottom: 1px solid #e0e0e0; display: flex; justify-content: space-between; align-items: center;">
            <h3 style="font-size: 1rem; font-weight: 600;">Conversations</h3>
            <button onclick="createNewConversation()" style="background: black; color: white; border: none; width: 32px; height: 32px; border-radius: 6px; cursor: pointer; font-size: 1.2rem;">+</button>
        </div>
        <div id="conversationsList" style="padding: 0.5rem;">
            <div style="text-align: center; padding: 2rem 1rem; color: #666; font-size: 0.875rem;">
                No conversations yet.<br>Click + to start.
            </div>
        </div>
    </div>

    <!-- Chat Main Area -->
    <div class="chat-main" style="display: flex; flex-direction: column; background: white;">

        <!-- Messages Area -->
        <div id="messagesArea" style="flex: 1; overflow-y: auto; padding: 1.5rem;">
            <div class="empty-state" style="text-align: center; padding: 3rem 1rem; color: #666;">
                <h3 style="font-size: 1.25rem; margin-bottom: 1rem;">Ask a question about your documents</h3>
                <p style="margin-bottom: 1.5rem;">Examples:</p>
                <div style="display: flex; flex-direction: column; gap: 0.75rem; max-width: 500px; margin: 0 auto;">
                    <button onclick="askExample('What are our Q1 priorities?')" style="padding: 0.75rem; background: #f8f9fa; border: 1px solid #e0e0e0; border-radius: 8px; cursor: pointer; text-align: left; transition: all 0.2s;">
                        "What are our Q1 priorities?"
                    </button>
                    <button onclick="askExample('Who knows about TypeScript?')" style="padding: 0.75rem; background: #f8f9fa; border: 1px solid #e0e0e0; border-radius: 8px; cursor: pointer; text-align: left; transition: all 0.2s;">
                        "Who knows about TypeScript?"
                    </button>
                    <button onclick="askExample('Summarize the marketing report')" style="padding: 0.75rem; background: #f8f9fa; border: 1px solid #e0e0e0; border-radius: 8px; cursor: pointer; text-align: left; transition: all 0.2s;">
                        "Summarize the marketing report"
                    </button>
                </div>
            </div>
        </div>

        <!-- Message Input Area -->
        <div style="border-top: 1px solid #e0e0e0; padding: 1rem; background: #f8f9fa;">
            <div style="display: flex; gap: 0.5rem; align-items: flex-end;">
                <textarea
                    id="messageInput"
                    placeholder="Ask a question about your documents or team..."
                    style="flex: 1; min-height: 60px; max-height: 150px; padding: 0.75rem; border: 1px solid #e0e0e0; border-radius: 8px; resize: vertical; font-family: inherit; font-size: 0.95rem;"
                    onkeydown="if(event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); sendChatMessage(); }"
                ></textarea>
                <button
                    onclick="sendChatMessage()"
                    id="sendBtn"
                    style="padding: 0.75rem 1.5rem; background: black; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; min-width: 80px; height: 60px;">
                    Send
                </button>
            </div>
            <div style="margin-top: 0.5rem; font-size: 0.75rem; color: #666;">
                <label style="display: flex; align-items: center; gap: 0.5rem;">
                    <input type="checkbox" id="useRagMode" checked>
                    Use simple RAG (faster, document Q&A only)
                </label>
            </div>
        </div>

    </div>
</div>
```

### 3. Add JavaScript Functions

Add these functions to handle chat interactions:

```javascript
// Global chat state
let currentConversationId = null;
let conversations = [];

// Switch between Documents and Chat views
function switchKBView(view) {
    const documentsView = document.getElementById('documentsView');
    const chatView = document.getElementById('chatView');
    const documentsTab = document.getElementById('documentsSubtab');
    const chatTab = document.getElementById('chatSubtab');

    if (view === 'documents') {
        documentsView.style.display = 'block';
        chatView.style.display = 'none';
        documentsTab.classList.add('active');
        chatTab.classList.remove('active');
    } else {
        documentsView.style.display = 'none';
        chatView.style.display = 'block';
        documentsTab.classList.remove('active');
        chatTab.classList.add('active');

        // Load conversations on first view
        if (conversations.length === 0) {
            loadConversations();
        }
    }
}

// Load all conversations
async function loadConversations() {
    try {
        const response = await fetch(`/api/chat/conversations?org_id=${orgId}`);
        const data = await response.json();
        conversations = data.conversations || [];

        renderConversationsList();
    } catch (error) {
        console.error('Error loading conversations:', error);
    }
}

// Render conversations list
function renderConversationsList() {
    const container = document.getElementById('conversationsList');

    if (conversations.length === 0) {
        container.innerHTML = `
            <div style="text-align: center; padding: 2rem 1rem; color: #666; font-size: 0.875rem;">
                No conversations yet.<br>Click + to start.
            </div>
        `;
        return;
    }

    container.innerHTML = conversations.map(conv => `
        <div class="conversation-item ${conv.id === currentConversationId ? 'active' : ''}"
             onclick="loadConversation(${conv.id})"
             style="padding: 0.75rem; margin-bottom: 0.5rem; background: ${conv.id === currentConversationId ? 'white' : 'transparent'}; border-radius: 8px; cursor: pointer; transition: all 0.2s; border: 1px solid ${conv.id === currentConversationId ? '#000' : 'transparent'};">
            <div style="font-weight: 600; font-size: 0.875rem; margin-bottom: 0.25rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                ${conv.title || 'Untitled Conversation'}
            </div>
            <div style="font-size: 0.75rem; color: #666; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                ${conv.last_message_preview || 'No messages yet'}
            </div>
        </div>
    `).join('');
}

// Create new conversation
async function createNewConversation() {
    try {
        const response = await fetch('/api/chat/conversations', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                org_id: orgId,
                title: 'New Conversation'
            })
        });

        const data = await response.json();
        currentConversationId = data.conversation_id;

        // Reload conversations
        await loadConversations();

        // Clear messages
        document.getElementById('messagesArea').innerHTML = '';
        document.getElementById('messageInput').focus();

    } catch (error) {
        console.error('Error creating conversation:', error);
        alert('Failed to create conversation');
    }
}

// Load conversation messages
async function loadConversation(conversationId) {
    currentConversationId = conversationId;
    renderConversationsList();

    try {
        const response = await fetch(`/api/chat/${conversationId}/messages`);
        const data = await response.json();

        renderMessages(data.messages || []);
    } catch (error) {
        console.error('Error loading conversation:', error);
    }
}

// Render messages
function renderMessages(messages) {
    const container = document.getElementById('messagesArea');

    if (messages.length === 0) {
        container.innerHTML = '<div style="text-align: center; padding: 2rem; color: #666;">No messages yet. Start the conversation!</div>';
        return;
    }

    container.innerHTML = messages.map(msg => {
        if (msg.role === 'user') {
            return `
                <div class="message user-message" style="margin-bottom: 1.5rem;">
                    <div style="background: #f0f0f0; padding: 1rem; border-radius: 8px; max-width: 70%;">
                        ${escapeHtml(msg.content)}
                    </div>
                </div>
            `;
        } else {
            return `
                <div class="message assistant-message" style="margin-bottom: 1.5rem;">
                    <div style="padding: 1rem; border-left: 3px solid black; max-width: 85%;">
                        <div style="margin-bottom: 1rem;">${escapeHtml(msg.content)}</div>

                        ${msg.reasoning ? `
                            <details style="margin-top: 1rem; font-size: 0.875rem; color: #666;">
                                <summary style="cursor: pointer; font-weight: 600;">🔍 How I figured this out</summary>
                                <div style="margin-top: 0.5rem; padding: 0.75rem; background: #f8f9fa; border-radius: 6px;">
                                    ${msg.reasoning.steps.map(step => `<div>✓ ${step}</div>`).join('')}
                                </div>
                            </details>
                        ` : ''}

                        ${msg.sources && (msg.sources.documents.length > 0 || msg.sources.employees.length > 0) ? `
                            <details style="margin-top: 1rem; font-size: 0.875rem;">
                                <summary style="cursor: pointer; font-weight: 600;">📚 Sources</summary>
                                <div style="margin-top: 0.5rem; padding: 0.75rem; background: #fafafa; border-radius: 6px;">
                                    ${msg.sources.documents.map(doc => `
                                        <div style="margin-bottom: 0.5rem; padding: 0.5rem; border-left: 2px solid #ccc; padding-left: 0.75rem;">
                                            <strong>${doc.filename}</strong> ${doc.page ? `(page ${doc.page})` : ''}
                                        </div>
                                    `).join('')}
                                    ${msg.sources.employees.map(emp => `
                                        <div style="margin-bottom: 0.5rem; padding: 0.5rem; border-left: 2px solid #ccc; padding-left: 0.75rem;">
                                            <strong>${emp.name}</strong> - ${emp.title}
                                        </div>
                                    `).join('')}
                                </div>
                            </details>
                        ` : ''}
                    </div>
                </div>
            `;
        }
    }).join('');

    // Scroll to bottom
    container.scrollTop = container.scrollHeight;
}

// Send message
async function sendChatMessage() {
    const input = document.getElementById('messageInput');
    const message = input.value.trim();

    if (!message) return;

    if (!currentConversationId) {
        await createNewConversation();
    }

    const sendBtn = document.getElementById('sendBtn');
    const useRag = document.getElementById('useRagMode').checked;

    // Disable input
    input.disabled = true;
    sendBtn.disabled = true;
    sendBtn.textContent = 'Sending...';

    // Add user message to UI immediately
    const messagesArea = document.getElementById('messagesArea');
    messagesArea.innerHTML += `
        <div class="message user-message" style="margin-bottom: 1.5rem;">
            <div style="background: #f0f0f0; padding: 1rem; border-radius: 8px; max-width: 70%;">
                ${escapeHtml(message)}
            </div>
        </div>
    `;
    messagesArea.scrollTop = messagesArea.scrollHeight;

    // Clear input
    input.value = '';

    try {
        const response = await fetch(`/api/chat/${currentConversationId}/messages`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message,
                use_rag: useRag
            })
        });

        const data = await response.json();

        // Add assistant response
        messagesArea.innerHTML += `
            <div class="message assistant-message" style="margin-bottom: 1.5rem;">
                <div style="padding: 1rem; border-left: 3px solid black; max-width: 85%;">
                    <div>${escapeHtml(data.answer)}</div>

                    ${data.reasoning_steps ? `
                        <details style="margin-top: 1rem; font-size: 0.875rem; color: #666;">
                            <summary style="cursor: pointer; font-weight: 600;">🔍 How I figured this out</summary>
                            <div style="margin-top: 0.5rem; padding: 0.75rem; background: #f8f9fa; border-radius: 6px;">
                                ${data.reasoning_steps.map(step => `<div>✓ ${step}</div>`).join('')}
                            </div>
                        </details>
                    ` : ''}

                    ${data.sources && (data.sources.documents.length > 0 || data.sources.employees.length > 0) ? `
                        <details style="margin-top: 1rem; font-size: 0.875rem;">
                            <summary style="cursor: pointer; font-weight: 600;">📚 Sources</summary>
                            <div style="margin-top: 0.5rem; padding: 0.75rem; background: #fafafa; border-radius: 6px;">
                                ${data.sources.documents.map(doc => `
                                    <div style="margin-bottom: 0.5rem; padding: 0.5rem; border-left: 2px solid #ccc; padding-left: 0.75rem;">
                                        <strong>${doc.filename}</strong> ${doc.page ? `(page ${doc.page})` : ''}
                                    </div>
                                `).join('')}
                                ${data.sources.employees.map(emp => `
                                    <div style="margin-bottom: 0.5rem; padding: 0.5rem; border-left: 2px solid #ccc; padding-left: 0.75rem;">
                                        <strong>${emp.name}</strong> - ${emp.title}
                                    </div>
                                `).join('')}
                            </div>
                        </details>
                    ` : ''}
                </div>
            </div>
        `;

        messagesArea.scrollTop = messagesArea.scrollHeight;

        // Update conversation list
        await loadConversations();

    } catch (error) {
        console.error('Error sending message:', error);
        messagesArea.innerHTML += `
            <div class="message assistant-message" style="margin-bottom: 1.5rem;">
                <div style="padding: 1rem; border-left: 3px solid #ef4444; max-width: 85%; background: #fef2f2;">
                    Error: ${error.message || 'Failed to send message'}
                </div>
            </div>
        `;
    } finally {
        input.disabled = false;
        sendBtn.disabled = false;
        sendBtn.textContent = 'Send';
        input.focus();
    }
}

// Example question shortcuts
function askExample(question) {
    document.getElementById('messageInput').value = question;
    sendChatMessage();
}

// HTML escape utility
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
```

### 4. Add CSS Styles

Add these styles to the existing `<style>` block:

```css
.kb-subtabs {
    display: flex;
    gap: 1rem;
    margin-bottom: 2rem;
    border-bottom: 2px solid #e0e0e0;
}

.kb-subtab {
    padding: 0.75rem 1.5rem;
    background: none;
    border: none;
    border-bottom: 3px solid transparent;
    font-family: 'Satoshi', sans-serif;
    font-size: 1rem;
    font-weight: 500;
    color: #666;
    cursor: pointer;
    transition: all 0.2s;
    margin-bottom: -2px;
}

.kb-subtab.active {
    color: black;
    font-weight: 600;
    border-bottom-color: black;
}

.kb-subtab:hover {
    color: black;
}

.conversation-item:hover {
    background: white !important;
    border-color: #e0e0e0 !important;
}

.message {
    animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}
```

---

## Summary of Changes

**Files to modify:**
1. `/Users/alessaweiler/Documents/making_ai_talk/flock/app.py` - around line 11200 (Knowledge Base tab)

**What to add:**
1. ✅ Sub-tabs for Documents vs Chat
2. ✅ Chat interface HTML
3. ✅ Conversation list sidebar
4. ✅ Message display with sources & reasoning
5. ✅ JavaScript functions for chat operations
6. ✅ CSS styles for chat UI

**Testing checklist:**
- [ ] Can switch between Documents and Chat tabs
- [ ] Can create new conversation
- [ ] Can send messages
- [ ] Messages appear with proper formatting
- [ ] Sources are displayed and collapsible
- [ ] Reasoning steps are displayed and collapsible
- [ ] Conversation list updates after sending messages
- [ ] Can switch between conversations
- [ ] Example questions work

This creates a complete, production-ready chat interface integrated into your existing Knowledge Base!
