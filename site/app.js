"use strict";
const app = document.getElementById("app");
const BANNER = `<p class="banner">Statistical estimates, not advice. Basketball is noisy and the mind even more so — use your own judgement.</p>`;
const EVID = { strong: "strong evidence", moderate: "moderate evidence", weak: "weak evidence", none: "no clear evidence" };
const cache = {};
let version = String(Date.now());
let TEAMS = {};
let META = {};

function get(path) {
  if (!cache[path]) {
    cache[path] = fetch(`data/${path}?v=${encodeURIComponent(version)}`).then(r => {
      if (!r.ok) throw new Error(`${r.status} ${path}`);
      return r.json();
    });
  }
  return cache[path];
}

/* ---------------------------------------------------------------- helpers */
const h = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = p => (p == null ? "–" : `${Math.round(p * 100)}%`);
const fx = (x, d = 1) => (x == null ? "–" : Number(x).toFixed(d));
const sgn = (x, d = 1) => (x == null ? "–" : `${x > 0 ? "+" : x < 0 ? "−" : "±"}${Math.abs(Number(x)).toFixed(d)}`);
const half = x => (Math.round(x * 2) / 2).toFixed(1);
const fmt = o => new Intl.DateTimeFormat("en-GB", o);
const tipFmt = fmt({ weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const timeFmt = fmt({ hour: "2-digit", minute: "2-digit" });
const dayFmt = new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
const longDayFmt = new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" });
const asDay = d => new Date(d + "T12:00:00Z");
const tip = iso => (iso ? tipFmt.format(new Date(iso)) : "");
const tm = iso => (iso ? timeFmt.format(new Date(iso)) : "");
const day = d => (d ? dayFmt.format(asDay(d)) : "");
const longDay = d => (d ? longDayFmt.format(asDay(d)) : "");
const T = ab => TEAMS[ab] || { abbr: ab, short: ab, name: ab, color: "#555", alt: "#999" };
function ago(iso) {
  const m = Math.round((Date.now() - new Date(iso)) / 60000);
  if (m < 60) return `${Math.max(m, 1)} min ago`;
  if (m < 48 * 60) return `${Math.round(m / 60)} h ago`;
  return day(iso.slice(0, 10));
}
function readable(hex) {
  const n = parseInt(String(hex || "#555").slice(1), 16);
  const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  return (0.299 * r + 0.587 * g + 0.114 * b) > 200 ? "#3a3f4a" : hex;
}
function disc(ab, size = "sm") {
  const t = T(ab);
  if (t.logo) return `<span class="disc logo ${size}"><img src="${h(t.logo)}" alt="" loading="lazy"></span>`;
  return `<span class="disc ${size}" style="background:${readable(t.color)}">${h(ab)}</span>`;
}
const tlink = ab => `<a class="tlink" href="#/team/${h(ab)}">${disc(ab, "xs")}<span>${h(T(ab).short)}</span></a>`;
const ev = e => `<span class="pill ${h(e)}">${h(EVID[e] || e)}</span>`;
const effCls = x => (x > 0.05 ? "up" : x < -0.05 ? "down" : "flat");
const fav = c => (c.margin >= 0 ? c.home : c.away);
function spreadTxt(c) {
  const f = fav(c);
  return `${T(f).abbr} −${half(Math.abs(c.margin))}`;
}
function mindTxt(c) {
  if (c.mind == null || Math.abs(c.mind) < 0.05) return "even";
  return `${sgn(Math.abs(c.mind))} ${T(c.mind > 0 ? c.home : c.away).abbr}`;
}
function stypeLabel(s) { return s === 3 ? "Playoffs" : s === 5 ? "Play-in" : "Regular season"; }
function demoBanner() {
  return META.mode === "demo"
    ? `<p class="banner demo">Preview with a simulated league: teams are real, every game, score, player and injury is invented. Real data appears once the site runs on GitHub with the ESPN feed.</p>` : "";
}
function setTitle(t) { document.title = t ? `${t} · Tip-Off Numbers` : "Tip-Off Numbers"; }

/* ---------------------------------------------------------------- pieces */
function strip(winHome, home, away, dark = true) {
  const ph = winHome, pa = 1 - winHome;
  const hc = readable(T(home).color), ac = readable(T(away).color);
  return `<div class="strip grow">
    <div class="strip-bar"><span style="width:${pa * 100}%;background:${dark ? "#fff" : ac};opacity:${dark ? 0.55 + 0.45 * (pa > ph) : 1}"></span><span style="width:${ph * 100}%;background:${dark ? "#fff" : hc};opacity:${dark ? 0.55 + 0.45 * (ph >= pa) : 1}"></span></div>
    <div class="strip-legend"><div><div class="p">${pct(pa)}</div><div class="who">${h(T(away).short)} win</div></div>
    <div><div class="p">${pct(ph)}</div><div class="who">${h(T(home).short)} win</div></div></div></div>`;
}

function fcard(c) {
  const done = c.home_pts != null;
  const live = c.live;
  const rows = [["away", c.away, c.away_rec, 1 - c.win_home, c.away_pts], ["home", c.home, c.home_rec, c.win_home, c.home_pts]];
  const winner = done ? (c.home_pts > c.away_pts ? c.home : c.away) : null;
  const top = done
    ? `<span>${day(c.day)} · Final${c.ot ? ` (${c.ot > 1 ? c.ot : ""}OT)` : ""}</span><span class="res-hit ${c.hit ? "y" : "n"}">${c.kind === "frozen" ? "estimate" : "model check"} ${c.hit ? "✓" : "✗"}</span>`
    : live ? `<span class="live">Live · ${h(live.detail || "")}</span><span>${h(stypeLabel(c.stype))}</span>`
      : `<span>${tip(c.tip)}</span><span>${c.tv ? `<span class="chip tv">National TV</span>` : ""}</span>`;
  const team = ([side, ab, rec, p, pts]) => {
    const lead = !done && p >= 0.5;
    const cls = done ? (ab === winner ? "w" : "l") : "";
    const right = done ? `<span class="pp">${pts}</span>` : live ? `<span class="pp">${live[side + "_pts"] ?? ""}</span>` : `<span class="pp ${lead ? "lead" : ""}">${pct(p)}</span>`;
    return `<div class="fc-team ${cls}">${disc(ab, "sm")}<span class="nm">${h(T(ab).short)}<small>${h(rec || "")}</small></span>${right}</div>`;
  };
  const tags = (c.tags || []).map(t => `<span class="chip">${h(T(t.team).abbr)} · ${h(t.label)}</span>`).join("");
  return `<a class="fcard" href="#/game/${h(c.id)}" style="--hc:${readable(T(c.home).color)};--ac:${readable(T(c.away).color)}">
    <div class="fc-top">${top}</div>${rows.map(team).join("")}
    <div class="fc-exp"><div><b>${done ? `${T(fav(c)).abbr} ${pct(Math.max(c.win_home, 1 - c.win_home))}` : spreadTxt(c)}</b>${done ? "estimate" : "spread est."}</div>
    <div><b>${fx(c.total, 0)}</b>total est.</div><div><b class="m">${mindTxt(c)}</b>mind edge</div></div>
    ${tags ? `<div class="fc-tags">${tags}</div>` : ""}</a>`;
}

function byDay(cards) {
  const m = new Map();
  for (const c of cards) { if (!m.has(c.day)) m.set(c.day, []); m.get(c.day).push(c); }
  return m;
}

function standingsTable(rows, short = false) {
  const cols = short
    ? `<tr><th></th><th>Team</th><th class="n">W</th><th class="n">L</th><th class="n">GB</th><th class="n">Net</th></tr>`
    : `<tr><th></th><th>Team</th><th class="n">W</th><th class="n">L</th><th class="n">Pct</th><th class="n">GB</th><th class="n">Home</th><th class="n">Away</th><th class="n">Conf</th><th class="n">L10</th><th class="n">Strk</th><th class="n">Pt diff</th><th class="n" title="Rating: points better than an average team per game">Net</th><th class="n" title="Last 5 games versus expectation">Conf.</th></tr>`;
  const body = rows.map(r => {
    const cut = r.seed === 6 || r.seed === 10 ? " cut" : "";
    const base = `<td class="pos">${r.seed}</td><td>${tlink(r.abbr)}</td><td class="n">${r.w}</td><td class="n">${r.l}</td>`;
    const rest = short
      ? `<td class="n">${r.gb ? fx(r.gb, 1) : "–"}</td><td class="n">${sgn(r.net)}</td>`
      : `<td class="n">${fx(r.pct, 3).replace(/^0/, "")}</td><td class="n">${r.gb ? fx(r.gb, 1) : "–"}</td><td class="n">${r.home}</td><td class="n">${r.away}</td><td class="n">${r.conf}</td><td class="n">${r.l10}</td><td class="n">${r.streak}</td><td class="n">${sgn(r.pd)}</td><td class="n">${sgn(r.net)}</td><td class="n ${effCls(r.confidence)}">${sgn(r.confidence)}</td>`;
    return `<tr class="z-${r.zone}${cut}">${base}${rest}</tr>`;
  }).join("");
  return `<div class="tscroll"><table>${cols}${body}</table></div>`;
}

/* ---------------------------------------------------------------- home */
async function home() {
  const [sch, hm, st, acc] = await Promise.all([get("schedule.json"), get("home.json"), get("standings.json"), get("accuracy.json")]);
  setTitle("");
  const up = sch.upcoming.filter(c => !c.live);
  const days = byDay(sch.upcoming);
  const [d1, d2] = [...days.keys()];
  const soon = sch.upcoming.filter(c => c.day === d1);
  const feat = [...soon].sort((a, b) => Math.abs(b.mind) - Math.abs(a.mind))[0] || up[0];
  const featHtml = feat ? `<a class="feature" href="#/game/${h(feat.id)}">
      <div class="feature-top"><span>Spotlight · ${tip(feat.tip)}</span><span>biggest mental edge on the next slate</span></div>
      <div class="feature-teams"><div class="t">${disc(feat.away, "md")}<span>${h(T(feat.away).short)}</span></div><div class="x">at</div><div class="t a"><span>${h(T(feat.home).short)}</span>${disc(feat.home, "md")}</div></div>
      ${strip(feat.win_home, feat.home, feat.away)}
      <div class="feature-exp"><span>Spread <b>${spreadTxt(feat)}</b></span><span>Total <b>${fx(feat.total, 0)}</b></span><span>Mind edge <b class="m">${mindTxt(feat)}</b></span></div></a>` : "";
  const lastDay = sch.results.length ? sch.results[0].day : null;
  const last = sch.results.filter(c => c.day === lastDay);
  const resultsHtml = last.map(c => {
    const hw = c.home_pts > c.away_pts;
    return `<li><a href="#/game/${h(c.id)}"><span><span class="r-t ${hw ? "l" : ""}">${disc(c.away, "xs")}${h(T(c.away).short)}</span><span class="r-t ${hw ? "" : "l"}">${disc(c.home, "xs")}${h(T(c.home).short)}</span></span>
      <span class="r-s"><span class="${hw ? "" : "w"}">${c.away_pts}</span><br><span>${c.home_pts}</span></span>
      <span class="r-e">${c.kind === "frozen" ? "Estimate" : "Model check"}: ${T(fav(c)).abbr} ${pct(Math.max(c.win_home, 1 - c.win_home))} <span class="res-hit ${c.hit ? "y" : "n"}">${c.hit ? "✓" : "✗"}</span></span></a></li>`;
  }).join("");
  const spots = (hm.spots || []).map(s => `<li><a href="#/game/${h(s.game)}">${disc(s.team, "sm")}
      <span><span class="g">${h(T(s.team).short)} · ${h(s.label)}</span><br><span class="sub">${h(T(s.away).short)} at ${h(T(s.home).short)} · ${tip(s.tip)}</span></span>
      <span class="eff ${effCls(s.pts)} num">${sgn(s.pts)} pts</span></a></li>`).join("");
  const rec = acc.live && acc.live.n ? acc.live : null;
  const chk = acc.checks;
  const bt = acc.backtest && acc.backtest.test;
  app.innerHTML = `<section class="hero home-hero court"><div class="wrap">
    <h1>Every NBA game, <em>by the numbers</em> — and <i>in the head</i>.</h1>
    <p class="lede">Win chances, scores and totals from team ratings, rest, travel and who is missing — plus a psychological layer (streaks, bounce-backs, revenge, letdowns, stakes) whose size is measured from past games, not assumed. Every estimate shows its inputs, its uncertainty and its track record.</p>
    ${featHtml}</div></section>
  <div class="wrap">${demoBanner()}${BANNER}
    ${d1 ? `<section><h2>${h(longDay(d1))} <span class="sub">${soon.length} game${soon.length > 1 ? "s" : ""} · US date, tip-off times in your time zone</span></h2><div class="cards">${soon.map(fcard).join("")}</div></section>` : `<p class="empty">No games scheduled in the next two weeks.</p>`}
    ${spots ? `<section class="section"><h2 class="mind">Mind games <span class="sub">the psychological spots worth most in the coming days</span></h2><ul class="spotlist">${spots}</ul></section>` : ""}
    ${d2 ? `<section class="section"><h2>${h(longDay(d2))}</h2><div class="cards">${days.get(d2).map(fcard).join("")}</div><p class="more" style="margin-top:14px"><a class="btn" href="#/games">All games</a></p></section>` : ""}
    ${last.length ? `<section class="section"><h2>${h(longDay(lastDay))} <span class="sub">results</span></h2><ul class="results">${resultsHtml}</ul></section>` : ""}
    <section class="section duo">${["East", "West"].map(cf => `<div class="panel mini-t"><div class="mt-head"><h3>${cf}</h3><a href="#/standings">Full table</a></div>${standingsTable(st[cf].slice(0, 10), true).replace('class="tscroll"', 'class=""')}</div>`).join("")}</section>
    <section class="section"><h2>Track record</h2><div class="panel proof">
      ${rec ? `<div><b>${pct(rec.hit)}</b><span>winners called, ${rec.n} frozen estimates</span></div><div><b>${fx(rec.mae_m, 1)}</b><span>points average miss on the margin</span></div>`
            : `<div><b>0</b><span>frozen estimates scored so far — the live record starts with the first games after launch</span></div>`}
      ${chk ? `<div><b>${pct(chk.hit)}</b><span>winners in this season's ${chk.n} model checks</span></div>` : ""}
      ${bt ? `<div><b>${pct(bt.full.hit)}</b><span>winners in the ${acc.backtest.test_season - 1}-${String(acc.backtest.test_season).slice(2)} backtest (${bt.n} games)</span></div>` : ""}
      <div><a class="btn" href="#/accuracy">See the track record</a></div></div></section>
  </div>`;
}

/* ---------------------------------------------------------------- games */
async function games(sel) {
  const sch = await get("schedule.json");
  setTitle("Games");
  const all = [...sch.results].reverse().concat(sch.upcoming);
  const days = byDay(all);
  const keys = [...days.keys()];
  const firstUp = sch.upcoming.length ? sch.upcoming[0].day : keys[keys.length - 1];
  const cur = sel && days.has(sel) ? sel : firstUp;
  const i = keys.indexOf(cur);
  const win = keys.slice(Math.max(0, i - 3), i + 6);
  const list = days.get(cur) || [];
  app.innerHTML = `<section class="hero court"><div class="wrap"><h1>Games</h1>
    <p class="sub" style="margin-top:8px">Estimates for the next two weeks, updated until tip-off and then frozen. Results for the last three weeks.</p>
    <nav class="tabs" style="margin-top:16px">${i > 3 ? `<a class="tab" href="#/games/${keys[Math.max(0, i - 7)]}">←</a>` : ""}${win.map(k => `<a class="tab" href="#/games/${k}" aria-current="${k === cur}">${day(k)}</a>`).join("")}${i + 6 < keys.length ? `<a class="tab" href="#/games/${keys[Math.min(keys.length - 1, i + 7)]}">→</a>` : ""}</nav>
  </div></section><div class="wrap">${demoBanner()}
    <h2>${h(longDay(cur))} <span class="sub">${list.length} game${list.length === 1 ? "" : "s"}</span></h2>
    <div class="cards">${list.map(fcard).join("")}</div></div>`;
}

/* ---------------------------------------------------------------- standings */
async function standings() {
  const st = await get("standings.json");
  setTitle("Standings");
  app.innerHTML = `<section class="hero court"><div class="wrap"><h1>Standings</h1><p class="sub" style="margin-top:8px">${h(st.season)} regular season. Net = rating, points better than an average team per game. Conf. = last five games versus what the ratings expected.</p></div></section>
  <div class="wrap">${demoBanner()}${["East", "West"].map(cf => `<section class="section" style="margin-top:0;margin-bottom:34px"><h2>${cf}ern Conference</h2>${standingsTable(st[cf])}</section>`).join("")}
  <div class="legend"><span><i style="background:var(--pos)"></i>Playoff spots (1-6)</span><span><i style="background:var(--body)"></i>Play-in (7-10)</span></div></div>`;
}

/* ---------------------------------------------------------------- teams */
async function teams() {
  const list = await get("teams.json");
  setTitle("Teams");
  const conf = cf => list.filter(t => t.conf === cf).sort((a, b) => a.name.localeCompare(b.name));
  app.innerHTML = `<section class="hero court"><div class="wrap"><h1>Teams</h1></div></section><div class="wrap">${demoBanner()}
    ${["East", "West"].map(cf => `<section style="margin-bottom:30px"><h2>${cf}</h2><ul class="teamgrid">${conf(cf).map(t => `<li><a href="#/team/${t.abbr}" style="--tc:${readable(t.color)}">${disc(t.abbr, "sm")}${h(t.name)}<span class="sub">${h(t.record)}</span></a></li>`).join("")}</ul></section>`).join("")}</div>`;
}

function respRow(label, p, help) {
  if (!p || !p.n) return `<li><span>${label}<br><small>${help}</small></span><span class="sub">no games</span><span></span></li>`;
  const v = p.vs_exp, w = Math.min(50, Math.abs(v) / 8 * 50);
  const bar = v >= 0 ? `left:50%;width:${w}%;background:var(--pos)` : `left:${50 - w}%;width:${w}%;background:var(--neg)`;
  return `<li><span>${label}<br><small>${help} · ${p.n} game${p.n > 1 ? "s" : ""}${p.n < 15 ? " (small sample)" : ""}</small></span><span class="track"><span style="${bar}"></span></span><span class="v ${effCls(v)}">${sgn(v)}</span></li>`;
}

async function team(ab) {
  const t = await get(`team/${ab}.json`);
  setTitle(t.name);
  const col = readable(t.color);
  const form = t.form.map(r => `<i class="${r.win ? "W" : "L"}" title="${r.home ? "vs" : "at"} ${h(T(r.opp).short)} ${sgn(r.margin, 0)}">${r.win ? "W" : "L"}</i>`).join("");
  const m = t.mind;
  const inj = t.injuries.length ? `<ul class="spots">${t.injuries.map(i => `<li><div class="sh"><b>${h(i.name)}</b><span class="pill ${i.weight >= 1 ? "weak" : "none"}">${h(i.status)}</span></div>${i.detail ? `<p>${h(i.detail)}</p>` : ""}</li>`).join("")}</ul>` : `<p class="sub">Nobody listed.</p>`;
  const roster = t.roster.length ? `<div class="tscroll"><table><tr><th>Player</th><th class="n">GP</th><th class="n">Min</th><th class="n">Pts</th><th class="n">Reb</th><th class="n">Ast</th><th>Share of production</th></tr>
    ${t.roster.map(p => `<tr><td>${h(p.name)}</td><td class="n">${p.gp}</td><td class="n">${fx(p.mpg)}</td><td class="n">${fx(p.ppg)}</td><td class="n">${fx(p.rpg)}</td><td class="n">${fx(p.apg)}</td><td>${p.share ? `<span class="share"><span style="width:${Math.min(100, p.share * 300)}%"></span></span>${pct(p.share)}` : `<span class="sub">not a current regular</span>`}</td></tr>`).join("")}</table></div>` : `<p class="sub">No box scores yet.</p>`;
  app.innerHTML = `<section class="thero" style="background:linear-gradient(110deg, ${col}, color-mix(in srgb, ${col} 55%, #0b1426))"><div class="wrap">${disc(t.abbr, "lg")}
    <div><h1>${h(t.name)}</h1><p class="meta">${h(t.conf)}ern Conference · ${h(t.div)}</p>
    <div class="facts"><div><b>${h(t.record)}</b>record</div><div><b>${t.seed ?? "–"}</b>seed</div><div><b>${sgn(t.net)}</b>net rating (#${t.net_rank})</div>
    <div><b>#${t.off_rank}</b>offence</div><div><b>#${t.def_rank}</b>defence</div><div><b>${t.streak ? (t.streak > 0 ? "W" : "L") + Math.abs(t.streak) : "–"}</b>streak</div></div></div></div></section>
  <div class="wrap">${demoBanner()}
    <section class="grid2">
      <div class="panel mind"><h3>How they respond</h3><p class="sub small">Average points versus what the ratings expected, in each situation over the stored seasons. Descriptive only — small samples are noisy, and the estimates use league-wide effects, not these.</p>
        <ul class="resp">${respRow("After a loss", m.after_loss, "next game")}${respRow("After a 20+ point loss", m.after_blowout, "next game")}${respRow("After a win", m.after_win, "next game")}
        ${respRow("On a back-to-back", m.b2b, "second night")}${respRow("Revenge games", m.revenge, "lost the last meeting")}${respRow("Long road trips", m.road_long, "4th+ straight road game")}</ul>
        <p class="sub small" style="margin-top:10px">Close games (5 points or fewer): <b>${m.close.w}-${m.close.n - m.close.w}</b></p></div>
      <div class="panel"><h3>Form</h3><p class="sub small">Last ${t.form.length} games, newest right. Confidence: ${sgn(t.confidence)} points a game versus expectation over the last five.</p>
        <div class="form">${form}</div>
        <ul class="spots" style="margin-top:12px">${t.form.slice(-5).reverse().map(r => `<li><div class="sh"><span>${r.home ? "vs" : "at"} ${h(T(r.opp).short)} · ${day(r.day)}</span><span class="eff ${r.win ? "up" : "down"}">${r.win ? "W" : "L"} ${sgn(r.margin, 0)}</span></div>${r.vs_exp != null ? `<p>${sgn(r.vs_exp)} versus expected margin</p>` : ""}</li>`).join("")}</ul></div>
    </section>
    ${t.upcoming.length ? `<section class="section"><h2>Next games</h2><div class="cards">${t.upcoming.map(fcard).join("")}</div></section>` : ""}
    ${t.results.length ? `<section class="section"><h2>Recent results</h2><div class="cards">${t.results.map(fcard).join("")}</div></section>` : ""}
    <section class="section grid2"><div><h2>Rotation</h2>${roster}</div><div><h2 class="body">Injury list</h2><div class="panel">${inj}</div></div></section>
  </div>`;
}

/* ---------------------------------------------------------------- game */
function marginChart(e, home, away, actual) {
  const W = 420, H = 120, m = e.margin, sd = e.sd_margin, lo = -36, hi = 36;
  const x = v => ((v - lo) / (hi - lo)) * W;
  const pdf = v => Math.exp(-0.5 * ((v - m) / sd) ** 2);
  let ptsH = "", ptsA = "";
  for (let v = lo; v <= hi; v += 0.5) {
    const y = H - 22 - pdf(v) * (H - 34);
    if (v >= 0) ptsH += `${x(v)},${y} `; else ptsA += `${x(v)},${y} `;
  }
  const base = H - 22;
  const ac = readable(T(away).color), hc = readable(T(home).color);
  const act = actual != null ? `<line x1="${x(Math.max(lo, Math.min(hi, actual)))}" x2="${x(Math.max(lo, Math.min(hi, actual)))}" y1="4" y2="${base}" stroke="var(--ink)" stroke-width="2" stroke-dasharray="3 3"/><text x="${x(Math.max(lo, Math.min(hi, actual))) + 4}" y="14">actual</text>` : "";
  return `<svg class="mchart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Spread of likely margins">
    <polygon points="${x(lo)},${base} ${ptsA} ${x(0)},${base}" fill="${ac}" opacity=".75"/>
    <polygon points="${x(0)},${base} ${ptsH} ${x(hi)},${base}" fill="${hc}" opacity=".75"/>
    <line x1="0" x2="${W}" y1="${base}" y2="${base}" stroke="var(--line)"/>
    ${[-30, -20, -10, 0, 10, 20, 30].map(v => `<text x="${x(v)}" y="${H - 6}" text-anchor="middle">${v === 0 ? "0" : Math.abs(v)}</text>`).join("")}
    <text x="4" y="12">← ${h(T(away).abbr)} wins by</text><text x="${W - 4}" y="12" text-anchor="end">${h(T(home).abbr)} wins by →</text>${act}</svg>`;
}

function gaugeSvg(v) {
  const c = Math.max(-4, Math.min(4, v || 0));
  const ang = Math.PI * (1 - (c + 4) / 8);
  const cx = 100, cy = 92, r = 74;
  const px = cx + r * 0.86 * Math.cos(ang), py = cy - r * 0.86 * Math.sin(ang);
  const arc = (a0, a1, col) => {
    const p0 = [cx + r * Math.cos(a0), cy - r * Math.sin(a0)], p1 = [cx + r * Math.cos(a1), cy - r * Math.sin(a1)];
    return `<path d="M${p0[0]} ${p0[1]} A${r} ${r} 0 0 1 ${p1[0]} ${p1[1]}" stroke="${col}" stroke-width="12" fill="none" stroke-linecap="butt"/>`;
  };
  return `<svg viewBox="0 0 200 112" role="img" aria-label="Mind gauge ${sgn(v)} points">
    ${arc(Math.PI, Math.PI * 0.62, "var(--neg)")}${arc(Math.PI * 0.62, Math.PI * 0.38, "var(--bar-bg)")}${arc(Math.PI * 0.38, 0, "var(--pos)")}
    <line x1="${cx}" y1="${cy}" x2="${px}" y2="${py}" stroke="var(--mind)" stroke-width="3.5" stroke-linecap="round"/><circle cx="${cx}" cy="${cy}" r="6" fill="var(--mind)"/>
    <text x="18" y="108">−4</text><text x="176" y="108">+4</text><text class="gv" x="${cx}" y="${cy - 26}" text-anchor="middle">${sgn(v)}</text></svg>`;
}

function spotList(list, layer, teamShort) {
  if (!list.length) return `<p class="none-note">${layer === "mind" ? `No psychological spot for the ${h(teamShort)}.` : `Nothing notable for the ${h(teamShort)}.`}</p>`;
  return `<ul class="spots">${list.map(s => `<li><div class="sh"><b>${h(s.label)}</b><span class="eff ${effCls(s.pts)}">${sgn(s.pts)} pts</span></div>
    <p>${h(s.text)}</p><div class="hist">History: ${s.per == null ? "–" : `${sgn(s.per, 2)} pts ${h(s.means || "")}`} · ${ev(s.evidence)}</div></li>`).join("")}</ul>`;
}

function buildRows(g) {
  const e = g.est, H = T(g.home.abbr).abbr, A = T(g.away.abbr).abbr;
  const rows = [["Base ratings", "var(--base)", e.base.margin], ["Rest, travel, availability", "var(--body)", e.physical.margin], ["Psychological spots", "var(--mind)", e.mind.margin], ["Estimate", "var(--ink)", e.margin]];
  const scale = Math.max(8, ...rows.map(r => Math.abs(r[2] || 0)));
  return `<ul class="build">${rows.map(([lab, col, v]) => {
    const w = Math.min(50, Math.abs(v || 0) / scale * 50);
    const st = v >= 0 ? `left:50%;width:${w}%` : `left:${50 - w}%;width:${w}%`;
    const txt = Math.abs(v || 0) < 0.05 ? "even" : `${v > 0 ? H : A} ${sgn(Math.abs(v))}`;
    return `<li><span class="lab"><i style="background:${col}"></i>${lab}</span><span class="track"><span style="${st};background:${col}"></span></span><span class="v">${txt}</span></li>`;
  }).join("")}</ul><div class="ends"><span>← ${h(A)}</span><span>${h(H)} →</span></div>`;
}

function linesList(lines, actual, label) {
  return `<ul class="lines">${lines.map(l => {
    const cls = actual == null ? "" : ((actual > l.line) === (l.over >= 0.5) ? "hit" : "miss");
    return `<li class="${cls}"><span>${label} ${l.line}</span><span class="bar"><span style="width:${l.over * 100}%"></span></span><span class="pct">${pct(l.over)}</span></li>`;
  }).join("")}</ul>`;
}

async function game(id) {
  const g = await get(`game/${id}.json`);
  const H = g.home.abbr, A = g.away.abbr;
  setTitle(`${T(A).short} at ${T(H).short}`);
  const e = g.est, res = g.result;
  const hc = readable(g.home.color), ac = readable(g.away.color);
  const kind = { estimate: "Estimate · updates until tip-off", frozen: "Estimate frozen at tip-off", check: "Model check · made after the fact, not in the track record" }[g.kind] || "";
  const center = res ? `<div class="score">${res.away_pts}–${res.home_pts}</div><div class="vs">Final${res.ot ? ` · ${res.ot > 1 ? res.ot : ""}OT` : ""}</div>`
    : g.live ? `<div class="score">${g.live.away_pts ?? 0}–${g.live.home_pts ?? 0}</div><div class="vs"><span class="live">${h(g.live.detail || "Live")}</span></div>`
      : `<div class="vs"><b>${tm(g.tip)}</b>${g.tip ? new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short" }).format(new Date(g.tip)) : day(g.day)}</div>`;
  const series = g.stype === 3 && g.home.series ? ` · series ${h(g.home.abbr)} ${h(g.home.series)}` : "";
  const sides = g.sides;
  const am = res ? res.home_pts - res.away_pts : null, at = res ? res.home_pts + res.away_pts : null;
  const scored = res ? `<p class="call"><b>${g.kind === "check" ? "Model check" : "Estimate"}:</b> ${h(T(e.margin >= 0 ? H : A).short)} by ${fx(Math.abs(e.margin))}, total ${fx(e.total, 0)}. <b>Result:</b> ${h(T(am > 0 ? H : A).short)} by ${Math.abs(am)}, total ${at}. Winner ${g.scored.hit ? "✓" : "✗"} · margin miss ${fx(Math.abs(g.scored.err_margin))} · total miss ${fx(Math.abs(g.scored.err_total))}</p>` : "";
  const mindCol = (side, ab) => {
    const t = g[side];
    return `<div class="mindcol"><h3>${disc(ab, "sm")}${h(T(ab).short)}</h3>
      <div class="gauge">${gaugeSvg(g.gauge[side])}</div>
      <div class="minifacts"><span><b>${t.streak ? (t.streak > 0 ? "W" : "L") + Math.abs(t.streak) : "–"}</b>streak</span><span><b class="${effCls(t.confidence)}">${sgn(t.confidence)}</b>last 5 vs expected</span>${t.series ? `<span><b>${h(t.series)}</b>series</span>` : ""}</div>
      ${t.form && t.form.length ? `<div class="form sm" style="margin-bottom:8px">${t.form.map(f => `<i class="${f[0]}" title="${f[0]} ${sgn(f[1], 0)} v ${h(f[2])}">${f[0]}</i>`).join("")}</div>` : ""}
      ${spotList(sides[side].mind, "mind", T(ab).short)}</div>`;
  };
  const bodyCol = (side, ab) => {
    const t = g[side];
    const inj = (t.injuries || []).length ? `<div class="hist" style="margin-top:8px">Injury list: ${t.injuries.map(i => `${h(i.name)} (${h(i.status)})`).join(", ")}</div>` : "";
    return `<div><h3>${disc(ab, "sm")} ${h(T(ab).short)}</h3>
      <div class="minifacts"><span><b>${t.b2b ? "0" : Math.min(t.rest, 9)}</b>days rest</span><span><b>${(t.km || 0).toLocaleString("en-GB")}</b>km travelled</span><span><b>${pct(t.missing)}</b>production missing</span></div>
      ${spotList(sides[side].physical, "body", T(ab).short)}${inj}</div>`;
  };
  const others = Object.entries(e.others || {}).map(([k, o]) => {
    const act = res && res.box ? (res.box.home[k] ?? null) + (res.box.away[k] ?? null) : null;
    return `<div class="panel"><h3>${h(o.label)}</h3><div class="stat-row"><span class="stat-big">${fx(o.total)}</span><span class="range">${h(T(A).abbr)} ${fx(o.away)} · ${h(T(H).abbr)} ${fx(o.home)}</span>${act != null && !isNaN(act) ? `<span class="actual">actual ${act}</span>` : ""}</div>
      ${linesList(o.lines, act, "Over")}<p class="sub small" style="margin-top:8px">Base ratings only.</p></div>`;
  }).join("");
  const box = res && res.box && res.box.home.fgm != null ? (() => {
    const b = res.box, rows = [["FG%", b.away.fgm / b.away.fga * 100, b.home.fgm / b.home.fga * 100, 1], ["3PT made", b.away.tpm, b.home.tpm, 0], ["Rebounds", b.away.reb, b.home.reb, 0], ["Assists", b.away.ast, b.home.ast, 0], ["Turnovers", b.away.tov, b.home.tov, 0], ["Free throws", b.away.ftm, b.home.ftm, 0]];
    return `<ul class="cmp">${rows.map(([l, va, vh, d]) => `<li><span class="lab">${l}</span><span class="v">${fx(va, d)}</span><span class="b"><span style="flex:${va};background:${ac}"></span><span style="flex:${vh};background:${hc}"></span></span><span class="v r">${fx(vh, d)}</span></li>`).join("")}</ul>`;
  })() : "";
  const tops = res && res.top ? `<div class="grid2">${[["away", A], ["home", H]].map(([s, ab]) => `<div class="panel"><h3>${disc(ab, "xs")} ${h(T(ab).short)} top scorers</h3><ul class="spots">${res.top[s].map(p => `<li><div class="sh"><span>${h(p.name)}</span><span class="num">${p.pts} pts · ${p.reb} reb · ${p.ast} ast</span></div></li>`).join("")}</ul></div>`).join("")}</div>` : "";
  const news = g.kind === "estimate" && !g.news ? `<p class="note">Team news is only read for games in the next three days; availability here assumes full squads.</p>` : "";
  app.innerHTML = `<section class="mhero" style="background:linear-gradient(100deg, ${ac} 0%, color-mix(in srgb, ${ac} 70%, #0b1426) 46%, color-mix(in srgb, ${hc} 70%, #0b1426) 54%, ${hc} 100%)"><div class="wrap">
    <div class="mhead"><div class="mteam">${disc(A, "lg")}<a href="#/team/${A}">${h(T(A).short)}</a><span class="rec">${h(g.away.record)}${g.away.seed ? ` · ${g.away.conf} #${g.away.seed}` : ""}</span></div>
      <div>${center}</div>
      <div class="mteam home">${disc(H, "lg")}<a href="#/team/${H}">${h(T(H).short)}</a><span class="rec">${h(g.home.record)}${g.home.seed ? ` · ${g.home.conf} #${g.home.seed}` : ""}</span></div></div>
    ${strip(e.win_home, H, A)}
    <p class="mmeta"><span class="pill">${h(kind)}</span><span>${tip(g.tip)}</span><span>${h(stypeLabel(g.stype))}${series}</span>${g.venue ? `<span>${h(g.venue)}</span>` : ""}${g.national_tv ? `<span>National TV</span>` : ""}${g.rivalry ? `<span>Division rivals</span>` : ""}</p>
  </div></section>
  <div class="wrap">${demoBanner()}${BANNER}${scored}
    <section class="grid">
      <div class="panel"><h3>Score estimate</h3><div class="teampts"><div>${disc(A, "sm")}<b>${fx(e.away_pts, 0)}</b></div><div>${disc(H, "sm")}<b>${fx(e.home_pts, 0)}</b></div></div>
        ${marginChart(e, H, A, am)}<p class="sub small">Likely margins (±${fx(e.sd_margin)} points is one standard deviation).</p>
        <ul class="lines">${e.spread_lines.map(l => `<li class="${am == null ? "" : ((am > l.line) === (l.home_cover >= 0.5) ? "hit" : "miss")}"><span>${h(T(H).abbr)} by ${l.line}+</span><span class="bar"><span style="width:${l.home_cover * 100}%"></span></span><span class="pct">${pct(l.home_cover)}</span></li>`).join("")}</ul></div>
      <div class="panel"><h3>Total points</h3><div class="stat-row"><span class="stat-big">${fx(e.total, 0)}</span><span class="range">80% range ${fx(e.total - 1.28 * e.sd_total, 0)}–${fx(e.total + 1.28 * e.sd_total, 0)}</span>${at != null ? `<span class="actual">actual ${at}</span>` : ""}</div>
        ${linesList(e.total_lines, at, "Over")}
        <p class="sub small" style="margin-top:10px">Base ${fx(e.base.total, 0)} · physical ${sgn(e.physical.total)} · mind ${sgn(e.mind.total)}</p></div>
      <div class="panel"><h3>Why</h3><ul class="why">${g.reasoning.map(r => `<li>${h(r)}</li>`).join("")}</ul>${g.analyst ? `<p class="call"><b>Analyst view:</b> ${h(g.analyst.text || g.analyst.overall || "")}</p>` : ""}</div>
    </section>
    <section class="section"><h2>How the number was built <span class="sub">points on the margin</span></h2><div class="panel">${buildRows(g)}
      <p class="sub small" style="margin-top:12px">Win chance with the psychological layer: <b>${pct(Math.max(e.win_home, 1 - e.win_home))}</b> ${h(T(e.win_home >= 0.5 ? H : A).abbr)} · without it: <b>${pct(e.win_home_nomind >= 0.5 ? e.win_home_nomind : 1 - e.win_home_nomind)}</b> ${h(T(e.win_home_nomind >= 0.5 ? H : A).abbr)} · plain averages: <b>${pct(Math.max(e.baseline.win_home, 1 - e.baseline.win_home))}</b> ${h(T(e.baseline.win_home >= 0.5 ? H : A).abbr)}</p></div></section>
    <section class="section"><h2 class="mind">The mental game <span class="sub">each team's psychological spots, sized by what they have been worth in past games</span></h2>
      <div class="panel mind grid2">${mindCol("away", A)}${mindCol("home", H)}</div></section>
    <section class="section"><h2 class="body">Body: rest, travel, availability</h2>${news}<div class="panel body grid2">${bodyCol("away", A)}${bodyCol("home", H)}</div></section>
    ${box ? `<section class="section"><h2>Box score</h2>${box}</section>` : ""}
    ${tops ? `<section class="section">${tops}</section>` : ""}
    ${others ? `<section class="section"><h2>Other numbers</h2><div class="grid">${others}</div></section>` : ""}
    ${g.made_at ? `<p class="sub small section">Estimate made ${ago(g.made_at)}.</p>` : ""}
  </div>`;
}

/* ---------------------------------------------------------------- accuracy */
function calibSvg(cal) {
  if (!cal || !cal.length) return "";
  const W = 310, H = 220, p = 38, x = v => p + (v - 0.5) / 0.5 * (W - 2 * p), y = v => H - p - (v - 0.3) / 0.7 * (H - 2 * p);
  return `<svg class="calib" viewBox="0 0 ${W} ${H}"><line x1="${x(.5)}" y1="${y(.5)}" x2="${x(1)}" y2="${y(1)}" stroke="var(--line)" stroke-width="2" stroke-dasharray="4 4"/>
    ${cal.map(c => `<circle cx="${x(c.p)}" cy="${y(c.hit)}" r="${3 + Math.sqrt(c.n) / 2}" fill="var(--base)" opacity=".75"><title>${pct(c.p)} said, ${pct(c.hit)} happened (${c.n})</title></circle>`).join("")}
    <line x1="${p}" y1="${H - p}" x2="${W - p}" y2="${H - p}" stroke="var(--muted)"/><line x1="${p}" y1="${p}" x2="${p}" y2="${H - p}" stroke="var(--muted)"/>
    ${[0.5, 0.6, 0.7, 0.8, 0.9, 1].map(v => `<text x="${x(v)}" y="${H - p + 14}" text-anchor="middle">${pct(v)}</text>`).join("")}
    ${[0.4, 0.6, 0.8, 1].map(v => `<text x="${p - 4}" y="${y(v) + 4}" text-anchor="end">${pct(v)}</text>`).join("")}
    <text x="${W / 2}" y="${H - 2}" text-anchor="middle">favourite's estimated chance</text></svg>`;
}

function duel(rows, key, lowerBetter, d = 3) {
  const vals = rows.map(r => r[1] && r[1][key]).filter(v => v != null);
  if (!vals.length) return "";
  const mx = Math.max(...vals), mn = Math.min(...vals);
  return `<div class="duel">${rows.filter(r => r[1] && r[1][key] != null).map(([lab, o, col]) => {
    const v = o[key];
    const w = mx === mn ? 80 : 30 + 70 * (lowerBetter ? (mx - v) / (mx - mn) : (v - mn) / (mx - mn));
    return `<div class="row"><span>${lab}</span><span class="bar" style="width:${w}%;background:${col}"></span><span class="d">${key === "hit" ? pct(v) : fx(v, d)}</span></div>`;
  }).join("")}</div>`;
}

function factorTable(f, target) {
  const rows = f.filter(r => r.target === target);
  return `<div class="tscroll"><table><tr><th>Factor</th><th>Per unit</th><th class="n">Points</th><th class="n">±</th><th class="n">Games</th><th>Evidence</th></tr>
    ${rows.map(r => `<tr><td><span class="mk" style="background:${r.layer === "mind" ? "var(--mind)" : "var(--body)"}"></span>${h(r.label)}</td><td class="sub small">${h(r.means)}</td><td class="n ${effCls(r.pts)}">${sgn(r.pts, 2)}</td><td class="n">${r.se == null ? "–" : fx(r.se, 2)}</td><td class="n">${r.n.toLocaleString("en-GB")}</td><td>${ev(r.evidence)}</td></tr>`).join("")}</table></div>`;
}

async function accuracy() {
  const a = await get("accuracy.json");
  setTitle("Track record");
  const bt = a.backtest;
  let verdict = "";
  if (bt && bt.test) {
    const d = bt.test.no_mind.brier - bt.test.full.brier;
    const dm = bt.test.no_mind.mae_margin - bt.test.full.mae_margin;
    verdict = `<p class="verdict"><b>Does the psychological layer help?</b> In the ${bt.test_season - 1}-${String(bt.test_season).slice(2)} test season it ${d > 0.0005 ? "improved" : d < -0.0005 ? "worsened" : "barely changed"} the win-chance score (Brier ${fx(bt.test.no_mind.brier, 4)} → ${fx(bt.test.full.brier, 4)}) and ${dm >= 0 ? "cut" : "added to"} the average margin miss by ${fx(Math.abs(dm), 2)} points. Its factors are sized from past games and shrunk towards zero, so a spot that history doesn't support can't move the estimate much.</p>`;
  }
  const rowsFor = o => o ? [["Full model", o.full || o, "var(--ball)"], ["Without psychology", o.no_mind || (o.brier_nomind != null ? { brier: o.brier_nomind, mae_margin: o.mae_m_nomind } : null), "var(--mind)"], ["Base ratings only", o.base_only, "var(--base)"], ["Plain averages", o.plain_average || (o.brier_base != null ? { brier: o.brier_base, mae_margin: o.mae_m_base, mae_total: o.mae_t_base } : null), "var(--muted)"]] : [];
  const liveO = a.live ? { full: { brier: a.live.brier, hit: a.live.hit, mae_margin: a.live.mae_m, mae_total: a.live.mae_t }, no_mind: { brier: a.live.brier_nomind, mae_margin: a.live.mae_m_nomind }, plain_average: { brier: a.live.brier_base, mae_margin: a.live.mae_m_base, mae_total: a.live.mae_t_base } } : null;
  const chkO = a.checks ? { full: { brier: a.checks.brier, hit: a.checks.hit, mae_margin: a.checks.mae_m, mae_total: a.checks.mae_t }, no_mind: { brier: a.checks.brier_nomind, mae_margin: a.checks.mae_m_nomind }, plain_average: { brier: a.checks.brier_base, mae_margin: a.checks.mae_m_base, mae_total: a.checks.mae_t_base } } : null;
  const block = (title, o, n, note, cal) => o ? `<section class="section"><h2>${title} <span class="sub">${n} games</span></h2>${note ? `<p class="sub">${note}</p>` : ""}
    <div class="grid"><div class="panel"><h3>Win chances</h3><p class="sub small">Brier score, lower is better</p>${duel(rowsFor(o), "brier", true, 4)}<p class="sub small" style="margin-top:12px">Winners called</p>${duel(rowsFor(o), "hit", false)}</div>
    <div class="panel"><h3>Margin</h3><p class="sub small">Average miss in points, lower is better</p>${duel(rowsFor(o), "mae_margin", true, 2)}<p class="sub small" style="margin-top:12px">Total points, average miss</p>${duel(rowsFor(o), "mae_total", true, 2)}</div>
    ${cal ? `<div class="panel"><h3>Calibration</h3><p class="sub small">When the favourite was given X%, how often did it win? Dots on the line = honest chances.</p>${calibSvg(cal)}</div>` : ""}</div></section>` : "";
  app.innerHTML = `<section class="hero court"><div class="wrap"><h1>Track record</h1><p class="sub" style="margin-top:8px">Every estimate is frozen at tip-off and scored after the final buzzer, against simpler methods — including the same model without its psychological layer.</p></div></section>
  <div class="wrap">${demoBanner()}${verdict}
    ${a.live ? block("Live record", liveO, a.live.n, "Estimates frozen before tip-off.", a.live.calibration) : `<section><h2>Live record</h2><p class="note">No frozen estimates have been scored yet. The record starts with the first games after the site goes live; nothing is ever added afterwards.</p></section>`}
    ${a.checks ? block("This season's model checks", chkO, a.checks.n, "Walk-forward: base ratings from games before each week, factor sizes from earlier seasons. Made after the fact, so not part of the live record.", a.checks.calibration) : ""}
    ${bt && bt.test ? block(`Backtest: ${bt.test_season - 1}-${String(bt.test_season).slice(2)} season`, bt.test, bt.test.n, `Settings tuned on ${bt.tune_season - 1}-${String(bt.tune_season).slice(2)}, tested once on the next season, walk-forward by week. Half-life ${bt.tuned.half_life} days, last-season weight ${bt.tuned.carry}.`) : ""}
    <section class="section"><h2>What each factor is worth <span class="sub">measured on ${a.effects_games.toLocaleString("en-GB")} games</span></h2>
      <p class="sub">Points on the margin for the team in that spot, from one penalised regression of what the base ratings missed on all factors together. ± is the standard error.</p>
      ${factorTable(a.factors, "margin")}<h3 style="margin-top:22px">Effects on total points</h3>${factorTable(a.factors, "total")}</section>
    ${a.recent && a.recent.length ? `<section class="section"><h2>Latest scored</h2><div class="tscroll"><table><tr><th>Day</th><th>Game</th><th class="n">Estimate</th><th class="n">Result</th></tr>${a.recent.map(r => `<tr><td>${day(r.day)}</td><td><a href="#/game/${r.id}">${h(T(r.away).short)} at ${h(T(r.home).short)}</a></td><td class="n">${h(T(r.margin >= 0 ? r.home : r.away).abbr)} by ${fx(Math.abs(r.margin))}</td><td class="n">${r.away_pts}–${r.home_pts}</td></tr>`).join("")}</table></div></section>` : ""}
  </div>`;
}

/* ---------------------------------------------------------------- about */
async function about() {
  const a = await get("accuracy.json");
  setTitle("How it works");
  const tuned = META.tuned || {};
  app.innerHTML = `<section class="hero court"><div class="wrap"><h1>How it works</h1></div></section>
  <div class="wrap prose">${demoBanner()}
    <p>Tip-Off Numbers estimates every NBA game in the next two weeks: each team's chance to win, the likely margin and total, and threes, rebounds and assists. One recipe for every game:</p>
    <p class="verdict"><b>estimate = base ratings + rest, travel &amp; availability + psychological spots</b></p>
    <h2>Where the data comes from</h2>
    <p>ESPN's public feed: results and schedule for three full seasons plus the current one, box scores and player minutes for this season and last, and the league injury report. A scheduled job refreshes everything every three hours.</p>
    <h2>1. Base ratings</h2>
    <p>For every team-game: points scored = league average + home court + the team's attack − the opponent's defence. One penalised regression per stat; recent games count more (half-life ${tuned.half_life ?? "–"} days), last season's games are discounted again (×${tuned.carry ?? "–"}) because rosters change, and every team is pulled towards average until the evidence says otherwise.</p>
    <h2 class="body">2. Rest, travel and availability</h2>
    <ul><li><b>Back-to-backs</b> and <b>three games in four nights</b>; days of rest.</li><li><b>Body clock</b>: time zones crossed heading east; <b>travel</b> distance since the last game.</li>
    <li><b>Missing players</b>: each rotation regular's share of the team's production (points + ½ rebounds + assists, last 15 games). For past games, who actually didn't play; for the next three days, the injury report (out = 100%, doubtful 75%, questionable 40%, day-to-day 30%).</li></ul>
    <h2 class="mind">3. The psychological layer</h2>
    <p>Basketball people talk about momentum, letdowns and revenge all the time. Here each of those stories becomes a precise, checkable condition, and its size is measured from what actually happened afterwards:</p>
    <ul><li><b>Streak</b>: current winning or losing run.</li><li><b>Confidence</b>: how far the last five games beat (or fell short of) what the ratings expected.</li>
    <li><b>Bounce-back</b>: lost the previous game by 20 or more.</li><li><b>Letdown</b>: beat a top team (.600+) last time out, now face a weak one (under .450).</li>
    <li><b>Revenge</b>: lost the last meeting between the two teams this season (in the playoffs, the previous game of the series).</li>
    <li><b>Look-ahead</b>: a weak opponent tonight and a top team (.620+) within two days.</li><li><b>Homecoming</b>: first home game after a road trip of four or more; <b>long road trip</b>: fourth or later straight road game.</li>
    <li><b>Stakes</b>: from game 55 on, within three games of a seed line (6/7 or 10/11) counts as a race; far out of the play-in, or a settled seed with few games left, counts as nothing to play for.</li>
    <li><b>Facing elimination</b> in the playoffs. Division rivalry, playoff intensity and dead-rubber games are measured on the total.</li></ul>
    <h2>How big is each effect?</h2>
    <p>Measured, not assumed. The base ratings make an out-of-sample prediction for every past game (refit every week on earlier games only). What they missed is regressed on all the factors at once, with a penalty that pulls each factor towards zero unless the evidence is there. That gives each factor its size in points, its uncertainty and a label: <b>strong</b>, <b>moderate</b>, <b>weak</b> or <b>no clear evidence</b>. A popular story that the data doesn't support simply ends up worth almost nothing. The current sizes are on the <a href="#/accuracy">track record</a> page; they're re-measured on every run.</p>
    <h2>From numbers to chances</h2>
    <p>Margins are treated as normally distributed around the estimate with the spread of past misses (${a.sd_margin ?? "–"} points); totals the same (${a.sd_total ?? "–"}). The win chance is the share of that distribution on each side of zero.</p>
    <h2>Keeping it honest</h2>
    <ul><li>An estimate is rewritten on every run until tip-off, then <b>frozen</b> and never touched again; after the game it is scored. The git history of <code>data/predictions/</code> proves each one existed before tip-off.</li>
    <li>Scores are compared with plain averages (points for and against) and with the same model <b>without</b> the psychological layer, so you can see whether the mind actually adds anything.</li>
    <li>Settings are tuned on one season and tested once on the next.</li></ul>
    <h2>Limits</h2>
    <ul><li>Psychology is noisy. Most spots are worth a point or two at most, and some are worth nothing.</li><li>Late scratches after the last refresh, trades and coaching changes are not in the numbers until the data shows them.</li>
    <li>These are statistical estimates, not advice.</li></ul>
  </div>`;
}

/* ---------------------------------------------------------------- search & routing */
function setupSearch() {
  const f = document.querySelector("[data-search]");
  const input = f.querySelector("input"), drop = f.querySelector(".drop");
  const close = () => { drop.hidden = true; };
  input.addEventListener("input", () => {
    const q = input.value.trim().toLowerCase();
    if (!q) return close();
    const hits = Object.values(TEAMS).filter(t => (t.name + " " + t.abbr).toLowerCase().includes(q)).slice(0, 8);
    drop.innerHTML = hits.length ? hits.map(t => `<a href="#/team/${t.abbr}">${disc(t.abbr, "xs")}${h(t.name)}<span class="sub">${h(t.record)}</span></a>`).join("") : `<p class="sub" style="padding:8px">No team found.</p>`;
    drop.hidden = false;
  });
  f.addEventListener("submit", e => { e.preventDefault(); const a = drop.querySelector("a"); if (a) { location.hash = a.getAttribute("href"); close(); input.value = ""; } });
  document.addEventListener("click", e => { if (!f.contains(e.target)) close(); });
  window.addEventListener("hashchange", () => { close(); input.value = ""; });
}

async function route() {
  const parts = location.hash.replace(/^#\/?/, "").split("/");
  const [page, arg] = parts;
  document.querySelectorAll("[data-nav]").forEach(a => a.setAttribute("aria-current", a.dataset.nav === (page || "home") || (page === "game" && a.dataset.nav === "games") || (page === "team" && a.dataset.nav === "teams") ? "page" : "false"));
  try {
    if (!page) await home();
    else if (page === "games") await games(arg);
    else if (page === "game") await game(arg);
    else if (page === "standings") await standings();
    else if (page === "teams") await teams();
    else if (page === "team") await team(arg);
    else if (page === "accuracy") await accuracy();
    else if (page === "about") await about();
    else await home();
  } catch (err) {
    app.innerHTML = `<div class="wrap" style="padding-top:40px"><p class="empty">Couldn't load this page (${h(err.message)}).</p><p><a href="#/">Back home</a></p></div>`;
  }
  window.scrollTo(0, 0);
  app.focus({ preventScroll: true });
}

(async function init() {
  try {
    META = await get("meta.json");
    version = META.updated || version;
    const list = await get("teams.json");
    for (const t of list) TEAMS[t.abbr] = t;
    document.getElementById("freshness").textContent = `Updated ${ago(META.updated)} · ${META.season} season${META.mode === "demo" ? " · simulated preview data" : ""}`;
  } catch (e) { /* pages show their own error */ }
  setupSearch();
  window.addEventListener("hashchange", route);
  route();
})();
