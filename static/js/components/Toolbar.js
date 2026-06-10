import { html } from '../preact.js';

export function Toolbar({ filter, onFilterChange, completedCount, onClearCompleted, viewMode, onViewModeChange }) {
    const filters = [
        { key: 'all', label: 'All' },
        { key: 'active', label: 'Active' },
        { key: 'completed', label: 'Completed' },
    ];

    return html`
        <div class="toolbar">
            <div class="toolbar-left">
                <div class="view-toggle">
                    <button
                        class=${`view-btn${viewMode === 'list' ? ' active' : ''}`}
                        onClick=${() => onViewModeChange('list')}
                        title="List view"
                    >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>
                    </button>
                    <button
                        class=${`view-btn${viewMode === 'calendar' ? ' active' : ''}`}
                        onClick=${() => onViewModeChange('calendar')}
                        title="Calendar view"
                    >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
                    </button>
                </div>
                <div class="filter-pills">
                    ${filters.map(f => html`
                        <button
                            key=${f.key}
                            class=${`filter-pill${filter === f.key ? ' active' : ''}`}
                            onClick=${() => onFilterChange(f.key)}
                        >${f.label}</button>
                    `)}
                </div>
            </div>
            <button
                class="clear-btn"
                disabled=${completedCount === 0}
                onClick=${onClearCompleted}
            >Clear completed</button>
        </div>
    `;
}