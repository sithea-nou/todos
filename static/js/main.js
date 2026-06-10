import { render, html } from './preact.js';
import { App } from './app.js';

render(html`<${App} />`, document.getElementById('app'));