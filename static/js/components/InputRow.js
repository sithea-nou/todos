import { html, useState } from '../preact.js';

export function InputRow({ onAdd }) {
    const [value, setValue] = useState('');
    const [priority, setPriority] = useState(0);
    const [dueDate, setDueDate] = useState('');

    const handleSubmit = (e) => {
        e.preventDefault();
        if (!value.trim()) return;
        onAdd({
            title: value.trim(),
            priority: priority || 0,
            due_date: dueDate || null,
        });
        setValue('');
        setPriority(0);
        setDueDate('');
    };

    return html`
        <form class="input-row" onSubmit=${handleSubmit}>
            <div class="input-main">
                <input
                    type="text"
                    value=${value}
                    onInput=${e => setValue(e.target.value)}
                    placeholder="What needs to be done?"
                    autofocus
                />
                <button class="add-btn" type="submit">Add</button>
            </div>
            <div class="input-options">
                <select class="priority-select" value=${priority} onChange=${e => setPriority(Number(e.target.value))}>
                    <option value=${0}>Priority</option>
                    <option value=${1}>P3 \u2014 Low</option>
                    <option value=${2}>P2 \u2014 Medium</option>
                    <option value=${3}>P1 \u2014 High</option>
                </select>
                <input
                    type="date"
                    class="date-input"
                    value=${dueDate}
                    onChange=${e => setDueDate(e.target.value)}
                />
            </div>
        </form>
    `;
}