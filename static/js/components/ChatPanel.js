import { html, useState, useEffect, useRef } from '../preact.js';
import { fetchChatInfo, ensureSession, sendChatStream, consumeSSE } from '../api.js';

export function ChatPanel({ open, onClose, chatInfo, setChatInfo, chatHistory, setChatHistory, chatStreaming, setChatStreaming, chatSessionId, setChatSessionId, onRefreshTodos }) {
    const messagesRef = useRef(null);
    const inputRef = useRef(null);
    const [inputValue, setInputValue] = useState('');

    useEffect(() => {
        if (open) {
            loadChatInfo();
            inputRef.current?.focus();
        }
    }, [open]);

    async function loadChatInfo() {
        try {
            const info = await fetchChatInfo();
            setChatInfo(info);
        } catch {
            setChatInfo(null);
        }
    }

    function resetSession() {
        setChatSessionId(null);
        setChatHistory([]);
        localStorage.removeItem('chatSessionId');
    }

    function appendMessage(role, text) {
        setChatHistory(prev => [...prev, { role, content: text }]);
        setTimeout(() => {
            if (messagesRef.current) {
                messagesRef.current.scrollTop = messagesRef.current.scrollHeight;
            }
        }, 10);
    }

    function appendToolEvent(text) {
        setChatHistory(prev => [...prev, { role: 'tool', content: text }]);
        setTimeout(() => {
            if (messagesRef.current) {
                messagesRef.current.scrollTop = messagesRef.current.scrollHeight;
            }
        }, 10);
    }

    async function sendChat() {
        const text = inputValue.trim();
        if (!text || chatStreaming) return;
        setInputValue('');
        setChatStreaming(true);

        appendMessage('user', text);
        const thinkIdx = chatHistory.length;
        appendMessage('thinking', '...');

        let sessionId;
        try {
            sessionId = await ensureSession(chatSessionId);
            if (!chatSessionId) {
                setChatSessionId(sessionId);
                localStorage.setItem('chatSessionId', sessionId);
            }
        } catch {
            setChatStreaming(false);
            setChatHistory(prev => prev.filter((_, i) => i !== thinkIdx));
            appendMessage('assistant', 'Could not start a chat session.');
            return;
        }

        let buffer = '';
        let finalText = '';
        let thinkingRemoved = false;
        const removeThinking = () => {
            if (thinkingRemoved) return;
            thinkingRemoved = true;
            setChatHistory(prev => prev.filter(m => m.role !== 'thinking'));
        };

        try {
            const res = await sendChatStream(text, sessionId);

            if (!res.body) {
                removeThinking();
                appendMessage('assistant', 'Error: no response body');
                return;
            }

            let assistantEl = null;

            await consumeSSE(res.body, (ev) => {
                if (ev._event === 'token') {
                    removeThinking();
                    buffer += ev.content || ev.delta || '';
                    if (!assistantEl) {
                        assistantEl = true;
                    }
                } else if (ev._event === 'tool') {
                    removeThinking();
                    buffer = '';
                    if (chatInfo && chatInfo.tool_use_supported) {
                        const name = ev.name || 'tool';
                        const args = ev.arguments ? JSON.stringify(ev.arguments) : '';
                        appendToolEvent(`\u2192 ${name}${args ? '  ' + args : ''}`);
                    }
                } else if (ev._event === 'tool_result') {
                    removeThinking();
                    const name = ev.name || 'tool';
                    const snippet = (ev.content || '').slice(0, 80);
                    appendToolEvent(`\u2190 ${name}  ${snippet}`);
                } else if (ev._event === 'done') {
                    removeThinking();
                    finalText = ev.response != null ? ev.response : buffer;
                } else if (ev._event === 'error') {
                    removeThinking();
                    appendMessage('assistant', 'Error: ' + (ev.message || 'unknown'));
                    return true;
                }
                return false;
            });

            if (!finalText && buffer) finalText = buffer;
            if (finalText) {
                appendMessage('assistant', finalText);
            } else {
                appendMessage('assistant', '(no response from model)');
            }

            await onRefreshTodos();
        } catch {
            removeThinking();
            appendMessage('assistant', 'Network error. Please try again.');
        } finally {
            setChatStreaming(false);
            inputRef.current?.focus();
        }
    }

    const handleNewSession = () => {
        if (chatStreaming) return;
        resetSession();
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendChat();
        }
    };

    const handleInput = (e) => {
        setInputValue(e.target.value);
        e.target.style.height = 'auto';
        e.target.style.height = Math.min(e.target.scrollHeight, 100) + 'px';
    };

    const providerLabel = chatInfo
        ? `${chatInfo.provider} \u00b7 ${chatInfo.model}`
        : 'connecting\u2026';
    const providerState = !chatInfo ? 'tool-warn'
        : chatStreaming ? 'streaming'
        : chatInfo.tool_use_supported ? 'tool-ok' : 'tool-warn';

    return html`
        <div class=${`chat-panel${open ? '' : ' hidden'}`}>
            <div class="chat-header">
                <div class="chat-header-title">
                    <span>AI Assistant</span>
                    <span class=${`chat-provider ${providerState}`} title=${chatInfo ? `${chatInfo.provider} \u00b7 ${chatInfo.model}` : providerLabel}>
                        <span class="dot"></span>
                        <span>${providerLabel}</span>
                    </span>
                </div>
                <div class="chat-header-right">
                    <button class="chat-icon-btn" onClick=${handleNewSession} title="New chat">+</button>
                    <button class="chat-icon-btn" onClick=${onClose} title="Close">\u00d7</button>
                </div>
            </div>
            <div class="chat-messages" ref=${messagesRef}>
                ${chatHistory.map((msg, i) => {
                    if (msg.role === 'thinking') {
                        return html`<div key=${i} class="chat-msg thinking">
                            <div class="dot"></div><div class="dot"></div><div class="dot"></div>
                        </div>`;
                    }
                    if (msg.role === 'tool') {
                        return html`<div key=${i} class="chat-tool-event">${msg.content}</div>`;
                    }
                    return html`<div key=${i} class=${`chat-msg ${msg.role}`}>${msg.content}</div>`;
                })}
            </div>
            <div class="chat-input-row">
                <textarea
                    ref=${inputRef}
                    class="chat-input"
                    value=${inputValue}
                    onInput=${handleInput}
                    onKeyDown=${handleKeyDown}
                    placeholder="Ask me to manage your todos\u2026"
                    rows="1"
                    disabled=${chatStreaming}
                ></textarea>
                <button class="chat-send" onClick=${sendChat} disabled=${chatStreaming || !inputValue.trim()}>\u27A4</button>
            </div>
        </div>
    `;
}