import { html, useState } from '../preact.js';
import { TodoItem } from './TodoItem.js';

export function TodoList({ todos, onToggle, onDelete, onReorder, filter, totalCount }) {
    const [dragIdx, setDragIdx] = useState(null);
    const [overIdx, setOverIdx] = useState(null);

    const canDrag = filter === 'all';

    if (todos.length === 0) {
        let msg = 'No todos yet. Add one above!';
        if (filter === 'active') msg = 'No active todos. Well done!';
        else if (filter === 'completed') msg = 'No completed todos yet.';
        return html`
            <div class="empty-state">
                <div class="icon">
                    ${filter === 'active' ? '\u2713' : filter === 'completed' ? '\u25cb' : '\ud83d\udccb'}
                </div>
                <p>${msg}</p>
            </div>
        `;
    }

    const handleDragStart = (idx) => {
        if (!canDrag) return;
        setDragIdx(idx);
    };
    const handleDragOver = (e, idx) => {
        if (!canDrag) return;
        e.preventDefault();
        setOverIdx(idx);
    };
    const handleDragLeave = () => { setOverIdx(null); };
    const handleDrop = (e, dropIdx) => {
        e.preventDefault();
        setOverIdx(null);
        if (dragIdx === null || dragIdx === dropIdx) { setDragIdx(null); return; }
        const items = [...todos];
        const [moved] = items.splice(dragIdx, 1);
        items.splice(dropIdx, 0, moved);
        setDragIdx(null);
        onReorder(items.map((t, i) => ({ id: t.id, position: i })));
    };
    const handleDragEnd = () => { setDragIdx(null); setOverIdx(null); };

    return html`
        <ul class="todo-list">
            ${todos.map((todo, idx) => html`
                <${TodoItem}
                    key=${todo.id}
                    todo=${todo}
                    onToggle=${onToggle}
                    onDelete=${onDelete}
                    draggable=${canDrag}
                    onDragStart=${() => handleDragStart(idx)}
                    onDragOver=${(e) => handleDragOver(e, idx)}
                    onDragLeave=${handleDragLeave}
                    onDrop=${(e) => handleDrop(e, idx)}
                    onDragEnd=${handleDragEnd}
                    isDragging=${dragIdx === idx}
                    isOver=${overIdx === idx}
                />
            `)}
        </ul>
    `;
}