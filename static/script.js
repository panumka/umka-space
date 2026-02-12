// відкриття/закриття модалки
document.addEventListener("DOMContentLoaded", () => {
    const open = document.getElementById("openPlatformModal");
    const modal = document.getElementById("platformModal");
  
    if (!open || !modal) return;
  
    const closeEls = modal.querySelectorAll("[data-close]");
  
    const show = () => {
      modal.classList.add("show");
      document.body.classList.add("modal-open");
      document.documentElement.classList.add("modal-open");
      if (typeof hideFooter === 'function') hideFooter();
    };

    const hide = () => {
      modal.classList.remove("show");
      document.body.classList.remove("modal-open");
      document.documentElement.classList.remove("modal-open");
      if (typeof showFooter === 'function') showFooter();
    };
  
    open.addEventListener("click", show);
    closeEls.forEach(el => el.addEventListener("click", hide));
    modal.addEventListener("click", e => {
      if (e.target === modal) hide();
    });
  });

// --- UmkA: Open full blog post in modal from /post_json/<id>
(function(){
  // prevent double init
  if (window.__umkaPostModalBound) return; 
  window.__umkaPostModalBound = true;

  function closeModal(overlay){
    if(!overlay) return;
    overlay.remove();
    document.body.style.overflow = '';
    document.documentElement.style.overflow = '';
    document.body.classList.remove('modal-open');
    document.documentElement.classList.remove('modal-open');
    if (typeof showFooter === 'function') showFooter();
  }

  function openModalWithHTML(title, date, html){
    const overlay = document.createElement('div');
    overlay.className = 'umka-modal-overlay';
    overlay.innerHTML = `
      <style>
        .umka-modal-overlay{position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.65);display:flex;align-items:center;justify-content:center;padding:24px}
        .umka-modal{max-width:900px;width:100%;max-height:90vh;overflow:auto;background:#111;border:1px solid #333;border-radius:16px;box-shadow:0 10px 40px rgba(0,0,0,.5)}
        .umka-modal header{position:sticky;top:0;background:#111;padding:16px 20px;border-bottom:1px solid #222}
        .umka-modal header h2{margin:0;font-size:20px}
        .umka-modal header .x{float:right;cursor:pointer;font-size:20px;opacity:.8}
        .umka-modal .body{padding:20px;color:#ddd}
        .umka-modal .body a{color:#9ecbff;text-decoration:none}
        .umka-modal .body a:hover{text-decoration:underline}
        .umka-modal .body h1,.umka-modal .body h2,.umka-modal .body h3{margin:14px 0 8px}
        .umka-modal .body figure{margin:0}
        .umka-modal .body img{max-width:100%;height:auto;border-radius:12px}
        .umka-modal .body p{line-height:1.6}
        .umka-modal .body ul, .umka-modal .body ol{padding-left:20px}
        .umka-modal .body blockquote{margin:12px 0;padding:8px 12px;border-left:3px solid #444;opacity:.9}
      </style>
      <div class="umka-modal" role="dialog" aria-modal="true">
        <header>
          <span class="x" aria-label="Close">×</span>
          <h2>${title || ''}</h2>
          ${date ? `<div style="opacity:.7;font-size:13px;margin-top:4px">${date}</div>`: ''}
        </header>
        <div class="body">${html || ''}</div>
      </div>`;

    // close handlers
    overlay.addEventListener('click', (e)=>{
      if(e.target === overlay || e.target.classList.contains('x')) closeModal(overlay);
    });
    document.addEventListener('keydown', function onEsc(ev){
      if(ev.key === 'Escape'){ closeModal(overlay); document.removeEventListener('keydown', onEsc);} 
    });

    // mount
    const root = document.getElementById('post-modal-root') || document.body;
    root.appendChild(overlay);
    document.body.style.overflow = 'hidden';
    document.documentElement.style.overflow = 'hidden';
    document.body.classList.add('modal-open');
    document.documentElement.classList.add('modal-open');
    if (typeof hideFooter === 'function') hideFooter();
  }

  // delegate clicks from cards/links that carry a page id
  let __umkaLoadingOverlay = null;
  function showLoading(){
    if(__umkaLoadingOverlay) return;
    __umkaLoadingOverlay = document.createElement('div');
    __umkaLoadingOverlay.className = 'umka-modal-overlay';
    __umkaLoadingOverlay.innerHTML = `
      <style>
        .umka-modal-overlay{position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.65);display:flex;align-items:center;justify-content:center;padding:24px}
        .umka-spinner{padding:14px 18px;border-radius:10px;background:#111;border:1px solid #333;color:#aaa;font-size:14px}
      </style>
      <div class="umka-spinner">Завантаження…</div>`;
    (document.getElementById('post-modal-root')||document.body).appendChild(__umkaLoadingOverlay);
  }
  function hideLoading(){
    if(__umkaLoadingOverlay){
      __umkaLoadingOverlay.remove();
      __umkaLoadingOverlay = null;
    }
  }

  document.addEventListener('click', async (e)=>{
    const trigger = e.target.closest('a.post-open, .post-card, [data-post-id]');
    if (trigger && trigger.closest('.release-card')) return;
    if(!trigger) return;
    const id = trigger.getAttribute('data-id') || trigger.getAttribute('data-post-id');
    if(!id) return;
    e.preventDefault();
    try{
      showLoading();
      const r = await fetch(`/post_json/${id}`);
      const j = await r.json();
      if(j && j.ok){
        openModalWithHTML(j.title, j.date, j.html);
      }
    }catch(err){
      console.error('post_json error', err);
    }finally{
      hideLoading();
    }
  });
})();

// --- Stream Modal (слухати на майданчиках) — FETCH FROM SERVER -----------------
function slugifyReleaseTitle(title) {
  if (!title) return "";
  const map = {
    а: "a", б: "b", в: "v", г: "h", ґ: "g", д: "d", е: "e", є: "ye",
    ж: "zh", з: "z", и: "y", і: "i", ї: "yi", й: "y", к: "k", л: "l",
    м: "m", н: "n", о: "o", п: "p", р: "r", с: "s", т: "t", у: "u",
    ф: "f", х: "kh", ц: "ts", ч: "ch", ш: "sh", щ: "shch", ь: "",
    ю: "yu", я: "ya",
  };
  let out = "";
  for (const ch of String(title).trim()) {
    const lower = ch.toLowerCase();
    if (map[lower] !== undefined) {
      out += map[lower];
    } else if (/[a-z0-9]/i.test(ch)) {
      out += lower;
    } else {
      out += "-";
    }
  }
  return out
    .replace(/-+/g, "-")
    .replace(/^-+|-+$/g, "")
    .toLowerCase();
}

function getReleaseFromHash() {
  const hash = (location.hash || "").replace(/^#/, "");
  if (!hash) return null;
  const m = hash.match(/^release=([^&]+)/);
  if (m) return decodeURIComponent(m[1]);
  return decodeURIComponent(hash);
}

function setReleaseHashFromTitle(title, fallbackId) {
  const slug = slugifyReleaseTitle(title) || fallbackId || "";
  if (!slug) return;
  history.pushState(null, "", `#${encodeURIComponent(slug)}`);
}

function clearReleaseHash() {
  history.pushState(null, "", location.pathname + location.search);
}

async function openReleaseModal(pageId, title) {
  if (!pageId) return;

  // ensure root exists
  const root = document.getElementById("stream-modal-root") || (() => {
    const el = document.createElement("div");
    el.id = "stream-modal-root";
    document.body.appendChild(el);
    return el;
  })();

  // scroll lock helpers
  const lockScroll = () => {
    document.body.dataset.scrollLocked = '1';
    document.body.style.overflow = 'hidden';
    document.documentElement.style.overflow = 'hidden';
    document.body.classList.add('modal-open');
    document.documentElement.classList.add('modal-open');
  };
  const unlockScroll = () => {
    delete document.body.dataset.scrollLocked;
    document.body.style.overflow = '';
    document.documentElement.style.overflow = '';
    document.body.classList.remove('modal-open');
    document.documentElement.classList.remove('modal-open');
  };

  setReleaseHashFromTitle(title, pageId);

  // loading state
  root.innerHTML = `
    <div class="modal show" role="dialog" aria-modal="true">
      <div class="modal-backdrop" data-close></div>
      <div class="modal-dialog modal-loading">
        <div style="opacity:.8">Завантаження…</div>
      </div>
    </div>
  `;
  lockScroll();
  if (typeof hideFooter === 'function') hideFooter();

  const RELEASE_MODAL_CACHE = (window.__umkaReleaseModalCache = window.__umkaReleaseModalCache || {});

  function escHtml(s){
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }
  function escAttr(s){
    return escHtml(s).replace(/`/g, "&#96;");
  }
  function fromCardPayload(cardEl){
    if (!cardEl) return null;
    let links = [];
    try {
      const raw = cardEl.dataset.links;
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) links = parsed;
      }
    } catch (e) {}
    const coverB64 = (cardEl.dataset.coverb64 || "").trim();
    const modalTitle = (cardEl.dataset.title || title || "").trim() || "Без назви";
    if (!links.length && !coverB64) return null;

    const coverHtml = coverB64
      ? `<div class="rm-cover"><img src="/proxy_img?b=${encodeURIComponent(coverB64)}&w=800&q=80" alt="${escAttr(modalTitle)}" loading="lazy" decoding="async"></div>`
      : "";
    const linksHtml = links.length
      ? links.map((l) => {
          const label = escHtml(l && (l.label || l.name || ""));
          const url = String(l && (l.url || l.href || "") || "").trim();
          if (!label || !url) return "";
          return `<a class="btn btn-sm link-btn platform-${escAttr(l.key || "")}" href="${escAttr(url)}" target="_blank" rel="noopener">${label}</a>`;
        }).join("")
      : '<div class="muted">Посилання відсутні.</div>';
    const shareBtn = (
      '<button type="button" class="rm-share" data-share aria-label="Поділитися">'
      + '<svg viewBox="0 0 24 24" aria-hidden="true">'
      + '<path d="M12 3l4 4m-4-4l-4 4m4-4v11" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
      + '<path d="M5 10v9a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-9" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
      + '</svg>'
      + '<span class="rm-share-label" aria-live="polite">Скопійовано</span>'
      + '</button>'
    );
    const html = (
      '<div class="release-modal">'
      + '  <div class="rm-grid">'
      + `    ${coverHtml}`
      + '    <div class="rm-links-list">'
      + `      ${linksHtml}`
      + '    </div>'
      + `    <div class="rm-title-under">${escHtml(modalTitle)}</div>`
      + `    ${shareBtn}`
      + '  </div>'
      + '</div>'
    );
    return { ok: true, title: modalTitle, html, links };
  }

  const cardForPayload = document.querySelector(`.release-card[data-page-id="${pageId}"], .release-card[data-id="${pageId}"]`);

  try {
    let j = RELEASE_MODAL_CACHE[pageId] || fromCardPayload(cardForPayload) || null;
    if (!j) {
      const r = await fetch(`/release_json/${pageId}`);
      j = await r.json();
    }
    if (j && j.ok) RELEASE_MODAL_CACHE[pageId] = j;
    if (!j || !j.ok) throw new Error("invalid response");

    root.innerHTML = `
      <div class="modal show" role="dialog" aria-modal="true">
        <div class="modal-backdrop" data-close></div>
        <div class="modal-dialog">
          <div class="stream-modal">
            ${j.html || "<div class='modal-body'><em>Порожньо</em></div>"}
          </div>
        </div>
      </div>
    `;

    // close/backdrop handlers
    const modalEl = root.querySelector('.modal');
    const dialogEl = root.querySelector('.modal-dialog');
    const backdropEl = root.querySelector('.modal-backdrop');
    const closeEls = root.querySelectorAll('[data-close]');
    const shareBtn = root.querySelector('[data-share]');
    function closeStreamModal(){
      const modalShellEl = root.querySelector('.modal');
      if (modalShellEl) modalShellEl.style.removeProperty('--modal-bg');
      root.innerHTML = '';
      unlockScroll();
      clearReleaseHash();
      if (typeof showFooter === 'function') showFooter();
    }
    backdropEl && backdropEl.addEventListener('click', closeStreamModal);
    closeEls.forEach(el => el.addEventListener('click', closeStreamModal));
    modalEl && modalEl.addEventListener('click', (ev)=>{
      if (!dialogEl) return;
      if (!dialogEl.contains(ev.target)) closeStreamModal();
    });
    document.addEventListener('keydown', function onEsc(ev){
      if (ev.key === 'Escape'){ closeStreamModal(); document.removeEventListener('keydown', onEsc); }
    });
    if (shareBtn) {
      shareBtn.addEventListener('click', async (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        const url = location.href;
        let ok = false;
        try {
          if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(url);
            ok = true;
          }
        } catch (err) {
          ok = false;
        }
        if (!ok) {
          try {
            window.prompt("Посилання для копіювання:", url);
          } catch (err) {
            // no-op
          }
        }
        shareBtn.classList.add('copied');
        setTimeout(() => shareBtn.classList.remove('copied'), 1500);
      });
    }

    // enforce compact cover size + two-column layout regardless of server HTML
    const dialog = root.querySelector(".modal-dialog");
    if (dialog) {
      // If server didn't wrap, try to build a minimal wrapper around first image + the rest
      const streamRoot = dialog.querySelector(".stream-modal");
      if (streamRoot) {
        // try to find a cover <img>
        let coverImg = streamRoot.querySelector("img");
        // set blurred backdrop image from cover
        const backdropEl = root.querySelector('.modal-backdrop');
        let coverUrl = null;
        if (coverImg && coverImg.getAttribute('src')) {
          coverUrl = coverImg.getAttribute('src');
        } else {
          const og = streamRoot.querySelector('meta[property="og:image"]');
          if (og) coverUrl = og.getAttribute('content');
        }
        if (backdropEl && coverUrl) {
          backdropEl.style.setProperty('--cover', `url("${coverUrl}")`);
        }
        // set blurred modal background (used by #stream-modal-root .modal::before)
        const modalShellEl = root.querySelector('.modal');
        if (modalShellEl && coverUrl) {
          modalShellEl.style.setProperty('--modal-bg', `url("${coverUrl}")`);
        }
        // try to find links container by common selectors or create one
        let linksBox = streamRoot.querySelector(".rm-links, .links, .platforms, .platform-links");
        if (!streamRoot.querySelector(".release-wrap") && !streamRoot.querySelector(".rm-grid")) {
          const wrap = document.createElement("div");
          wrap.className = "release-wrap";
          // move cover + links into wrap if they exist
          if (coverImg) wrap.appendChild(coverImg);
          if (linksBox) {
            wrap.appendChild(linksBox);
          } else {
            // keep original HTML but still constrain image
            const rest = document.createElement("div");
            rest.className = "links";
            // move all anchors except those inside the image link (if any)
            streamRoot.querySelectorAll("a").forEach(a => {
              if (!a.contains(coverImg) && !coverImg?.contains(a)) {
                rest.appendChild(a);
              }
            });
            if (rest.childElementCount) wrap.appendChild(rest);
          }
          // only attach if we actually moved something
          if (wrap.childElementCount) {
            // move leftover nodes to the end
            while (streamRoot.firstChild) {
              const n = streamRoot.firstChild;
              streamRoot.removeChild(n);
              // avoid duplicating nodes we already placed
              if (n !== wrap && n !== coverImg && n !== linksBox) {
                // skip, we will re-append wrap only
              }
            }
            streamRoot.appendChild(wrap);
          }
        }

        // --- normalize platform links into consistent rows --------------------
        const linksContainer =
          streamRoot.querySelector(".rm-links-list") ||
          streamRoot.querySelector(".links") ||
          streamRoot.querySelector(".platforms") ||
          streamRoot.querySelector(".platform-links");

        if (linksContainer) {
          // --- brand icons (inline SVG) -------------------------------------
          const ICON_SVGS = {
            'spotify': `
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <circle cx="12" cy="12" r="12" fill="#1DB954"/>
                <path d="M17.3 15.5a.9.9 0 0 1-1.24.32c-3.41-2.09-7.7-.84-7.74-.83a.9.9 0 1 1-.52-1.72c.19-.06 4.89-1.41 8.76.92a.9.9 0 0 1 .34 1.31zM18.27 12.9a1 1 0 0 1-1.38.36c-3.9-2.36-9.84-1.03-9.9-1.02a1 1 0 0 1-.46-1.94c.26-.06 6.5-1.49 11.06 1.26a1 1 0 0 1 .68 1.34zM18.37 10.17c-4.38-2.6-11.08-1.46-11.36-1.41a1.1 1.1 0 0 1-.39-2.17c.32-.06 7.96-1.31 12.97 1.63a1.1 1.1 0 1 1-1.22 1.95z" fill="#0B0B0B"/>
              </svg>`,
            'apple music': `
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <circle cx="12" cy="12" r="12" fill="#FA2D48"/>
                <path d="M15.5 6.5v8.2a2.8 2.8 0 1 1-1.6-2.6V8.1l-4 .9v6.7a2.8 2.8 0 1 1-1.6-2.6V7.5l7.2-1z" fill="#fff"/>
              </svg>`,
            'itunes': `
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <circle cx="12" cy="12" r="12" fill="#BF5AF2"/>
                <path d="M16.5 6.7v7.9a2.7 2.7 0 1 1-1.6-2.5V8.3l-4 .9v6.4a2.7 2.7 0 1 1-1.6-2.5V7.7l7.2-1z" fill="#fff"/>
              </svg>`,
            'youtube music': `
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <circle cx="12" cy="12" r="12" fill="#FF0033"/>
                <polygon points="10,8 16,12 10,16" fill="#fff"/>
                <circle cx="12" cy="12" r="5.5" fill="none" stroke="#fff" stroke-width="2"/>
              </svg>`,
            'youtube': `
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <rect x="1" y="5" width="22" height="14" rx="4" fill="#FF0033"/>
                <polygon points="10,9 16,12 10,15" fill="#fff"/>
              </svg>`,
           'deezer': `
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <rect x="2" y="14" width="4" height="4" fill="#22D1EE"/>
    <rect x="7" y="12" width="4" height="6" fill="#7C4DFF"/>
    <rect x="12" y="10" width="4" height="8" fill="#FFAA00"/>
    <rect x="17" y="8"  width="4" height="10" fill="#00E676"/>
  </svg>`,
'bandcamp': `
  <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <path fill="#629AA9" d="M3 17h8.7L21 7H12.3L3 17z"/>
  </svg>`,
'soundcloud': `
  <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <path fill="#FF7700" d="M18.5 10.2c-.5 0-1 .1-1.4.3-.3-2.1-2.1-3.7-4.2-3.7-1 0-1.9.3-2.6.9-.2.2-.3.4-.3.7v6.9h8.5c1.6 0 2.9-1.3 2.9-2.9s-1.3-2.9-2.9-2.9zM2.9 11.3H4V15H2.9v-3.7zm1.9-1H6v5.7H4.8V10.3zm1.9-.6H8v6.3H6.7V9.7zm1.9-.6h1.2v6.9H8.6V9.1zm1.9-.4h1.2v7.3h-1.2V8.7z"/>
  </svg>`
          };
          function keyFromLabel(label){
            return String(label || '').trim().toLowerCase();
          }

          // --- helpers -------------------------------------------------------
          function normalizeUrl(u){
            if (!u) return "";
            let s = String(u).trim();
            if (!s) return "";
            if (s.startsWith("//")) return "https:" + s;
            if (!/^https?:\/\//i.test(s)) {
              if (/^[\w.-]+\.[\w.-]+(\/.*)?$/.test(s)) return "https://" + s;
            }
            return s;
          }
          function isProbablyUrl(u){
            if (!u) return false;
            const s = String(u).trim();
            if (!s) return false;
            if (/^https?:\/\//i.test(s)) return true;
            if (s.startsWith("//")) return true;
            return /^[\w.-]+\.[\w.-]+(\/.*)?$/.test(s);
          }

          // renderer that keeps label EXACTLY as provided from Notion
          function renderRow(label, url, icon){
            const a = document.createElement("a");
            a.href = url; a.target = "_blank"; a.rel = "noopener";
            a.className = "platform-row";
            const k = keyFromLabel(label);
            const svg = ICON_SVGS[k] || '';
            const iconHTML = svg
              ? `<span class="platform-icon" aria-hidden="true">${svg}</span>`
              : (icon ? `<img class="platform-icon-img" src="${icon}" alt="${label}" loading="lazy" decoding="async">` : "");
            a.innerHTML = `
              ${iconHTML}
              <span class="platform-name">${label}</span>
            `;
            linksContainer.appendChild(a);
          }

          // Clear and render strictly in the order that comes from backend/Notion
          linksContainer.innerHTML = "";

          let rendered = 0;

          // 1) Preferred: array j.links with explicit { label/name, url/href }
          if (Array.isArray(j.links) && j.links.length){
            j.links.forEach(it => {
              const url   = normalizeUrl(it.url || it.href);
              const label = (it.label || it.name || "").toString().trim();
              if (!label || !isProbablyUrl(url)) return;
              renderRow(label, url, (it.icon || it.favicon));
              rendered++;
            });
          }

          // 2) Fallback: object maps from backend (properties/props/platforms)
          if (!rendered){
            const maps = j.properties || j.props || j.platforms;
            if (maps && typeof maps === 'object'){
              // Build a normalized label->url map while preserving insertion order
              const entries = Object.entries(maps).map(([label, url]) => {
                return [String(label).trim(), normalizeUrl(url)];
              }).filter(([L, U]) => L && isProbablyUrl(U));

              // Preferred order to match Notion columns exactly
              const preferredOrder = [
                'Spotify',
                'Apple Music',
                'YouTube Music',
                'Deezer',
                'iTunes',
                'YouTube'
              ].map(s => s.toLowerCase());

              // Helper to do case-insensitive pick
              const consumed = new Set();
              function pickByName(nameLc){
                for (let i = 0; i < entries.length; i++){
                  if (consumed.has(i)) continue;
                  const [L, U] = entries[i];
                  if (L.toLowerCase() === nameLc){
                    renderRow(L, U);
                    consumed.add(i);
                    return true;
                  }
                }
                return false;
              }

              // 1) Render in preferred order (only those that exist)
              preferredOrder.forEach(nLc => pickByName(nLc));

              // 2) Render any remaining platforms in their original order
              for (let i = 0; i < entries.length; i++){
                if (consumed.has(i)) continue;
                const [L, U] = entries[i];
                renderRow(L, U);
              }

              rendered += entries.length;
            }
          }

          // 3) Last resort: parse anchors already present in HTML; keep their text as label
          if (!rendered){
            streamRoot.querySelectorAll("a[href]").forEach(a => {
              const url = normalizeUrl(a.getAttribute("href"));
              const label = (a.textContent || "").trim();
              if (!label || !isProbablyUrl(url)) return;
              renderRow(label, url);
              rendered++;
            });
          }
          // If still nothing, leave empty
        }
        // --- /normalize platform links ---------------------------------------
      }
    }
  } catch (err) {
    console.error("release_json error", err);
    root.innerHTML = `
      <div class="modal show" role="dialog" aria-modal="true">
        <div class="modal-backdrop" data-close></div>
        <div class="modal-dialog">
          <div class="modal-header">
            <strong>Помилка</strong>
            <button type="button" data-close aria-label="Закрити">×</button>
          </div>
          <div class="modal-body"><p>Не вдалось завантажити реліз.</p></div>
        </div>
      </div>
    `;
    const cleanup = () => {
      root.innerHTML = "";
      clearReleaseHash();
      if (typeof showFooter === 'function') showFooter();
    };
    root.querySelectorAll('[data-close]').forEach(el => el.addEventListener('click', cleanup));
  }
}

document.addEventListener("click", (e) => {
  const card = e.target.closest(".release-card");
  if (!card) return;
  e.preventDefault();
  e.stopPropagation();
  const pageId = card.dataset.id || card.dataset.pageId || card.getAttribute("data-page-id");
  const title = card.dataset.title || "";
  openReleaseModal(pageId, title);
});

window.addEventListener("DOMContentLoaded", () => {
  const bodyRid = document.body && document.body.dataset ? document.body.dataset.releaseId : "";
  if (bodyRid) {
    const card = document.querySelector(`.release-card[data-page-id="${bodyRid}"], .release-card[data-id="${bodyRid}"]`);
    const title = card ? (card.dataset.title || "") : "";
    openReleaseModal(bodyRid, title);
    return;
  }
  const slug = getReleaseFromHash();
  if (!slug) return;
  const cards = Array.from(document.querySelectorAll(".release-card"));
  for (const card of cards) {
    const title = card.dataset.title || "";
    const cardSlug = slugifyReleaseTitle(title);
    if (cardSlug && cardSlug === slug) {
      const pageId = card.dataset.id || card.dataset.pageId || card.getAttribute("data-page-id");
      openReleaseModal(pageId, title);
      return;
    }
  }
  // fallback: treat hash as a direct page id
  openReleaseModal(slug, "");
});

// Allow closing modal by clicking outside the dialog or on backdrop
document.addEventListener('click', (e) => {
  const modal = document.querySelector('.modal');
  if (!modal) return;
  const dialog = modal.querySelector('.modal-dialog');
  if (!dialog) return;
  const clickedOutside = !dialog.contains(e.target);
  const clickedBackdrop = e.target.classList.contains('modal-backdrop');
  if (clickedOutside || clickedBackdrop) {
    const root = document.getElementById('stream-modal-root') || document.body;
    if (root && root.contains(modal)) root.innerHTML = '';
    if (document.body.dataset.scrollLocked) document.body.style.overflow = '';
    document.body.classList.remove('modal-open');
    document.documentElement.classList.remove('modal-open');
    if (typeof showFooter === 'function') showFooter();
    delete document.body.dataset.scrollLocked;
  }
});
// --- /Stream Modal FETCH ------------------------------------------------------
// === Footer hide/show on modal open/close ===
const FOOTER_SELECTOR = 'footer.site-footer, .site-footer, footer';

function getFooterEl() {
  return document.querySelector(FOOTER_SELECTOR);
}

function hideFooter() {
  const footer = getFooterEl();
  if (footer) footer.style.display = 'none';
}

function showFooter() {
  const footer = getFooterEl();
  if (footer) footer.style.display = '';
}

// (footer hide/show logic simplified and event/observer-based logic removed)
