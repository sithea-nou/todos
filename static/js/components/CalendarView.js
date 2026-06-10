import { html, useState } from '../preact.js';
import { priorityBadge, getWeekDates, formatWeekRange, toDateStr, normalizeDate, DAY_NAMES, formatDate } from '../utils.js';

export function CalendarView({ todos, onToggle, onDelete, onUpdateDate, filter }) {
    const [weekOffset, setWeekOffset] = useState(0);
    const dates = getWeekDates(weekOffset);
    const today = toDateStr(new Date());

    const weekStart = toDateStr(dates[0]);
    const weekEnd = toDateStr(dates[6]);

    const todosByDate = {};
    const unscheduled = [];
    const otherDates = [];
    for (const t of todos) {
        const dd = normalizeDate(t.due_date);
        if (dd) {
            if (!todosByDate[dd]) todosByDate[dd] = [];
            todosByDate[dd].push(t);
            if (dd < weekStart || dd > weekEnd) {
                otherDates.push(t);
            }
        } else {
            unscheduled.push(t);
        }
    }
    for (const ds of Object.keys(todosByDate)) {
        todosByDate[ds].sort((a, b) => (b.priority || 0) - (a.priority || 0));
    }
    unscheduled.sort((a, b) => (b.priority || 0) - (a.priority || 0));
    otherDates.sort((a, b) => (a.due_date || '').localeCompare(b.due_date || ''));

    const goToTodoWeek = (dateStr) => {
        const todoDate = new Date(dateStr + 'T00:00:00');
        const now = new Date();
        const day = now.getDay();
        const mondayOffset = day === 0 ? -6 : 1 - day;
        const currentMonday = new Date(now.getFullYear(), now.getMonth(), now.getDate() + mondayOffset);
        const diffDays = Math.floor((todoDate - currentMonday) / (7 * 24 * 60 * 60 * 1000));
        setWeekOffset(diffDays);
    };

    return html`
        <div class="calendar-view">
            <div class="calendar-nav">
                <button class="calendar-nav-btn" onClick=${() => setWeekOffset(weekOffset - 1)}>\u2190 Prev</button>
                ${weekOffset !== 0 ? html`<button class="calendar-nav-btn" onClick=${() => setWeekOffset(0)}>Today</button>` : null}
                <h3>${formatWeekRange(dates)}</h3>
                <button class="calendar-nav-btn" onClick=${() => setWeekOffset(weekOffset + 1)}>Next \u2192</button>
            </div>
            <div class="calendar-grid">
                ${dates.map((d, i) => {
                    const ds = toDateStr(d);
                    const isToday = ds === today;
                    const dayTodos = todosByDate[ds] || [];
                    return html`
                        <div key=${ds} class=${`calendar-day${isToday ? ' today' : ''}`}>
                            <div class="calendar-day-header-date">${DAY_NAMES[i]} ${d.getDate()}</div>
                            ${dayTodos.map(t => {
                                const b = priorityBadge(t.priority);
                                return html`
                                    <div key=${t.id} class=${`calendar-card${t.is_completed ? ' completed' : ''}${b ? ' card-' + b.cls : ''}`}>
                                        <div
                                            class=${`calendar-card-check${t.is_completed ? ' checked' : ''}`}
                                            onClick=${() => onToggle(t.id, t.is_completed)}
                                        />
                                        ${b && html`<span class=${`priority-badge ${b.cls}`} style="font-size:0.55rem;padding:0 3px;">${b.label}</span>`}
                                        <span class="calendar-card-title">${t.title}</span>
                                    </div>
                                `;
                            })}
                        </div>
                    `;
                })}
            </div>
            ${unscheduled.length > 0 && html`
                <div class="calendar-unscheduled">
                    <h4>No due date (${unscheduled.length})</h4>
                    ${unscheduled.map(t => {
                        const b = priorityBadge(t.priority);
                        return html`
                            <div key=${t.id} class=${`todo-item${t.is_completed ? ' completed' : ''}`} style="padding:8px 12px;border-bottom:1px solid var(--border)">
                                <div
                                    class=${`checkbox${t.is_completed ? ' checked' : ''}`}
                                    onClick=${() => onToggle(t.id, t.is_completed)}
                                ></div>
                                <div class="todo-content">
                                    <div class="todo-title">${t.title}</div>
                                    ${b && html`
                                        <div class="todo-meta">
                                            <span class=${`priority-badge ${b.cls}`}>${b.label}</span>
                                        </div>
                                    `}
                                </div>
                                <button class="delete-btn" style="opacity:1" onClick=${() => onDelete(t.id)}>\u00d7</button>
                            </div>
                        `;
                    })}
                </div>
            `}
            ${otherDates.length > 0 && html`
                <div class="calendar-unscheduled">
                    <h4>Other dates (${otherDates.length})</h4>
                    ${otherDates.map(t => {
                        const b = priorityBadge(t.priority);
                        const dd = normalizeDate(t.due_date);
                        return html`
                            <div key=${t.id} class=${`todo-item${t.is_completed ? ' completed' : ''}`} style="padding:8px 12px;border-bottom:1px solid var(--border)">
                                <div
                                    class=${`checkbox${t.is_completed ? ' checked' : ''}`}
                                    onClick=${() => onToggle(t.id, t.is_completed)}
                                ></div>
                                <div class="todo-content">
                                    <div class="todo-title">${t.title}</div>
                                    <div class="todo-meta">
                                        ${b && html`<span class=${`priority-badge ${b.cls}`}>${b.label}</span>`}
                                        ${dd && html`<span class="due-date" onClick=${() => goToTodoWeek(dd)} style="cursor:pointer">${formatDate(dd)}</span>`}
                                    </div>
                                </div>
                                <button class="delete-btn" style="opacity:1" onClick=${() => onDelete(t.id)}>\u00d7</button>
                            </div>
                        `;
                    })}
                </div>
            `}
        </div>
    `;
}