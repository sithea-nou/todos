import { html } from '../preact.js';
import { priorityBadge, formatDate, isOverdue } from '../utils.js';

export function TodoItem({ todo, onToggle, onDelete, draggable, onDragStart, onDragOver, onDragLeave, onDrop, onDragEnd, isDragging, isOver }) {
    const badge = priorityBadge(todo.priority);
    const overdue = isOverdue(todo.due_date);
    const classes = [
        'todo-item',
        todo.is_completed ? ' completed' : '',
        isDragging ? ' dragging' : '',
        isOver ? ' drag-over' : '',
    ].join('');
    return html`
        <li
            class=${classes}
            draggable=${draggable}
            onDragStart=${onDragStart}
            onDragOver=${onDragOver}
            onDragLeave=${onDragLeave}
            onDrop=${onDrop}
            onDragEnd=${onDragEnd}
        >
            <div
                class=${`checkbox${todo.is_completed ? ' checked' : ''}`}
                onClick=${() => onToggle(todo.id, todo.is_completed)}
            ></div>
            <div class="todo-content">
                <div class="todo-title">${todo.title}</div>
                ${(badge || todo.due_date) && html`
                    <div class="todo-meta">
                        ${badge && html`<span class=${`priority-badge ${badge.cls}`}>${badge.label}</span>`}
                        ${todo.due_date && html`<span class=${`due-date${overdue ? ' overdue' : ''}`}>${formatDate(todo.due_date)}</span>`}
                    </div>
                `}
            </div>
            <button class="delete-btn" onClick=${() => onDelete(todo.id)}>\u00d7</button>
        </li>
    `;
}