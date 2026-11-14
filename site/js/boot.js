/* Tip-Off Numbers: Page-wide behaviour (depth, offline, install, tab bar) and start-up. Loaded last: init calls into every other file.
   Plain scripts loaded in order (index.html); they share one global scope, no build step. */
"use strict";

/* ---------------------------------------------------------------- depth: cards lean toward the pointer and catch the light */
(function tilt() {
  if (REDUCED || !window.matchMedia("(hover: hover) and (pointer: fine)").matches) return;
  const SEL = "[data-tilt], .gm, .tile, .pc, .hw-card, .panel";
  let cur = null, raf = 0;
  const reset = el => { el.style.removeProperty("--rx"); el.style.removeProperty("--ry"); el.classList.remove("lit"); };
  document.addEventListener("pointermove", e => {
    const el = e.target.closest && e.target.closest(SEL);
    if (cur && cur !== el) reset(cur);
    cur = el;
    if (!el || raf) return;
    raf = requestAnimationFrame(() => {
      raf = 0;
      const r = el.getBoundingClientRect(), x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
      const k = el.matches("[data-tilt]") ? 2.2 : 3.5;  // big tickets lean less
      el.style.setProperty("--rx", `${((0.5 - y) * k).toFixed(2)}deg`);
      el.style.setProperty("--ry", `${((x - 0.5) * k).toFixed(2)}deg`);
      el.style.setProperty("--mx", `${(x * 100).toFixed(1)}%`);
      el.style.setProperty("--my", `${(y * 100).toFixed(1)}%`);
      el.classList.add("lit");
    });
  }, { passive: true });
  document.addEventListener("pointerleave", () => { if (cur) reset(cur); cur = null; });
})();

/* ---------------------------------------------------------------- installable app (home-screen icon, offline copy) */
if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost")) {
  window.addEventListener("load", () => navigator.serviceWorker.register("sw.js", { updateViaCache: "none" }).then(r => r.update()).catch(() => {}));
  // when a new version of the app takes over, reload once so the page shows it
  let reloaded = false;
  navigator.serviceWorker.addEventListener("controllerchange", () => { if (!reloaded && navigator.serviceWorker.controller) { reloaded = true; location.reload(); } });
}
(function installPrompt() {
  const standalone = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone;
  const phone = window.matchMedia("(max-width: 820px)").matches;
  if (standalone || !phone || LS.get("tipoff.install.dismissed", false)) return;
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
  const bar = document.createElement("div");
  bar.className = "installbar";
  const close = () => { bar.remove(); LS.set("tipoff.install.dismissed", true); };
  if (ios) {
    bar.innerHTML = `<img src="icons/icon-192.png" alt=""><p><b>Get the app</b>Tap <span class="ios-share" aria-label="Share">⬆︎</span> Share, then <b class="in">Add to Home Screen</b>.</p><button type="button" aria-label="Close">✕</button>`;
    bar.querySelector("button").onclick = close;
    setTimeout(() => document.body.appendChild(bar), 2500);
  } else {
    window.addEventListener("beforeinstallprompt", e => {
      e.preventDefault();
      bar.innerHTML = `<img src="icons/icon-192.png" alt=""><p><b>Get the app</b>One tap, opens full screen, works without signal.</p><button type="button" class="go">Install</button><button type="button" aria-label="Close">✕</button>`;
      bar.querySelector(".go").onclick = async () => { e.prompt(); await e.userChoice.catch(() => {}); close(); };
      bar.querySelector("[aria-label=Close]").onclick = close;
      document.body.appendChild(bar);
    });
  }
})();
function offlineNote() {
  let n = document.getElementById("offline-note");
  if (navigator.onLine) { if (n) n.remove(); return; }
  if (!n) { n = document.createElement("div"); n.id = "offline-note"; n.textContent = "No signal: showing the last saved data."; document.body.appendChild(n); }
}
window.addEventListener("online", offlineNote); window.addEventListener("offline", offlineNote); offlineNote();

document.addEventListener("click", e => {
  const tb = e.target.closest && e.target.closest("[data-tech]");
  if (tb) { const tk = tb.closest(".ticket"); tk.classList.toggle("show-tech"); tb.textContent = tk.classList.contains("show-tech") ? "Hide the numbers behind it" : "Show the numbers behind it"; return; }
  const b = e.target.closest && e.target.closest(".search-toggle");
  if (!b) return;
  const f = document.querySelector(".hsearch");
  f.classList.toggle("open");
  if (f.classList.contains("open")) f.querySelector("input").focus();
});

/* phones and tablets: the tabs live at the bottom of the screen. The header blurs what is behind it, and a
   blurred box pins anything inside it, so the tab bar is moved out of the header (and back on desktop). */
(function placeTabs() {
  const mq = window.matchMedia("(max-width: 900px), (hover: none) and (pointer: coarse), (display-mode: standalone)");
  const nav = document.querySelector(".nav"), home = document.querySelector(".top-inner"), brand = home && home.querySelector(".brand");
  if (!nav || !home) return;
  const place = () => {
    if (mq.matches) { if (nav.parentElement !== document.body) document.body.appendChild(nav); nav.classList.add("tabbar"); }
    else { if (nav.parentElement !== home) brand.after(nav); nav.classList.remove("tabbar"); }
  };
  place();
  (mq.addEventListener ? mq.addEventListener("change", place) : mq.addListener(place));
})();


/* ---------------------------------------------------------------- start-up */
(async function init() {
  try {
    META = await get("meta.json");
    version = META.updated || version;
    const list = await get("teams.json");
    for (const t of list) TEAMS[t.abbr] = t;
    document.getElementById("freshness").textContent = `Updated ${ago(META.updated)} · ${META.season} season${META.mode === "demo" ? " · simulated preview data" : ""}`;
    statusLine();
  } catch (e) { /* pages show their own error */ }
  setupSearch();
  try { PAR = await get("parlay.json"); } catch (e) { PAR = null; }
  renderSlip();
  document.addEventListener("click", e => {
    const add = e.target.closest("[data-add]");
    if (add) { e.preventDefault(); e.stopPropagation(); toggleSlip(add.dataset.add, add.dataset.leg ? JSON.parse(add.dataset.leg) : null); }
  }, true);
  document.addEventListener("click", async e => {
    const b = e.target.closest("[data-copy]");
    if (!b) return;
    try { await navigator.clipboard.writeText(b.dataset.copy); b.textContent = "Copied"; } catch (err) { b.textContent = "Copy failed"; }
  });
  window.addEventListener("hashchange", route);
  route();
})();
