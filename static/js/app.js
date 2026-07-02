import { html, useState, useEffect, useCallback } from './preact.js';
import { InputRow } from './components/InputRow.js';
import { Toolbar } from './components/Toolbar.js';
import { TodoList } from './components/TodoList.js';
import { CalendarView } from './components/CalendarView.js';
import { TrashView } from './components/TrashView.js';
import { ChatBubble } from './components/ChatBubble.js';
import { ChatPanel } from './components/ChatPanel.js';
import { ThemeToggle } from './components/ThemeToggle.js';
import { Toast } from './components/Toast.js';
import * as api from './api.js';
import { isOverdue, isDueSoon } from './utils.js';

export function App() {
    const [todos, setTodos] = useState([]);
    const [trash, setTrash] = useState([]);
    const [stats, setStats] = useState(null);
    const [filter, setFilter] = useState('all');
    const [viewMode, setViewMode] = useState('list');
    const [showTrash, setShowTrash] = useState(false);
    const [search, setSearch] = useState('');
    const [priorityFilter, setPriorityFilter] = useState(null);
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
            const params = {};
            if (search.trim()) params.q = search.trim();
            if (priorityFilter !== null) params.priority = priorityFilter;
            const data = await api.fetchTodos(params);
            setTodos(data);
        } catch (e) {
            console.error('Error fetching todos:', e);
            showToast('Failed to fetch todos');
            setTodos([]);
        }
    }, [showToast, search, priorityFilter]);

    const fetchTrash = useCallback(async () => {
        try {
            const data = await api.fetchTrash();
            setTrash(data);
        } catch (e) {
            console.error('Error fetching trash:', e);
            setTrash([]);
        }
    }, []);

    const fetchStats = useCallback(async () => {
        try {
            const data = await api.fetchStats();
            setStats(data);
        } catch (e) {
            setStats(null);
        }
    }, []);

    useEffect(() => { fetchTodos(); }, [fetchTodos]);
    useEffect(() => { if (showTrash) fetchTrash(); }, [showTrash, fetchTrash]);
    useEffect(() => { fetchStats(); }, [fetchTodos]);

    const addTodo = useCallback(async (data) => {
        try {
            await api.addTodo(data);
            await Promise.all([fetchTodos(), fetchStats()]);
        } catch (e) {
            console.error('Error creating todo:', e);
            showToast('Failed to create todo');
        }
    }, [fetchTodos, fetchStats, showToast]);

    const toggleTodo = useCallback(async (id, isCompleted) => {
        try {
            await api.toggleTodo(id, isCompleted);
            await Promise.all([fetchTodos(), fetchStats()]);
        } catch (e) {
            console.error('Error toggling todo:', e);
            showToast('Failed to update todo');
        }
    }, [fetchTodos, fetchStats, showToast]);

    const updateTodo = useCallback(async (id, changes) => {
        try {
            await api.updateTodo(id, changes);
            await Promise.all([fetchTodos(), fetchStats()]);
        } catch (e) {
            console.error('Error updating todo:', e);
            showToast('Failed to update todo');
        }
    }, [fetchTodos, fetchStats, showToast]);

    const deleteTodo = useCallback(async (id) => {
        try {
            await api.deleteTodo(id);
            await Promise.all([fetchTodos(), fetchStats(), showTrash ? fetchTrash() : Promise.resolve()]);
        } catch (e) {
            console.error('Error deleting todo:', e);
            showToast('Failed to delete todo');
        }
    }, [fetchTodos, fetchStats, fetchTrash, showTrash, showToast]);

    const restoreTodo = useCallback(async (id) => {
        try {
            await api.restoreTodo(id);
            await Promise.all([fetchTodos(), fetchTrash(), fetchStats()]);
            showToast('Todo restored');
        } catch (e) {
            console.error('Error restoring todo:', e);
            showToast('Failed to restore todo');
        }
    }, [fetchTodos, fetchTrash, fetchStats, showToast]);

    const purgeTodo = useCallback(async (id) => {
        try {
            await api.purgeTodo(id);
            await fetchTrash();
            showToast('Todo permanently deleted');
        } catch (e) {
            console.error('Error purging todo:', e);
            showToast('Failed to purge todo');
        }
    }, [fetchTrash, showToast]);

    const emptyTrash = useCallback(async () => {
        if (!confirm('Permanently delete all todos in trash?')) return;
        try {
            await api.emptyTrash();
            await Promise.all([fetchTrash(), fetchStats()]);
            showToast('Trash emptied');
        } catch (e) {
            console.error('Error emptying trash:', e);
            showToast('Failed to empty trash');
        }
    }, [fetchTrash, fetchStats, showToast]);

    const updateTodoDate = useCallback(async (id, dueDate) => {
        try {
            await api.updateTodoDate(id, dueDate);
            await Promise.all([fetchTodos(), fetchStats()]);
        } catch (e) {
            console.error('Error updating date:', e);
            showToast('Failed to update date');
        }
    }, [fetchTodos, fetchStats, showToast]);

    const clearCompleted = useCallback(async () => {
        const ids = todos.filter(t => t.is_completed).map(t => t.id);
        await Promise.all(ids.map(id => api.deleteTodo(id)));
        await Promise.all([fetchTodos(), fetchStats()]);
    }, [todos, fetchTodos, fetchStats]);

    const reorderTodos = useCallback(async (items) => {
        try {
            await api.reorderTodos(items);
            await fetchTodos();
        } catch (e) {
            console.error('Error reordering todos:', e);
            showToast('Failed to reorder');
        }
    }, [fetchTodos, showToast]);

    // Reminders: notify the user about overdue / due-soon todos once on load.
    useEffect(() => {
        if (!('Notification' in window) || todos.length === 0) return;
        const dueSoon = todos.filter(t => !t.is_completed && isDueSoon(t.due_date));
        const overdueItems = todos.filter(t => !t.is_completed && isOverdue(t.due_date));
        if (dueSoon.length === 0 && overdueItems.length === 0) return;
        if (Notification.permission === 'granted') {
            const overdueMsg = overdueItems.length > 0 ? `${overdueItems.length} overdue` : '';
            const soonMsg = dueSoon.length > 0 ? `${dueSoon.length} due soon` : '';
            const msg = [overdueMsg, soonMsg].filter(Boolean).join(', ');
            if (msg) new Notification('MyToDo reminders', { body: msg });
        } else if (Notification.permission === 'default') {
            Notification.requestPermission();
        }
    }, [todos]);

    const filtered = todos.filter(t => {
        if (filter === 'active') return !t.is_completed;
        if (filter === 'completed') return t.is_completed;
        return true;
    });

    const activeCount = todos.filter(t => !t.is_completed).length;
    const completedCount = todos.filter(t => t.is_completed).length;
    const progress = stats ? (stats.total === 0 ? 0 : (stats.completed / stats.total) * 100) : 0;
    const overdueCount = stats ? stats.overdue : 0;

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
                ${stats && html`
                    <div class="stats-bar">
                        <span>${stats.total} total</span>
                        <span>${stats.active} active</span>
                        <span>${stats.completed} done</span>
                        ${overdueCount > 0 && html`<span class="stat-overdue">${overdueCount} overdue</span>`}
                    </div>
                `}
                <${Toolbar}
                    filter=${filter}
                    onFilterChange=${setFilter}
                    completedCount=${completedCount}
                    onClearCompleted=${clearCompleted}
                    viewMode=${viewMode}
                    onViewModeChange=${setViewMode}
                    search=${search}
                    onSearchChange=${setSearch}
                    priorityFilter=${priorityFilter}
                    onPriorityFilterChange=${setPriorityFilter}
                    showTrash=${showTrash}
                    onToggleTrash=${() => setShowTrash(!showTrash)}
                />
                ${showTrash
                    ? html`<${TrashView} trash=${trash} onRestore=${restoreTodo} onPurge=${purgeTodo} onEmpty=${emptyTrash} />`
                    : (viewMode === 'calendar'
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
                            onUpdate=${updateTodo}
                            onReorder=${reorderTodos}
                            filter=${filter}
                            totalCount=${todos.length}
                        />`)
                }
                ${todos.length > 0 && !showTrash && html`
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
            onRefreshTodos=${() => Promise.all([fetchTodos(), fetchStats()])}
        />
        <${Toast} message=${toast} />
    `;
}