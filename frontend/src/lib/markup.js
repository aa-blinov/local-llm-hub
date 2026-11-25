// Formatting and answer rendering helpers, kept identical to the old panel.

// Escape text that ends up inside the answer markup ({@html}).
export const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

export const gib = (v) => (v == null ? '—' : v.toFixed(2) + ' GiB');
export const fmt = (v, u = '') => (v == null ? '—' : v + u);

// Code blocks go into a box; the rest gets simple formatting (headings, bold,
// lists). Everything is escaped before it enters the markup.
export function renderAnswer(text) {
  const parts = String(text).split('```');
  return parts.map((part, i) => {
    if (i % 2 === 1) {
      const body = part.replace(/^[a-zA-Z0-9+#.-]*\n/, ''); // drop the language name on the first line
      return `<pre class="code"><code>${esc(body.replace(/\n$/, ''))}</code></pre>`;
    }
    return renderPlain(part);
  }).join('');
}

function renderPlain(text) {
  const lines = esc(text).split('\n').map((line) => {
    let l = line.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
    const h = l.match(/^#{1,6}\s+(.*)$/);
    if (h) return `<h4>${h[1].replace(/\*\*/g, '')}</h4>`;
    const li = l.match(/^\s*[-*]\s+(.*)$/);
    if (li) return `<li>• ${li[1]}</li>`;
    return l.trim() ? `<p>${l}</p>` : '';
  });
  return lines.join('');
}
