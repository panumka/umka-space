// відкриття/закриття модалки
document.addEventListener("DOMContentLoaded", () => {
    const open = document.getElementById("openPlatformModal");
    const modal = document.getElementById("platformModal");
  
    if (!open || !modal) return;
  
    const closeEls = modal.querySelectorAll("[data-close]");
  
    const show = () => {
      modal.classList.add("show");
    };
  
    const hide = () => {
      modal.classList.remove("show");
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
document.addEventListener("click", async (e) => {
  const card = e.target.closest(".release-card");
  if (!card) return;

  e.preventDefault();
  e.stopPropagation();

  const pageId = card.dataset.id || card.dataset.pageId || card.getAttribute("data-page-id");
  if (!pageId) return;

  // ensure root exists
  const root = document.getElementById("stream-modal-root") || (() => {
    const el = document.createElement("div");
    el.id = "stream-modal-root";
    document.body.appendChild(el);
    return el;
  })();

  // loading state
  root.innerHTML = `
    <div class="modal" role="dialog" aria-modal="true">
      <div class="modal-backdrop" data-close></div>
      <div class="modal-dialog" style="display:flex;align-items:center;justify-content:center;min-width:320px;min-height:200px;">
        <div style="opacity:.8">Завантаження…</div>
      </div>
    </div>
  `;

  try {
    const r = await fetch(`/release_json/${pageId}`);
    const j = await r.json();
    if (!j || !j.ok) throw new Error("invalid response");

    root.innerHTML = `
      <div class="modal" role="dialog" aria-modal="true">
        <div class="modal-backdrop" data-close></div>
        <div class="modal-dialog">
          <div class="stream-modal">
            ${j.html || "<div class='modal-body'><em>Порожньо</em></div>"}
          </div>
        </div>
      </div>
    `;

    // enforce compact cover size + two-column layout regardless of server HTML
    const dialog = root.querySelector(".modal-dialog");
    if (dialog) {
      // inject lightweight inline styles so we don't depend on external CSS
      const styleEl = document.createElement("style");
      styleEl.textContent = `
          .modal-dialog{ max-width: 780px; width: calc(100% - 24px); max-height: 90vh; overflow:auto; }
          .stream-modal{ padding: 16px; }
          .stream-modal .release-wrap{ display:flex; gap:16px; align-items:stretch; }
          /* Square cover (crop if needed) */
          .stream-modal img{
            width:320px;
            height:320px;
            max-width:320px;
            max-height:320px;
            object-fit:cover;
            border-radius:12px;
            display:block;
          }
          /* Links column sized to fit 6 rows into the 320px cover height */
          .stream-modal .links{
            min-width:260px;
            display:flex;
            flex-direction:column;
            gap:10px;                 /* 5 gaps * 10px = 50px */
            flex:1 1 auto;
            max-height:320px;        /* matches cover */
            overflow:hidden;         /* hide anything beyond 6 rows */
          }
          /* Row height tuned: 6 rows * 45px + 5 gaps(10px) = 320px */
          .stream-modal .platform-row{
            display:flex;
            align-items:center;
            gap:10px;
            padding:8px 12px;        /* compact vertical padding */
            background:#151515;
            border:1px solid #222;
            border-radius:12px;
            text-decoration:none;
            color:#ddd;
            font-size:0.92rem;
            min-height:45px;         /* target row height */
            line-height:1.1;
          }
          .stream-modal .platform-row:hover{ background:#181818; border-color:#2a2a2a; }
          .stream-modal .platform-icon{
            width:12px;
            height:12px;
            border-radius:4px;
            background:#4d4d4d;      /* neutral default, can be colored later */
            display:inline-block;
            flex:0 0 12px;
          }
          .stream-modal .platform-name{ flex:1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }

          @media (max-width:640px){
            .stream-modal .release-wrap{ flex-direction:column; }
            .stream-modal img{
              width:100%;
              max-width:100%;
              height:auto;           /* on narrow screens we drop the strict 1:1 to avoid extreme crops */
              max-height:none;
            }
            .stream-modal .links{
              max-height:none;       /* allow natural height on mobile */
              overflow:visible;
            }
          }
        `;

      dialog.prepend(styleEl);

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
        // try to find links container by common selectors or create one
        let linksBox = streamRoot.querySelector(".links, .platforms, .platform-links");
        if (!streamRoot.querySelector(".release-wrap")) {
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

        // finally, hard-limit any image that might slip through
        streamRoot.querySelectorAll("img").forEach(img => {
          img.style.maxWidth = "320px";
          img.style.width = "320px";
          img.style.height = "auto";
          img.style.borderRadius = "12px";
        });

        // --- normalize platform links into consistent rows --------------------
        const linksContainer =
          streamRoot.querySelector(".links") ||
          streamRoot.querySelector(".platforms") ||
          streamRoot.querySelector(".platform-links");

        if (linksContainer) {
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
          function renderRow(label, url){
            const a = document.createElement("a");
            a.href = url; a.target = "_blank"; a.rel = "noopener";
            a.className = "platform-row";
            a.innerHTML = `
              <span class="platform-icon" aria-hidden="true"></span>
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
              renderRow(label, url);
              rendered++;
            });
          }

          // 2) Fallback: object maps from backend (properties/props/platforms)
          if (!rendered){
            const maps = j.properties || j.props || j.platforms;
            if (maps && typeof maps === 'object'){
              Object.entries(maps).forEach(([label, url]) => {
                const L = String(label).trim();
                const U = normalizeUrl(url);
                if (!L || !isProbablyUrl(U)) return;
                renderRow(L, U);
                rendered++;
              });
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
      <div class="modal" role="dialog" aria-modal="true">
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
    const cleanup = () => { root.innerHTML = ""; };
    root.querySelectorAll('[data-close]').forEach(el => el.addEventListener('click', cleanup));
  }
});

// Allow closing modal by clicking outside the dialog or on backdrop
document.addEventListener('click', (e) => {
  const modal = document.querySelector('.modal.show, .modal');
  if (!modal) return;
  const dialog = modal.querySelector('.modal-dialog');
  if (!dialog) return;

  const clickedOutside = !dialog.contains(e.target);
  const clickedBackdrop = e.target.classList.contains('modal-backdrop');
  if (clickedOutside || clickedBackdrop) {
    modal.remove();
  }
});
// --- /Stream Modal FETCH ------------------------------------------------------