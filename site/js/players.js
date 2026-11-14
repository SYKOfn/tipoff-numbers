/* Tip-Off Numbers: The bet slip, the players pages and the mind ranking.
   Plain scripts loaded in order (index.html); they share one global scope, no build step. */
"use strict";

/* ---------------------------------------------------------------- bet slip (follows you on every page) */
const slipDay = () => (PAR && PAR.today && PAR.today.day) || "none";
function slipPool() {
  const t = PAR && PAR.today, m = new Map();
  if (!t) return m;
  [...(t.board || []), ...(t.singles || []), ...(t.parlays || []).flatMap(pr => pr.legs)].forEach(l => m.set(l.id, l));
  return m;
}
function slipLegs() {
  const pool = slipPool(), extra = LS.get("tipoff.slipx." + slipDay(), {});
  return LS.get("tipoff.pick." + slipDay(), []).map(id => pool.get(id) || extra[id]).filter(l => l && !singleOnly(l));
}
function toggleSlip(id, leg) {
  const k = "tipoff.pick." + slipDay();
  let ids = LS.get(k, []);
  if (ids.includes(id)) ids = ids.filter(x => x !== id);
  else {
    ids = [...ids, id];
    if (leg && !slipPool().has(id)) { const x = LS.get("tipoff.slipx." + slipDay(), {}); x[id] = leg; LS.set("tipoff.slipx." + slipDay(), x); }
  }
  LS.set(k, ids);
  SLIP_OPEN = SLIP_OPEN || ids.length === 1;
  renderSlip();
  syncAddButtons();
  if (typeof refreshValues === "function" && document.getElementById("custom")) document.getElementById("custom").innerHTML = custom();
  app.querySelectorAll(".pick[data-leg]").forEach(cb => { cb.checked = ids.includes(cb.dataset.leg); });
}
function syncAddButtons() {
  const ids = new Set(LS.get("tipoff.pick." + slipDay(), []));
  document.querySelectorAll("[data-add]").forEach(b => { const on = ids.has(b.dataset.add); b.setAttribute("aria-pressed", on ? "true" : "false"); b.classList.toggle("on", on); b.title = on ? "In your ticket (tap to remove)" : "Add to your ticket"; });
}
const singleOnly = l => l && l.kind === "prop" && l.stat === "pra";
const addBtn = (l, label = "") => singleOnly(l) ? `<span class="single-tag" title="Winamax only takes points + rebounds + assists as a bet on its own, never inside a combiné">single bet</span>` : `<button type="button" class="addleg" data-add="${h(l.id)}"${l._synthetic ? ` data-leg="${h(JSON.stringify(l))}"` : ""} aria-pressed="false" aria-label="Add ${h(legDesc(l))} to your ticket"><span class="plus">+</span><span class="tick">✓</span>${label}</button>`;
function propLeg(pid, name, team, game, tip, opp, home, stat, line, over) {
  // a player over built from the projection, for players and lines not in tonight's curated list
  return { id: `x${pid}_${stat}_${line}`, _synthetic: true, game, kind: "prop", player: pid, player_name: name, team, stat, line, side: "over", p: over,
    fair: +(1 / over).toFixed(2), min_odds: +(1.05 / over).toFixed(2), tip, matchup: home ? `${opp} at ${team}` : `${team} at ${opp}` };
}
let SLIP_OPEN = false;
function renderSlip() {
  let el = document.getElementById("slip");
  if (!el) { el = document.createElement("aside"); el.id = "slip"; el.setAttribute("aria-label", "Your ticket"); document.body.appendChild(el); }
  const legs = slipLegs();
  document.body.classList.toggle("has-slip", legs.length > 0);
  if (!legs.length) { el.hidden = true; el.innerHTML = ""; return; }
  el.hidden = false;
  const p = jointOf(legs), odds = legs.map(l => oddsOf(l.id)), all = odds.every(Boolean), prod = all ? odds.reduce((a, b) => a * b, 1) : null;
  const ev = prod ? p * prod - 1 : null;
  el.className = SLIP_OPEN ? "open" : "";
  el.innerHTML = `<div class="slip-in">
    <button type="button" class="slip-bar" id="slipToggle" aria-expanded="${SLIP_OPEN}">
      <span class="slip-count num">${legs.length}</span><span class="slip-title">My ticket</span>
      <span class="slip-stat"><span>Chance</span><b class="num">${pct(p)}</b></span>
      <span class="slip-stat"><span>Fair odds</span><b class="num">${fx(1 / p, 2)}</b></span>
      <span class="slip-stat go"><span>Take at</span><b class="num">${fx(1.05 / p, 2)}+</b></span>
      ${prod ? `<span class="slip-stat ${ev >= 0 ? "go" : "bad"}"><span>Your Winamax odds</span><b class="num">${fx(prod, 2)} · ${ev >= 0 ? "worth it" : "not worth it"}</b></span>` : ""}
      <span class="slip-chev" aria-hidden="true">${SLIP_OPEN ? "▾" : "▴"}</span></button>
    ${SLIP_OPEN ? `<div class="slip-body"><ul>${legs.map(l => `<li><div class="grow"><b>${h(legDesc(l))}</b><span class="sub small">${h(l.matchup || "")}${l.tip ? ` · ${tipTime(l.tip)}` : ""} · ${pct(effP(l))} · take at ${fx(1.05 / effP(l), 2)}+</span></div>
        <label class="sr" for="so_${h(l.id)}">Winamax odds</label><input id="so_${h(l.id)}" class="slipodds" data-id="${h(l.id)}" type="number" inputmode="decimal" step="0.01" min="1.01" placeholder="Odds" value="${oddsOf(l.id) || ""}">
        <button type="button" class="slip-x" data-add="${h(l.id)}" aria-label="Remove ${h(legDesc(l))}">×</button></li>`).join("")}</ul>
      <div class="slip-acts"><button type="button" class="pill-btn" id="slipClear">Clear</button><button type="button" class="pill-btn" data-copy="${h(`My ticket — Tip-Off Numbers\n` + legs.map((l, i) => `${i + 1}. ${legDesc(l)} — ${pct(effP(l))}, take at ${fx(1.05 / effP(l), 2)}+`).join("\n") + `\nAll: ${pct(p)} · fair ${fx(1 / p, 2)} · worth placing at ${fx(1.05 / p, 2)}+`)}">Copy</button>
        <button type="button" class="pill-btn primary" id="slipRecord">Record as my bet</button></div>
      <p class="sub small" style="margin:10px 0 0">Same-game legs from tonight's checked list are priced together; other player lines added from the Players page count as independent, so two lines on the same player are a bit more likely together than shown. A leg whose player doesn't play is voided on Winamax.</p></div>` : ""}
  </div>`;
  document.getElementById("slipToggle").onclick = () => { SLIP_OPEN = !SLIP_OPEN; renderSlip(); };
  const clr = document.getElementById("slipClear");
  if (clr) clr.onclick = () => { LS.set("tipoff.pick." + slipDay(), []); renderSlip(); syncAddButtons(); app.querySelectorAll(".pick[data-leg]").forEach(cb => { cb.checked = false; }); };
  const rec = document.getElementById("slipRecord");
  if (rec) rec.onclick = () => { recordBet("My ticket", legs, p); rec.textContent = "Recorded"; };
  el.querySelectorAll(".slipodds").forEach(inp => inp.onchange = () => { const v = parseFloat(inp.value); LS.set(`tipoff.odds.${inp.dataset.id}`, v > 1 ? v : null); renderSlip(); });
}

/* ---------------------------------------------------------------- players */
const PCOLS = [["gp", "GP", 0], ["mpg", "MIN", 1], ["ppg", "PTS", 1], ["rpg", "REB", 1], ["apg", "AST", 1], ["tpm", "3PM", 1], ["spg", "STL", 1], ["bpg", "BLK", 1], ["ts", "TS%", 3], ["usg", "USG%", 1], ["pm", "+/-", 1], ["l5", "Last 5", 1], ["next_pts", "Next game", 1]];
const PSTATE = { sort: "ppg", dir: -1, q: "", team: "", pos: "", min: 3 };
const plink = (id, name) => `<a href="#/player/${h(id)}">${h(name)}</a>`;
function newsTag(n) {
  if (!n) return "";
  const t = n.rest ? "resting (news)" : n.min_cap ? `limit ~${Math.round(n.min_cap)} min (news)` : n.start ? "starting (news)" : n.bench ? "to the bench (news)" : n.returning ? "returning (news)" : "";
  return t ? `<span class="ptag news" title="${h(n.quote || "")}">${h(t)}</span>` : "";
}
function ptags(p) {
  return newsTag(p.news) + (p.out ? `<span class="ptag out">${h(p.status || "Out")}</span>` : p.status ? `<span class="ptag q">${h(p.status)}</span>` : "")
    + (p.contract_year ? `<span class="ptag" title="Final year of his contract">contract yr</span>` : "")
    + (p.former ? `<span class="ptag" title="Has played for another team in the stored seasons">ex-team</span>` : "");
}
function allPlayersTable(list) {
  const render = () => {
    const q = PSTATE.q.toLowerCase();
    let rows = list.filter(p => (p.gp || 0) >= PSTATE.min && (!PSTATE.team || p.team === PSTATE.team) && (!PSTATE.pos || (p.pos || "").includes(PSTATE.pos)) && (!q || p.name.toLowerCase().includes(q)));
    rows.sort((a, b) => ((a[PSTATE.sort] ?? -1e9) - (b[PSTATE.sort] ?? -1e9)) * PSTATE.dir || a.name.localeCompare(b.name));
    const head = `<tr><th>#</th><th>Player</th><th>Team</th>${PCOLS.map(([k, l]) => `<th class="n sortable ${PSTATE.sort === k ? "sorted" : ""}" data-k="${k}">${l}${PSTATE.sort === k ? (PSTATE.dir < 0 ? " ↓" : " ↑") : ""}</th>`).join("")}</tr>`;
    const body = rows.slice(0, 400).map((p, i) => `<tr class="${p.out ? "out" : ""}"><td class="pos">${i + 1}</td><td class="nm">${plink(p.id, p.name)}<span class="sub">${h(p.pos || "")}</span>${ptags(p)}</td><td>${tlink(p.team)}</td>
      ${PCOLS.map(([k, , d]) => `<td class="n ${PSTATE.sort === k ? "hl" : ""}">${k === "ts" ? (p[k] == null ? "–" : (p[k] * 100).toFixed(1)) : k === "pm" ? sgn(p[k]) : fx(p[k], d)}</td>`).join("")}</tr>`).join("");
    document.getElementById("ptab").innerHTML = `<div class="tscroll"><table class="ptable">${head}${body}</table></div><p class="sub small" style="margin-top:8px">${rows.length} players${rows.length > 400 ? " (first 400 shown)" : ""}. "Next game" is the projected points for his next game.</p>`;
    document.querySelectorAll("#ptab th.sortable").forEach(th => th.onclick = () => { const k = th.dataset.k; PSTATE.dir = PSTATE.sort === k ? -PSTATE.dir : -1; PSTATE.sort = k; render(); });
  };
  const teams = Object.values(TEAMS).sort((a, b) => a.name.localeCompare(b.name));
  document.getElementById("pview").innerHTML = `<div class="toolbar"><input id="pq" type="search" placeholder="Filter by name" value="${h(PSTATE.q)}">
    <select id="pt"><option value="">All teams</option>${teams.map(t => `<option value="${t.abbr}" ${PSTATE.team === t.abbr ? "selected" : ""}>${h(t.name)}</option>`).join("")}</select>
    <select id="pp"><option value="">All positions</option>${["G", "F", "C"].map(x => `<option ${PSTATE.pos === x ? "selected" : ""}>${x}</option>`).join("")}</select>
    <select id="pm"><option value="1">1+ games</option><option value="3" selected>3+ games</option><option value="10">10+ games</option></select></div><div id="ptab"></div>`;
  document.getElementById("pm").value = String(PSTATE.min);
  document.getElementById("pq").oninput = e => { PSTATE.q = e.target.value; render(); };
  document.getElementById("pt").onchange = e => { PSTATE.team = e.target.value; render(); };
  document.getElementById("pp").onchange = e => { PSTATE.pos = e.target.value; render(); };
  document.getElementById("pm").onchange = e => { PSTATE.min = +e.target.value; render(); };
  render();
}

const STATW = { pts: "points", reb: "rebounds", ast: "assists", tpm: "threes", pra: "pts+reb+ast" };
function legFor(p, b) {
  // the curated leg for this player and line if tonight's list has it, else one built from his projection
  const hit = [...slipPool().values()].find(l => l.kind === "prop" && String(l.player) === String(p.id) && l.stat === b.stat && Math.abs(l.line - b.line) < 0.01 && l.side === "over");
  return hit || propLeg(p.id, p.name, p.team, p.next_game, p.next_tip, p.next_opp, p.next_home, b.stat, b.line, b.over);
}
function gameBuilder(g) {
  const gid = String(g.id || g.game_id || location.hash.split("/")[2]);
  const legs = [...slipPool().values()].filter(l => String(l.game) === gid).sort((a, b) => b.p - a.p).slice(0, 12);
  if (!legs.length || g.kind !== "estimate") return "";
  const row = l => `<div class="bb-leg"><span class="kind ${l.kind}">${KIND[l.kind] || l.kind}</span><span class="grow">${h(legDesc(l))}</span><span class="num sub">${pct(effP(l))}</span><b class="num">${fx(1.05 / effP(l), 2)}+</b>${addBtn(l)}</div>`;
  return `<section class="section"><h2>Legs from this game <span class="sub">the model's strongest; tap + to add to your ticket</span></h2>
    <div class="bb">${legs.slice(0, 5).map(row).join("")}${legs.length > 5 ? `<details class="vb-fold"><summary>Show ${legs.length - 5} more</summary>${legs.slice(5).map(row).join("")}</details>` : ""}</div></section>`;
}
function playerCard(p) {
  const ink = teamInk(p.team);
  return `<article class="pc" style="--c:${ink}">
    <div class="pc-top">${mono(p.team, "sm")}<div class="grow"><a class="pc-name" href="#/player/${h(p.id)}">${h(p.name)}</a>
      <span class="sub small">${p.next_home ? "vs" : "at"} ${h(T(p.next_opp).short)} · ${tipTime(p.next_tip)}${p.pos ? ` · ${h(p.pos)}` : ""}</span></div>
      ${newsTag(p.news)}${p.status ? `<span class="ptag q">${h(p.status)}</span>` : ""}</div>
    <div class="pc-nums">${[["Points", p.next_pts], ["Rebounds", p.next_reb], ["Assists", p.next_ast], ["Threes", p.next_tpm]].map(([k, v]) => `<div><b class="num">${v == null ? "–" : fx(v, 1)}</b><span>${k}</span></div>`).join("")}</div>
    ${(p.next_best || []).length ? `<div class="pc-legs">${p.next_best.map(b => { const l = legFor(p, b); return `<div class="pc-leg"><span>${Math.ceil(b.line)}+ ${STATW[b.stat] || b.stat}</span><b class="num">${pct(b.over)}</b>${addBtn(l)}</div>`; }).join("")}</div>` : ""}
    ${(p.next_spots || []).length ? `<p class="pc-spots">${p.next_spots.map(h).join(" · ")}</p>` : ""}
  </article>`;
}
const TSTATE = { q: "", team: "", sort: "next_pts", n: 48 };
async function playersPage() {
  const list = await get("players.json");
  setTitle("Players");
  const now = Date.now();
  const tips = list.filter(p => p.next_tip && !p.out).map(p => p.next_tip).sort();
  const firstDay = tips.length ? new Date(tips[0]).getTime() : null;
  const tonight = firstDay ? list.filter(p => p.next_tip && !p.out && p.next_pts != null && new Date(p.next_tip).getTime() - firstDay < 20 * 3600e3) : [];
  const mode = location.hash.includes("/all") || !tonight.length ? "all" : "tonight";
  const teamsTonight = [...new Set(tonight.map(p => p.team))].sort((a, b) => T(a).short.localeCompare(T(b).short));
  app.innerHTML = `<div class="wrap tn">${demoBanner()}<section class="tn-hero" style="padding-bottom:28px"><div class="lead"><p class="eyebrow">${mode === "tonight" ? `${tonight.length} players in tonight's games` : "Every player this season"}</p><h1>Players</h1>
    <p class="sublede">${mode === "tonight" ? "Tonight's projections and each player's likeliest overs. Tap + to add a line to your ticket." : "Per-game numbers, shooting efficiency, usage and the projection for each player's next game."}</p></div></section>
    <nav class="daytabs" aria-label="View"><a href="#/players" aria-current="${mode === "tonight" ? "page" : "false"}">Tonight</a><a href="#/players/all" aria-current="${mode === "all" ? "page" : "false"}">All players</a></nav>
    <div id="pview" style="margin-top:24px"></div></div>`;
  if (mode === "all") { allPlayersTable(list); return; }
  const render = () => {
    const q = TSTATE.q.toLowerCase();
    let rows = tonight.filter(p => (!TSTATE.team || p.team === TSTATE.team) && (!q || p.name.toLowerCase().includes(q)));
    rows.sort((a, b) => (b[TSTATE.sort] ?? -1) - (a[TSTATE.sort] ?? -1));
    document.getElementById("pcards").innerHTML = rows.slice(0, TSTATE.n).map(playerCard).join("") || `<p class="empty">No player matches.</p>`;
    const more = document.getElementById("pmore");
    more.hidden = rows.length <= TSTATE.n;
    more.textContent = `Show more (${rows.length - TSTATE.n} more)`;
    syncAddButtons();
    enhance(document.getElementById("pcards"));
  };
  document.getElementById("pview").innerHTML = `<div class="toolbar"><label class="sr" for="tq">Search tonight's players</label><input id="tq" type="search" placeholder="Search tonight's players" value="${h(TSTATE.q)}">
    <label class="sr" for="tt">Team</label><select id="tt"><option value="">All teams tonight</option>${teamsTonight.map(a => `<option value="${a}" ${TSTATE.team === a ? "selected" : ""}>${h(T(a).name)}</option>`).join("")}</select>
    <label class="sr" for="ts">Sort by</label><select id="ts">${[["next_pts", "Most points"], ["next_reb", "Most rebounds"], ["next_ast", "Most assists"], ["next_tpm", "Most threes"]].map(([k, l]) => `<option value="${k}" ${TSTATE.sort === k ? "selected" : ""}>${l}</option>`).join("")}</select></div>
    <div class="pc-grid" id="pcards"></div><button type="button" class="vb-more pc-more" id="pmore" hidden></button>`;
  document.getElementById("tq").oninput = e => { TSTATE.q = e.target.value; render(); };
  document.getElementById("tt").onchange = e => { TSTATE.team = e.target.value; render(); };
  document.getElementById("ts").onchange = e => { TSTATE.sort = e.target.value; render(); };
  document.getElementById("pmore").onclick = () => { TSTATE.n += 48; render(); };
  render();
}
function linesBlock(lines, which) {
  const keys = which || Object.keys(lines || {});
  return `<div class="plines">${keys.filter(k => lines[k]).map(k => `<div><h4>${h({ pts: "Points", reb: "Rebounds", ast: "Assists", tpm: "Threes", pra: "Pts+Reb+Ast" }[k] || k)}</h4>${linesList(lines[k], null, "Over")}</div>`).join("")}</div>`;
}

function formChart(log) {
  const g = log.slice(0, 15).reverse();
  if (!g.length) return "";
  const W = 520, H = 160, pad = 22, top = 18, bw = (W - pad * 2) / g.length;
  const mx = Math.max(10, ...g.map(x => Math.max(x.pts, x.proj ? x.proj.pts : 0)));
  const y = v => H - pad - v / mx * (H - pad - top);
  return `<svg class="formchart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Points in recent games">
    ${g.map((x, i) => {
      const cx = pad + i * bw + bw / 2, yb = y(x.pts), yp = x.proj ? y(x.proj.pts) : null;
      // the number sits above both the bar and the projection mark, so they never overlap
      const yl = Math.min(yb, yp ?? yb) - 6;
      return `<rect x="${pad + i * bw + 3}" y="${yb}" width="${bw - 6}" height="${H - pad - yb}" rx="3" fill="${x.win ? "var(--pos)" : "var(--neg)"}" opacity=".8"><title>${day(x.day)} ${x.home ? "vs" : "at"} ${lab3(x.opp)}: ${x.pts} pts${x.proj ? `, projected ${fx(x.proj.pts)}` : ""} (${x.win ? "win" : "loss"} ${h(x.score)})</title></rect>
      ${yp != null ? `<line x1="${pad + i * bw + 1}" x2="${pad + (i + 1) * bw - 1}" y1="${yp}" y2="${yp}" stroke="var(--ink)" stroke-width="2.5"/>` : ""}
      <text x="${cx}" y="${yl}" text-anchor="middle">${x.pts}</text><text x="${cx}" y="${H - 6}" text-anchor="middle">${h(lab3(x.opp))}</text>`; }).join("")}
    <line x1="${pad}" x2="${W - pad}" y1="${H - pad}" y2="${H - pad}" stroke="var(--line)"/></svg>`;
}

async function player(id) {
  const p = await get(`player/${id}.json`);
  setTitle(p.name);
  const t = T(p.team), col = readable(t.color), c = p.current || {};
  const n = p.next;
  const ltabs = ["pts", "reb", "ast", "tpm", "pra"];
  const nextHtml = n ? `<div class="panel"><h3>Next game: ${n.home ? "vs" : "at"} <a href="#/team/${n.opp}">${h(T(n.opp).short)}</a> · <a href="#/game/${n.game}">${tip(n.tip)}</a></h3>
      ${n.out ? `<p class="call"><b>${h(n.status || "Out")}</b>${n.detail ? ` — ${h(n.detail)}` : ""}. Not projected to play.</p>` : `
      ${n.status ? `<p class="call"><b>${h(n.status)}</b>${n.detail ? ` — ${h(n.detail)}` : ""}. ${n.play != null && n.play < 1 ? `Chance he plays: <b>${pct(n.play)}</b>. ` : ""}Projection assumes he plays.</p>` : ""}
      <div class="projgrid">${[["min", "Minutes"], ["pts", "Points"], ["reb", "Rebounds"], ["ast", "Assists"], ["tpm", "Threes"], ["pra", "Pts+Reb+Ast"], ["stl", "Steals"], ["blk", "Blocks"], ["tov", "Turnovers"]].map(([k, l]) => `<div><b>${fx(n.proj[k])}</b>${l}</div>`).join("")}</div>
      ${n.spots && n.spots.length ? `<ul class="spots">${n.spots.map(s => `<li><div class="sh"><b>${h(s.label)}</b><span class="eff ${effCls(s.pct)}">${sgn(s.pct)}% pts</span></div><p>${h(s.text)}</p><div class="hist">${ev(s.evidence)}</div></li>`).join("")}</ul>` : `<p class="none-note">No special spot for him in this game.</p>`}
      ${(() => {
        const pp = { id: p.id, name: p.name, team: p.team, next_game: n.game, next_tip: n.tip, next_opp: n.opp, next_home: n.home };
        const best = Object.entries(n.lines || {}).map(([st, lst]) => { const ok = (lst || []).filter(l => l.over >= 0.6); return ok.length ? { stat: st, ...ok.reduce((a, b) => (b.line > a.line ? b : a)) } : null; }).filter(Boolean);
        return best.length ? `<h4 style="margin:16px 0 8px">Likeliest overs</h4><div class="pc-legs">${best.map(b => `<div class="pc-leg"><span>${Math.ceil(b.line)}+ ${STATW[b.stat] || b.stat}</span><b class="num">${pct(b.over)}</b>${addBtn(legFor(pp, b))}</div>`).join("")}</div>` : "";
      })()}
      <div class="ltabs" id="ltabs">${ltabs.map((k, i) => `<button data-k="${k}" aria-pressed="${i === 0}">${{ pts: "Points", reb: "Rebounds", ast: "Assists", tpm: "Threes", pra: "PRA" }[k]}</button>`).join("")}</div><div id="lbox">${n.lines ? linesList(n.lines.pts, null, "Over") : ""}</div>`}</div>`
    : `<div class="panel"><h3>Next game</h3><p class="sub">Not in a projected rotation for the next two weeks (injury, or too few recent minutes).</p></div>`;
  const seasonRows = p.seasons.map(s => `<tr><td>${s.season - 1}-${String(s.season).slice(2)}</td><td>${tlink(s.team)}</td><td class="n">${s.gp}</td><td class="n">${fx(s.mpg)}</td><td class="n">${fx(s.ppg)}</td><td class="n">${fx(s.rpg)}</td><td class="n">${fx(s.apg)}</td><td class="n">${fx(s.tpm)}</td><td class="n">${fx(s.spg)}</td><td class="n">${fx(s.bpg)}</td><td class="n">${s.fg == null ? "–" : (s.fg * 100).toFixed(1)}</td><td class="n">${s.tp == null ? "–" : (s.tp * 100).toFixed(1)}</td><td class="n">${s.ft == null ? "–" : (s.ft * 100).toFixed(1)}</td><td class="n">${s.ts == null ? "–" : (s.ts * 100).toFixed(1)}</td><td class="n">${fx(s.usg)}</td><td class="n">${fx(s.p36)}</td><td class="n">${sgn(s.pm)}</td></tr>`).join("");
  const adv = c.gp ? `<div class="adv">${[["TS%", c.ts == null ? "–" : (c.ts * 100).toFixed(1), "true shooting"], ["eFG%", c.efg == null ? "–" : (c.efg * 100).toFixed(1), "effective FG"], ["USG%", fx(c.usg), "plays used on floor"], ["REB%", fx(c.reb_pct), "rebounds grabbed"], ["AST%", fx(c.ast_pct), "team baskets assisted"], ["AST/TO", fx(c.ast_tov, 2), "assists per turnover"], ["Per 36", `${fx(c.p36)}/${fx(c.r36)}/${fx(c.a36)}`, "pts/reb/ast"], ["+/-", sgn(c.pm), "per game on floor"]].map(([l, v, s]) => `<div><b>${v}</b>${l} · ${s}</div>`).join("")}</div>` : "";
  const splits = p.splits.length ? `<div class="tscroll"><table><tr><th>Split</th><th class="n">GP</th><th class="n">MIN</th><th class="n">PTS</th><th class="n">REB</th><th class="n">AST</th><th class="n">3PM</th><th class="n">TS%</th></tr>${p.splits.map(s => `<tr><td>${h(s.name)}</td><td class="n">${s.gp}</td><td class="n">${fx(s.mpg)}</td><td class="n">${fx(s.ppg)}</td><td class="n">${fx(s.rpg)}</td><td class="n">${fx(s.apg)}</td><td class="n">${fx(s.tpm)}</td><td class="n">${s.ts == null ? "–" : (s.ts * 100).toFixed(1)}</td></tr>`).join("")}</table></div>` : "";
  const vs = p.vs.length ? `<div class="tscroll"><table><tr><th>Opponent</th><th class="n">GP</th><th class="n">PTS</th><th class="n">REB</th><th class="n">AST</th></tr>${p.vs.map(s => `<tr><td>${tlink(s.opp)}</td><td class="n">${s.gp}</td><td class="n">${fx(s.ppg)}</td><td class="n">${fx(s.rpg)}</td><td class="n">${fx(s.apg)}</td></tr>`).join("")}</table></div>` : "";
  const glog = `<div class="tscroll"><table class="ptable"><tr><th>Date</th><th>Opp</th><th>Result</th><th class="n">MIN</th><th class="n">PTS</th><th class="n">Proj</th><th class="n">REB</th><th class="n">AST</th><th class="n">3PM</th><th class="n">STL</th><th class="n">BLK</th><th class="n">TO</th><th class="n">FG</th><th class="n">3PT</th><th class="n">FT</th><th class="n">+/-</th></tr>
    ${p.log.map(r => `<tr><td><a href="#/game/${r.id}">${day(r.day)}</a></td><td>${r.home ? "vs" : "@"} ${h(lab3(r.opp))}</td><td class="${r.win ? "up" : "down"}">${r.win ? "W" : "L"} ${h(r.score)}</td><td class="n">${r.min}</td><td class="n hl">${r.pts}</td><td class="n sub">${r.proj ? fx(r.proj.pts) : "–"}</td><td class="n">${r.reb}</td><td class="n">${r.ast}</td><td class="n">${r.tpm ?? "–"}</td><td class="n">${r.stl ?? "–"}</td><td class="n">${r.blk ?? "–"}</td><td class="n">${r.tov ?? "–"}</td><td class="n">${r.fg ?? "–"}</td><td class="n">${r.tp ?? "–"}</td><td class="n">${r.ft ?? "–"}</td><td class="n">${sgn(r.pm, 0)}</td></tr>`).join("")}</table></div>`;
  app.innerHTML = `<section class="gh ph" style="--ca:${teamInk(p.team)};--ch:${teamInk(p.team)}"><div class="wrap">
    <div class="ph-main"><div class="ph-num num">${h(p.jersey ?? p.pos ?? "")}</div>
      <div class="ph-id"><p class="eyebrow">${h(p.pos || "")} · <a href="#/team/${p.team}">${h(t.name)}</a>${p.former.length ? ` · formerly ${p.former.map(x => h(T(x).short)).join(", ")}` : ""}</p><h1>${h(p.name)}</h1></div></div>
    <div class="ph-tiles">${[["Points", fx(c.ppg)], ["Rebounds", fx(c.rpg)], ["Assists", fx(c.apg)], ["Minutes", fx(c.mpg)], ["True shooting", c.ts == null ? "–" : (c.ts * 100).toFixed(1) + "%"], ["Usage", c.usg == null ? "–" : fx(c.usg) + "%"], ["Games", c.gp ?? 0]].map(([k, v]) => `<div class="tile"><p class="k">${k}</p><p class="v num">${v}</p></div>`).join("")}</div>
  </div></section>
  <div class="wrap">${demoBanner()}
    ${p.story.length ? `<p class="call"><b>Storylines:</b> ${p.story.map(h).join(" ")}</p>` : ""}
    <section class="grid2" style="margin-top:14px">${nextHtml}<div class="panel" style="align-self:start"><h3>Recent games</h3><p class="sub small">Points per game, newest on the right. Green bar: his team won; red: it lost. White line: what the model projected before that game.</p>${formChart(p.log)}</div></section>
    ${adv ? `<section class="section"><h2>Advanced <span class="sub">this season</span></h2>${adv}</section>` : ""}
    ${splits ? `<section class="section grid2"><div><h2>Splits</h2>${splits}</div><div><h2>Against each opponent <span class="sub">this season and last</span></h2>${vs}</div></section>` : ""}
    <section class="section"><h2>Season by season</h2><div class="tscroll"><table><tr><th>Season</th><th>Team</th><th class="n">GP</th><th class="n">MIN</th><th class="n">PTS</th><th class="n">REB</th><th class="n">AST</th><th class="n">3PM</th><th class="n">STL</th><th class="n">BLK</th><th class="n">FG%</th><th class="n">3P%</th><th class="n">FT%</th><th class="n">TS%</th><th class="n">USG%</th><th class="n">Pts/36</th><th class="n">+/-</th></tr>${seasonRows}</table></div></section>
    <section class="section"><h2>Game log</h2>${glog}</section></div>`;
  const lt = document.getElementById("ltabs");
  if (lt && n && n.lines) lt.onclick = e => { const b = e.target.closest("button"); if (!b) return; lt.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", x === b)); document.getElementById("lbox").innerHTML = linesList(n.lines[b.dataset.k], null, "Over"); };
}

/* ---------------------------------------------------------------- mind ranking */
const CATCOL = { Hot: "var(--pos)", Cold: "var(--base)", "Under pressure": "var(--body)", Coasting: "var(--muted)", Steady: "var(--mind)" };
const catTag = c => `<span class="cat ${h(c.split(" ")[0])}">${h(c)}</span>`;
async function mind() {
  const rows = await get("mind.json");
  setTitle("Mind ranking");
  const counts = {};
  rows.forEach(r => counts[r.cat] = (counts[r.cat] || 0) + 1);
  const mx = Math.max(4, ...rows.map(r => Math.abs(r.score)));
  app.innerHTML = `<section class="hero court"><div class="wrap"><h1>Mind ranking</h1><p class="sub" style="margin-top:8px">Each team's momentum and state of mind right now, and the measured edge it carries into its next games.</p></div></section>
  <div class="wrap">${demoBanner()}
    <div class="catsum">${["Hot", "Steady", "Cold", "Under pressure", "Coasting"].map(c => `<div style="border-left:4px solid ${CATCOL[c]}"><b>${counts[c] || 0}</b>${c}</div>`).join("")}</div>
    <ul class="mindrank">${rows.map(r => {
      const w = Math.min(50, Math.abs(r.score) / mx * 50);
      const bar = r.score >= 0 ? `left:50%;width:${w}%;background:var(--pos)` : `left:${50 - w}%;width:${w}%;background:var(--neg)`;
      return `<li style="--cc:${CATCOL[r.cat]}"><span class="rk">${r.rank}</span><span>${tlink(r.abbr)}<br><span class="sub small">${h(r.record)} · ${catTag(r.cat)}</span></span>
        <span><span class="mtrack"><span style="${bar}"></span></span><span class="sub small">momentum ${sgn(r.score)}</span></span>
        <ul class="why">${r.why.length ? r.why.map(x => `<li>${h(x)}</li>`).join("") : "<li>nothing unusual</li>"}</ul>
        <span class="edge ${effCls(r.edge)}">${sgn(r.edge)}<small>mind edge, next games</small></span></li>`;
    }).join("")}</ul>
    <p class="note" style="margin-top:16px">Momentum describes; it doesn't predict. Whether hot or cold streaks carry over is measured separately — see "Streak" and "Confidence" on the <a href="#/accuracy">track record</a>.</p></div>`;
}
