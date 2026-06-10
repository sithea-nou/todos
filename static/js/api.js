const API = '/api/todos';
const CHAT_API = '/api/chat';

export async function fetchTodos() {
    const res = await fetch(`${API}/?order_by=position`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

export async function addTodo(data) {
    const body = typeof data === 'string' ? { title: data } : data;
    if (!body.title || !body.title.trim()) return;
    const res = await fetch(`${API}/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

export async function toggleTodo(id, isCompleted) {
    const res = await fetch(`${API}/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_completed: !isCompleted }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

export async function deleteTodo(id) {
    const res = await fetch(`${API}/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

export async function updateTodoDate(id, dueDate) {
    const res = await fetch(`${API}/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ due_date: dueDate }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

export async function clearCompleted(ids) {
    for (const id of ids) {
        await fetch(`${API}/${id}`, { method: 'DELETE' });
    }
}

export async function reorderTodos(items) {
    const res = await fetch(`${API}/reorder`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

export async function fetchChatInfo() {
    const res = await fetch(`${CHAT_API}/info`);
    if (!res.ok) throw new Error(`info ${res.status}`);
    return res.json();
}

export async function ensureSession(chatSessionId) {
    if (chatSessionId) {
        const res = await fetch(`${CHAT_API}/sessions/${chatSessionId}`);
        if (res.ok) return chatSessionId;
    }
    const res = await fetch(`${CHAT_API}/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: 'New chat' }),
    });
    if (!res.ok) throw new Error(`session ${res.status}`);
    const session = await res.json();
    return session.id;
}

export async function sendChatStream(text, sessionId) {
    const res = await fetch(`${CHAT_API}/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, session_id: sessionId }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res;
}

export function consumeSSE(body, onEvent) {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    const dispatch = (raw) => {
        let event = 'message';
        const dataLines = [];
        for (const line of raw.split('\n')) {
            if (!line || line.startsWith(':')) continue;
            const idx = line.indexOf(':');
            if (idx < 0) continue;
            const field = line.slice(0, idx);
            let value = line.slice(idx + 1);
            if (value.startsWith(' ')) value = value.slice(1);
            if (field === 'event') event = value;
            else if (field === 'data') dataLines.push(value);
        }
        if (!dataLines.length) return false;
        let parsed;
        try { parsed = JSON.parse(dataLines.join('\n')); } catch { return false; }
        parsed._event = event;
        return onEvent(parsed);
    };

    return (async () => {
        try {
            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const frames = buffer.split(/\n\n|(?=\nevent:)/);
                buffer = frames.pop() || '';
                for (const ev of frames) {
                    if (!ev.trim()) continue;
                    const stop = await dispatch(ev);
                    if (stop) { try { await reader.cancel(); } catch {} return; }
                }
            }
            if (buffer.trim()) await dispatch(buffer);
        } finally {
            try { reader.releaseLock(); } catch {}
        }
    })();
}