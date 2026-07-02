import { html, useState } from '../preact.js';
import { priorityBadge, formatDate, isOverdue, isDueSoon, parseTags } from '../utils.js';

export function TodoItem({ todo, onToggle, onDelete, onUpdate, draggable, onDragStart, onDragOver, onDragLeave, onDrop, onDragEnd, isDragging, isOver }) {
    const [editing, setEditing] = useState(false);
    const [title, setTitle] = useState(todo.title);
    const [description, setDescription] = useState(todo.description || '');
    const [tags, setTags] = useState(todo.tags || '');

    const badge = priorityBadge(todo.priority);
    const overdue = isOverdue(todo.due_date);
    const soon = isDueSoon(todo.due_date);
    const tagsList = parseTags(todo.tags);
    const classes = [
        'todo-item',
        todo.is_completed ? ' completed' : '',
        isDragging ? ' dragging' : '',
        isOver ? ' drag-over' : '',
        overdue ? ' overdue' : '',
        soon && !overdue ? ' due-soon' : '',
    ].join('');

    const startEdit = () => {
        setTitle(todo.title);
        setDescription(todo.description || '');
        setTags(todo.tags || '');
        setEditing(true);
    };

    const saveEdit = () => {
        const changes = {};
        if (title.trim() && title !== todo.title) changes.title = title.trim();
        if (description !== (todo.description || '')) changes.description = description || null;
        if (tags !== (todo.tags || '')) changes.tags = tags || null;
        if (Object.keys(changes).length) onUpdate(todo.id, changes);
        setEditing(false);
    };

    const cancelEdit = () => setEditing(false);

    if (editing) {
        return html`
            <li class=${`todo-item editing${todo.is_completed ? ' completed' : ''}`}>
                <div class=${`checkbox${todo.is_completed ? ' checked' : ''}`}
                    onClick=${() => onToggle(todo.id, todo.is_completed)} />
                <div class="todo-content">
                    <input class="edit-input" type="text" value=${title}
                        onInput=${e => setTitle(e.target.value)}
                        onKeyDown=${e => { if (e.key === 'Enter') saveEdit(); if (e.key === 'Escape') cancelEdit(); }}
                        autoFocus />
                    <textarea class="edit-input edit-desc" rows="2" placeholder="Description"
                        value=${description}
                        onInput=${e => setDescription(e.target.value)} />
                    <input class="edit-input edit-tags" type="text" placeholder="tags (comma-separated)"
                        value=${tags}
                        onInput=${e => setTags(e.target.value)} />
                    <div class="edit-actions">
                        <button class="save-btn" onClick=${saveEdit}>Save</button>
                        <button class="cancel-btn" onClick=${cancelEdit}>Cancel</button>
                    </div>
                </div>
            </li>
        `;
    }

    return html`
        <li
            class=${classes}
            draggable=${draggable}
            onDragStart=${onDragStart}
            onDragOver=${onDragOver}
            onDragLeave=${onDragLeave}
            onDrop=${onDrop}
            onDragEnd=${onDragEnd}
            onDoubleClick=${startEdit}
        >
            <div
                class=${`checkbox${todo.is_completed ? ' checked' : ''}`}
                onClick=${() => onToggle(todo.id, todo.is_completed)}
            ></div>
            <div class="todo-content">
                <div class="todo-title" onClick=${startEdit} title="Double-click to edit">${todo.title}</div>
                ${todo.description && html`<div class="todo-desc">${todo.description}</div>`}
                ${(badge || todo.due_date || tagsList.length > 0) && html`
                    <div class="todo-meta">
                        ${badge && html`<span class=${`priority-badge ${badge.cls}`}>${badge.label}</span>`}
                        ${todo.due_date && html`<span class=${`due-date${overdue ? ' overdue' : ''}${soon && !overdue ? ' soon' : ''}`}>${formatDate(todo.due_date)}</span>`}
                        ${tagsList.map(t => html`<span key=${t} class="tag-chip">${t}</span>`)}
                    </div>
                `}
            </div>
            <button class="edit-btn" onClick=${startEdit} title="Edit">\u270e</button>
            <button class="delete-btn" onClick=${() => onDelete(todo.id)} title="Delete">\u00d7</button>
        </li>
    `;
}