// Chinese and English. The Chinese text is the key, as in gettext: t('打开 {name}', { name }) gives the English
// from i18n/en.json when the page is English, else the Chinese itself (also for any text with no translation).
// The server (stocking/i18n.py) reads the same catalog and serves the page with <html lang> set to the language.
import EN from './i18n/en.json' with { type: 'json' };

export const LANG = document.documentElement.lang.startsWith('en') ? 'en' : 'zh';

export function t(text, params) {
  let s = LANG === 'en' && Object.hasOwn(EN, text) ? EN[text] : text;
  if (params) s = s.replace(/\{(\w+)\}/g, (m, k) => (k in params ? String(params[k]) : m));
  return s;
}

const ATTRS = ['title', 'aria-label', 'data-tip', 'aria-description', 'aria-valuetext'];

// The page's own text, as written in index.html: every text node and labelling attribute whose (trimmed) text is
// in the catalog. Elements marked translate="no" (the language switch, file names) are left as they are.
export function translatePage() {
  if (LANG !== 'zh') {
    document.title = t(document.title);
    const skip = (node) => node.parentElement && node.parentElement.closest('[translate="no"]');
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      const s = n.nodeValue, k = s.trim();
      if (k && Object.hasOwn(EN, k) && !skip(n)) n.nodeValue = s.replace(k, EN[k]);
    }
    for (const el of document.body.querySelectorAll('*')) {
      if (el.closest('[translate="no"]')) continue;
      for (const a of ATTRS) {
        const v = el.getAttribute(a);
        if (v && Object.hasOwn(EN, v)) el.setAttribute(a, EN[v]);
      }
    }
  }
  document.documentElement.classList.add('i18n-done');
}
