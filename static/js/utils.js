export function escapeHtml(text) {
    const d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML;
}

export function formatDate(iso) {
    if (!iso) return '';
    const d = new Date(iso + 'T00:00:00');
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return `${months[d.getMonth()]} ${d.getDate()}`;
}

export function isOverdue(dateStr) {
    if (!dateStr) return false;
    const d = new Date(dateStr + 'T23:59:59');
    return d < new Date();
}

export function priorityBadge(p) {
    if (!p || p === 0) return null;
    if (p >= 3) return { label: 'P1', cls: 'p1' };
    if (p === 2) return { label: 'P2', cls: 'p2' };
    return { label: 'P3', cls: 'p3' };
}

export function getWeekDates(offset) {
    const now = new Date();
    const day = now.getDay();
    const mondayOffset = day === 0 ? -6 : 1 - day;
    const monday = new Date(now.getFullYear(), now.getMonth(), now.getDate() + mondayOffset + offset * 7);
    const dates = [];
    for (let i = 0; i < 7; i++) {
        const d = new Date(monday);
        d.setDate(monday.getDate() + i);
        dates.push(d);
    }
    return dates;
}

export function formatWeekRange(dates) {
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    const s = dates[0], e = dates[6];
    if (s.getMonth() === e.getMonth()) {
        return `${months[s.getMonth()]} ${s.getDate()} \u2013 ${e.getDate()}, ${s.getFullYear()}`;
    }
    return `${months[s.getMonth()]} ${s.getDate()} \u2013 ${months[e.getMonth()]} ${e.getDate()}, ${s.getFullYear()}`;
}

export function toDateStr(d) {
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}

export function normalizeDate(val) {
    if (!val) return null;
    return val.slice(0, 10);
}

export const DAY_NAMES = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];