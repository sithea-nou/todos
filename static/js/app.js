import { html, useState, useEffect, useCallback } from './preact.js';
import { InputRow } from './components/InputRow.js';
import { Toolbar } from './components/Toolbar.js';
import { TodoList } from './components/TodoList.js';
import { CalendarView } from './components/CalendarView.js';
import { ChatBubble } from './components/ChatBubble.js';
import { ChatPanel } from './components/ChatPanel.js';
import { ThemeToggle } from './components/ThemeToggle.js';
import { Toast } from './components/Toast.js';
import * as api from './api.js';

export function App() {
    const [todos, setTodos] = useState([]);
    const [filter, setFilter] = useState('all');
    const [viewMode, setViewMode] = useState('list');
    const [error, setError] = useState(null);
    const [chatOpen, setChatOpen] = useState(false);
    const [chatHistory, setChatHistory] = useState([]);
    const [chatStreaming, setChatStreaming] = useState(false);
    const [chatInfo, setChatInfo] = useState(null);
    const [chatSessionId, setChatSessionId] = useState(() => localStorage.getItem('chatSessionId') || null);
    const [toast, setToast] = useState(null);
    const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'auto');

    useEffect(() => {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
    }, [theme]);

    const showToast = useCallback((msg) => {
        setToast(msg);
        setTimeout(() => setToast(null), 3000);
    }, []);

    const fetchTodos = useCallback(async () => {
        try {
            const data = await api.fetchTodos();
            setTodos(data);
        } catch (e) {
            console.error('Error fetching todos:', e);
            showToast('Failed to fetch todos');
            setTodos([]);
        }
    }, [showToast]);

    useEffect(() => { fetchTodos(); }, [fetchTodos]);

    const addTodo = useCallback(async (data) => {
        try {
            await api.addTodo(data);
            await fetchTodos();
        } catch (e) {
            console.error('Error creating todo:', e);
            showToast('Failed to create todo');
        }
    }, [fetchTodos, showToast]);

    const toggleTodo = useCallback(async (id, isCompleted) => {
        try {
            await api.toggleTodo(id, isCompleted);
            await fetchTodos();
        } catch (e) {
            console.error('Error toggling todo:', e);
            showToast('Failed to update todo');
        }
    }, [fetchTodos, showToast]);

    const deleteTodo = useCallback(async (id) => {
        try {
            await api.deleteTodo(id);
            await fetchTodos();
        } catch (e) {
            console.error('Error deleting todo:', e);
            showToast('Failed to delete todo');
        }
    }, [fetchTodos, showToast]);

    const updateTodoDate = useCallback(async (id, dueDate) => {
        try {
            await api.updateTodoDate(id, dueDate);
            await fetchTodos();
        } catch (e) {
            console.error('Error updating date:', e);
            showToast('Failed to update date');
        }
    }, [fetchTodos, showToast]);

    const clearCompleted = useCallback(async () => {
        const ids = todos.filter(t => t.is_completed).map(t => t.id);
        await api.clearCompleted(ids);
        await fetchTodos();
    }, [todos, fetchTodos]);

    const reorderTodos = useCallback(async (items) => {
        try {
            await api.reorderTodos(items);
            await fetchTodos();
        } catch (e) {
            console.error('Error reordering todos:', e);
            showToast('Failed to reorder');
        }
    }, [fetchTodos, showToast]);

    const filtered = todos.filter(t => {
        if (filter === 'active') return !t.is_completed;
        if (filter === 'completed') return t.is_completed;
        return true;
    });

    const activeCount = todos.filter(t => !t.is_completed).length;
    const completedCount = todos.filter(t => t.is_completed).length;
    const progress = todos.length === 0 ? 0 : (completedCount / todos.length) * 100;

    return html`
        <div class="container">
            <div class="header">
                <h1>MyToDo</h1>
                <p>${activeCount} task${activeCount !== 1 ? 's' : ''} remaining</p>
                <${ThemeToggle} theme=${theme} onThemeChange=${setTheme} />
            </div>

            <div class="card">
                <${InputRow} onAdd=${addTodo} />
                <div class="progress-track">
                    <div class="progress-fill" style=${`width: ${progress}%`}></div>
                </div>
                <${Toolbar}
                    filter=${filter}
                    onFilterChange=${setFilter}
                    completedCount=${completedCount}
                    onClearCompleted=${clearCompleted}
                    viewMode=${viewMode}
                    onViewModeChange=${setViewMode}
                />
                ${viewMode === 'calendar'
                    ? html`<${CalendarView}
                        todos=${filtered}
                        onToggle=${toggleTodo}
                        onDelete=${deleteTodo}
                        onUpdateDate=${updateTodoDate}
                        filter=${filter}
                    />`
                    : html`<${TodoList}
                        todos=${filtered}
                        onToggle=${toggleTodo}
                        onDelete=${deleteTodo}
                        onReorder=${reorderTodos}
                        filter=${filter}
                        totalCount=${todos.length}
                    />`
                }
                ${todos.length > 0 && html`
                    <div class="stats">${completedCount} of ${todos.length} completed</div>
                `}
            </div>
        </div>

        <${ChatBubble} onClick=${() => setChatOpen(!chatOpen)} />
        <${ChatPanel}
            open=${chatOpen}
            onClose=${() => setChatOpen(false)}
            chatInfo=${chatInfo}
            setChatInfo=${setChatInfo}
            chatHistory=${chatHistory}
            setChatHistory=${setChatHistory}
            chatStreaming=${chatStreaming}
            setChatStreaming=${setChatStreaming}
            chatSessionId=${chatSessionId}
            setChatSessionId=${setChatSessionId}
            onRefreshTodos=${fetchTodos}
        />
        <${Toast} message=${toast} />
    `;
}