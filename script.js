// ── Scroll reveal ──
const observer = new IntersectionObserver((entries) => {
  entries.forEach(e => {
    if (e.isIntersecting) {
      e.target.classList.add('visible');
      observer.unobserve(e.target);
    }
  });
}, { threshold: 0.1, rootMargin: '0px 0px -40px 0px' });

document.querySelectorAll('.reveal').forEach(el => observer.observe(el));

// ── Copy to clipboard ──
function copyCmd(btn, text) {
  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.textContent;
    btn.textContent = 'copied!';
    btn.style.background = 'var(--green)';
    btn.style.color = '#fff';
    setTimeout(() => {
      btn.textContent = orig;
      btn.style.background = '';
      btn.style.color = '';
    }, 2000);
  });
}

// ── Changelog nav ──
document.querySelectorAll('.cl-version-btn').forEach((btn, i) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.cl-version-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const entries = document.querySelectorAll('.changelog-entry');
    if (entries[i]) {
      entries[i].scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
});

// ── Screenshot tabs ──
const ssTabs = document.querySelectorAll('.ss-tab');
const ssPanels = document.querySelectorAll('.ss-panel');

ssTabs.forEach(tab => {
  tab.addEventListener('click', () => {
    ssTabs.forEach(t => t.classList.remove('active'));
    ssPanels.forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    const target = document.getElementById('ss-' + tab.dataset.panel);
    if (target) target.classList.add('active');
  });
});

// ── Terminal typewriter on load ──
const cursor = document.querySelector('.t-cursor');
let visible = true;
setInterval(() => {
  cursor.style.opacity = (visible = !visible) ? '1' : '0';
}, 530);

// ── Ko-fi widget — render into nav slot ──
// Note: kofiwidget2 must be loaded via CDN script in HTML before this script
if (typeof kofiwidget2 !== 'undefined') {
  kofiwidget2.init('Support me on Ko-fi', '#f76e25', 'R6R11Z1NDP');
  const navKofi = document.getElementById('kofi-nav');
  if (navKofi) navKofi.innerHTML = kofiwidget2.getHTML();
}
