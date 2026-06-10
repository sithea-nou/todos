import { html } from '../preact.js';

export function Toast({ message }) {
    if (!message) return null;
    return html`<div class="toast error">${message}</div>`;
}