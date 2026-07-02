import { html } from '../preact.js';
import { priorityBadge, formatDate, parseTags } from '../utils.js';

export function TrashView({ trash, onRestore, onPurge, onEmpty }) {
    if (trash.length === 0) {
        return html`
            <div class="empty-state">
                <div class="icon">\ud83d\uddd1</div>
                <p>Trash is empty.</p>
            </div>
        `;
    }
    return html`
        <div class="trash-view">
            <div class="trash-header">
                <span>${trash.length} deleted todo${trash.length !== 1 ? 's' : ''}</span>
                <button class="empty-trash-btn" onClick=${onEmpty}>Empty trash</button>
            </div>
            <ul class="todo-list">
                ${trash.map(t => {
                    const b = priorityBadge(t.priority);
                    const tags = parseTags(t.tags);
                    return html`
                        <li key=${t.id} class="todo-item deleted">
                            <div class="todo-content">
                                <div class="todo-title">${t.title}</div>
                                <div class="todo-meta">
                                    ${b && html`<span class=${`priority-badge ${b.cls}`}>${b.label}</span>`}
                                    ${t.due_date && html`<span class="due-date">${formatDate(t.due_date)}</span>`}
                                    ${tags.map(tag => html`<span key=${tag} class="tag-chip">${tag}</span>`)}
                                    ${t.deleted_at && html`<span class="deleted-ago">deleted ${new Date(t.deleted_at).toLocaleDateString()}</span>`}
                                </div>
                            </div>
                            <button class="restore-btn" onClick=${() => onRestore(t.id)} title="Restore">Restore</button>
                            <button class="delete-btn" style="opacity:1" onClick=${() => onPurge(t.id)} title="Delete forever">\u00d7</button>
                        </li>
                    `;
                })}
            </ul>
        </div>
    `;
}