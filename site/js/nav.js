/* Tip-Off Numbers: Search, routing between pages, page transitions and the status line.
   Plain scripts loaded in order (index.html); they share one global scope, no build step. */
"use strict";

/* ---------------------------------------------------------------- search & routing */
/* search: players, teams, tonight's games and every page, fully usable from the keyboard (an ARIA combobox) */
const PAGES = [["Tonight", "#/", "Tonight's games and the best picks"], ["Tickets", "#/parlay", "Tonight's game tickets"],
  ["Games", "#/games", "Every upcoming game"], ["Players", "#/players", "Every player, projections and lines"],
  ["Record", "#/results", "How the tickets did"], ["Standings", "#/standings", "Both conferences"], ["Teams", "#/teams", "All 30 teams"],
  ["Model accuracy", "#/accuracy", "How often the chances came true"], ["Mind ranking", "#/mind", "Psychological edges by team"],
  ["Your bets", "#/you", "Tickets you recorded"], ["How it works", "#/about", "Methods and tests"]];
function searchHits(q, ps, games) {
  const has = (...xs) => xs.join(" ").toLowerCase().includes(q);
  const out = [];
  PAGES.filter(([n, , d]) => !q || has(n, d)).slice(0, q ? 4 : 11).forEach(([n, href, d]) => out.push({ href, kind: "Page", html: `<b>${h(n)}</b><span class="sub">${h(d)}</span>` }));
  games.filter(g => !q || has(T(g.away).name, T(g.home).name, g.away, g.home)).slice(0, q ? 4 : 0)
    .forEach(g => out.push({ href: `#/game/${g.id}`, kind: "Game", html: `${disc(g.away, "xs")}${disc(g.home, "xs")}<b>${h(T(g.away).short)} at ${h(T(g.home).short)}</b><span class="sub">${tip(g.tip)}</span>` }));
  if (q) {
    Object.values(TEAMS).filter(t => has(t.name, t.abbr)).slice(0, 4).forEach(t => out.push({ href: `#/team/${t.abbr}`, kind: "Team", html: `${disc(t.abbr, "xs")}<b>${h(t.name)}</b><span class="sub">${h(t.record || "")}</span>` }));
    if (q.length >= 2) ps.filter(p => p.name.toLowerCase().includes(q)).slice(0, 8).forEach(p => out.push({ href: `#/player/${p.id}`, kind: "Player", html: `${disc(p.team, "xs")}<b>${h(p.name)}</b><span class="sub">${fx(p.ppg)} ppg</span>` }));
  }
  return out;
}
function setupSearch() {
  const f = document.querySelector("[data-search]");
  const input = f.querySelector("input"), drop = f.querySelector(".drop");
  let hits = [], act = -1, ps = null, games = null;
  const close = () => { drop.hidden = true; act = -1; input.setAttribute("aria-expanded", "false"); input.removeAttribute("aria-activedescendant"); };
  const mark = () => {
    drop.querySelectorAll("[role=option]").forEach((o, i) => { o.setAttribute("aria-selected", i === act ? "true" : "false"); if (i === act) o.scrollIntoView({ block: "nearest" }); });
    if (act >= 0) input.setAttribute("aria-activedescendant", `hq-o${act}`); else input.removeAttribute("aria-activedescendant");
  };
  const go = i => { const x = hits[i]; if (!x) return; close(); input.value = ""; input.blur(); f.classList.remove("open"); location.hash = x.href; };
  const show = async () => {
    const q = input.value.trim().toLowerCase();
    if (ps === null) { try { ps = await get("players.json"); } catch (e) { ps = []; } }
    if (games === null) { try { games = ((await get("schedule.json")).upcoming || []).slice(0, 15); } catch (e) { games = []; } }
    if (input.value.trim().toLowerCase() !== q) return;
    hits = searchHits(q, ps, games); act = hits.length ? 0 : -1;
    let last = "";
    drop.innerHTML = hits.length ? hits.map((x, i) => `${x.kind !== last ? (last = x.kind, `<p class="drop-h" role="presentation">${x.kind}s</p>`) : ""}<a id="hq-o${i}" role="option" aria-selected="false" href="${x.href}" tabindex="-1">${x.html}</a>`).join("")
      : `<p class="sub" style="padding:8px" role="presentation">Nothing found for “${h(q)}”.</p>`;
    drop.hidden = false; input.setAttribute("aria-expanded", "true"); mark();
  };
  input.addEventListener("input", show);
  input.addEventListener("focus", show);
  input.addEventListener("keydown", e => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); if (drop.hidden) return show(); if (!hits.length) return; act = (act + (e.key === "ArrowDown" ? 1 : -1) + hits.length) % hits.length; mark(); }
    else if (e.key === "Escape") { e.preventDefault(); close(); input.value = ""; input.blur(); f.classList.remove("open"); }
  });
  drop.addEventListener("mousedown", e => e.preventDefault());  // keep focus in the field while clicking a result
  drop.addEventListener("click", e => { const a = e.target.closest("[role=option]"); if (a) { e.preventDefault(); go(+a.id.slice(4)); } });
  f.addEventListener("submit", e => { e.preventDefault(); go(act >= 0 ? act : 0); });
  document.addEventListener("click", e => { if (!f.contains(e.target) && !e.target.closest(".search-toggle")) close(); });
  window.addEventListener("hashchange", close);
  // "/" anywhere (outside a text field) jumps to search, as on most sites
  document.addEventListener("keydown", e => {
    if (e.key !== "/" || e.metaKey || e.ctrlKey || e.altKey || /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName) || document.activeElement.isContentEditable) return;
    e.preventDefault(); f.classList.add("open"); input.focus();
  });
}
/* the "More" menu closes with Escape (focus back on its button) and when a link inside it is followed */
(function moreMenu() {
  const d = document.querySelector("details.more");
  if (!d) return;
  d.addEventListener("keydown", e => { if (e.key === "Escape" && d.open) { d.open = false; d.querySelector("summary").focus(); } });
  document.addEventListener("click", e => { if (d.open && !d.contains(e.target)) d.open = false; });
})();
/* skip link: straight to the page content (a plain #app link would be read as a route) */
document.addEventListener("click", e => {
  const s = e.target.closest && e.target.closest("[data-skip]");
  if (s) { e.preventDefault(); app.focus(); app.scrollIntoView(); }
});

let LAST_HASH = null;
let NAVIGATED = false;
let LAST_GAME = null;
let LAST_PLAYER = null;  // the player page we came from (its name flies back into the list)  // the game page we came from (its card grows back on the way home)
const SCROLL = {};
async function route() {
  if (LAST_HASH !== null) SCROLL[LAST_HASH] = window.scrollY;
  const HERE = location.hash || "#/";
  LAST_HASH = HERE;
  app.oninput = app.onchange = app.onclick = null;
  const parts = location.hash.replace(/^#\/?/, "").split("/");
  const [page, arg] = parts;
  document.querySelectorAll("[data-nav]").forEach(a => a.setAttribute("aria-current", a.dataset.nav === (page || "home") || (page === "game" && a.dataset.nav === "games") || (page === "team" && a.dataset.nav === "teams") || (page === "player" && a.dataset.nav === "players") || (page === "you" && a.dataset.nav === "accuracy") ? "page" : "false"));
  const more = document.querySelector("[data-nav-more]");
  if (more) {
    more.setAttribute("aria-current", document.querySelector(".more-menu [aria-current='page']") ? "page" : "false");
    more.parentElement.open = false;
  }
  const render = async () => {
    stopLive();
    try {
      if (!page) await home();
      else if (page === "games") await games(arg);
      else if (page === "game") await game(arg);
      else if (page === "standings") await standings();
      else if (page === "teams") await teams();
      else if (page === "team") await team(arg);
      else if (page === "players") await playersPage();
      else if (page === "player") await player(arg);
      else if (page === "mind") await mind();
      else if (page === "parlay") await parlayPage();
      else if (page === "accuracy") await accuracy();
      else if (page === "results") await results();
      else if (page === "you") await yourBets();
      else if (page === "about") await about();
      else await home();
      startLive();
      // wide tables scroll sideways: reachable and announced for keyboard and screen-reader users
      app.querySelectorAll(".tscroll").forEach(e => { e.tabIndex = 0; e.setAttribute("role", "region"); e.setAttribute("aria-label", "Table, scrolls sideways"); });
    } catch (err) {
      app.innerHTML = `<div class="wrap" style="padding-top:40px"><p class="empty">Couldn't load this page (${h(err.message)}).</p><p><a href="#/">Back home</a></p></div>`;
    }
    window.scrollTo(0, SCROLL[HERE] || 0);
    enhance(app);
    syncAddButtons();
    renderSlip();
    // the game card and the game page's header are the same object: name the one on this page
    if (page === "game") { const gh = app.querySelector(".gh"); if (gh) gh.style.viewTransitionName = "game-hero"; }
    else if (LAST_GAME) { const c = app.querySelector(`.gm[href="#/game/${CSS.escape(LAST_GAME)}"], a[href="#/game/${CSS.escape(LAST_GAME)}"] .gm`); if (c) c.style.viewTransitionName = "game-hero"; }
    // a player's name flies from the list into the player page's heading, and back
    if (page === "player") { const h1 = app.querySelector(".ph h1, h1"); if (h1) h1.style.viewTransitionName = "player-name"; }
    else if (LAST_PLAYER) { const n = app.querySelector(`.pc-name[href="#/player/${CSS.escape(LAST_PLAYER)}"]`); if (n) n.style.viewTransitionName = "player-name"; }
  };
  if (document.startViewTransition && !REDUCED && app.firstElementChild && !app.querySelector(".sk")) {
    // a real transition: the old page lifts away, the new one rises in; header and tab bar stay put
    if (!(page === "game")) { const gh = app.querySelector(".gh"); if (gh && LAST_GAME) gh.style.viewTransitionName = "game-hero"; }
    if (page !== "player" && LAST_PLAYER) { const h1 = app.querySelector(".ph h1"); if (h1) h1.style.viewTransitionName = "player-name"; }
    app.classList.remove("entering", "leaving");
    const tr = document.startViewTransition(render);
    try { await tr.finished; } catch (e) { /* skipped: the page is still rendered */ }
    document.querySelectorAll("[style*='view-transition-name']").forEach(e => { e.style.viewTransitionName = ""; });
  } else {
    // fallback: a quick fade of the old page while the next one loads
    app.classList.remove("entering");
    app.classList.add("leaving");
    const leaveDone = new Promise(r => setTimeout(r, REDUCED ? 0 : 140));
    if (!app.firstElementChild || app.querySelector(".loading")) app.innerHTML = skeleton();
    await leaveDone;
    await render();
    app.classList.remove("leaving");
    void app.offsetWidth;  // restart the entrance animation
    app.classList.add("entering");
    document.querySelectorAll("[style*='view-transition-name']").forEach(e => { e.style.viewTransitionName = ""; });
  }
  LAST_GAME = page === "game" ? arg : LAST_GAME;
  LAST_PLAYER = page === "player" ? arg : page === "players" ? LAST_PLAYER : null;
  // after a navigation, keyboard and screen-reader users continue from the new page (not on the first load,
  // where Tab must reach the skip link first)
  if (NAVIGATED) app.focus({ preventScroll: true });
  NAVIGATED = true;
  const ann = document.getElementById("announce");
  if (ann) { const h1 = app.querySelector("h1"); ann.textContent = `${h1 ? h1.innerText.replace(/\s+/g, " ").trim() : document.title}, page loaded`; }
}

/* ---------------------------------------------------------------- motion */
const REDUCED = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
function skeleton() {
  const blk = (w, hgt, r = 18) => `<div class="sk" style="width:${w};height:${hgt}px;border-radius:${r}px"></div>`;
  return `<div class="wrap" style="padding-top:72px">${blk("180px", 14, 7)}<div style="height:18px"></div>${blk("60%", 64, 14)}<div style="height:14px"></div>${blk("40%", 20, 8)}
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px;margin-top:48px">${blk("100%", 190, 22).repeat(4)}</div></div>`;
}
let revealObs = null;
function enhance(root) {
  // numbers count up the first time they appear
  if (!REDUCED) root.querySelectorAll(".tile .v.num, .take .v, .tk-foot .v, .rec-tiles .v.num, .ph-tiles .v, .count").forEach(el => countUp(el));
  // sections further down rise in as they scroll into view
  if (!("IntersectionObserver" in window) || REDUCED) return;
  if (revealObs) revealObs.disconnect();
  revealObs = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add("in"); revealObs.unobserve(e.target); } }), { rootMargin: "0px 0px -8% 0px", threshold: 0.06 });
  root.querySelectorAll(".tn-sec, .section, .gm, .panel, .tk-mini, .hw-card, .hw-step, .listcard .row").forEach((el, i) => {
    const r = el.getBoundingClientRect();
    if (r.top > window.innerHeight * 0.92) { el.classList.add("reveal"); el.style.setProperty("--d", `${(i % 6) * 45}ms`); revealObs.observe(el); }
  });
}
function countUp(el) {
  const txt = el.textContent.trim(), m = txt.match(/^([^0-9\-−+]*)([+\-−]?)([0-9]+(?:[.,][0-9]+)?)(.*)$/);
  if (!m || el.dataset.counted || /[:\/]/.test(txt)) return;
  el.dataset.counted = "1";
  const [, pre, sign, num, post] = m, target = parseFloat(num.replace(",", ".")), dec = (num.split(/[.,]/)[1] || "").length;
  if (!isFinite(target) || target === 0) return;
  const t0 = performance.now(), dur = 700;
  const step = t => {
    const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
    el.textContent = `${pre}${sign}${(target * e).toFixed(dec)}${post}`;
    if (k < 1) requestAnimationFrame(step); else el.textContent = txt;
  };
  requestAnimationFrame(step);
}

/* status line: is everything working? */
async function statusLine() {
  const el = document.getElementById("status");
  if (!el || !META.updated) return;
  const st = META.status || {};
  let chk = null, blocked = null;
  try { blocked = await get("checks_failed.json"); } catch (e) { blocked = null; }
  try { chk = await get("checks.json"); } catch (e) { chk = null; }
  const hm = iso => new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  const ageMin = (Date.now() - new Date(META.updated)) / 60000;
  const parts = [];
  parts.push(`<span class="${ageMin > 200 ? "down" : "up"}">●</span> Last update ${hm(META.updated)}${ageMin > 200 ? " (late)" : ""}`);
  parts.push(blocked ? `<span class="down">Safety checks blocked the last run: showing the previous good version</span>`
    : chk ? (chk.ok ? `Safety checks passed (${chk.games_checked} games)` : `<span class="down">Safety checks failed</span>`) : "Safety checks: not run yet");
  if (st.odds_on) parts.push(`Odds credits today ${st.odds_spent_today ?? 0}/${h(String(st.odds_cap))}${st.odds_left ? ` · ${Number(st.odds_left).toLocaleString("en-GB")} left this month` : ""}`);
  if (st.next_refresh) parts.push(`Next refresh about ${hm(st.next_refresh)} (your local time)`);
  if (st.collector_errors && st.collector_errors.length) parts.push(`<span class="down" title="${h(st.collector_errors.join(" | "))}">feed warnings: ${st.collector_errors.length}</span>`);
  el.innerHTML = parts.join(" · ");
  const pill = document.getElementById("statuspill");
  if (pill) {
    const bad = blocked || (chk && !chk.ok) || ageMin > 200;
    pill.innerHTML = `<span class="dot ${bad ? "bad" : ""}"></span>Updated ${hm(META.updated)}<span class="pill-x"> · ${blocked ? "showing last good version" : chk ? (chk.ok ? "Safety checks passed" : "Safety checks failed") : "checks pending"}</span>`;
    pill.title = pill.textContent;
    pill.hidden = false;
  }
}
