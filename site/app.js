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
const STATS_SHORT = { pts: "PTS", reb: "REB", ast: "AST", pra: "PRA" };
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
    ? `<tr><th></th><th>Team</th><th class="n">W</th><th class="n">L</th><th class="n">GB</th><th class="n">Net</th><th class="n">Playoffs</th></tr>`
    : `<tr><th></th><th>Team</th><th class="n">W</th><th class="n">L</th><th class="n">Pct</th><th class="n">GB</th><th class="n">Home</th><th class="n">Away</th><th class="n">Conf</th><th class="n">L10</th><th class="n">Strk</th><th class="n">Pt diff</th><th class="n" title="Rating: points better than an average team per game">Net</th><th class="n" title="Last 5 games versus expectation">Conf.</th><th class="n" title="Projected wins">Proj W</th><th title="Chance to make the playoffs (incl. via the play-in)">Playoffs</th><th class="n" title="Chance of a top-6 seed">Top 6</th></tr>`;
  const body = rows.map(r => {
    const cut = r.seed === 6 || r.seed === 10 ? " cut" : "";
    const base = `<td class="pos">${r.seed}</td><td>${tlink(r.abbr)}</td><td class="n">${r.w}</td><td class="n">${r.l}</td>`;
    const rest = short
      ? `<td class="n">${r.gb ? fx(r.gb, 1) : "–"}</td><td class="n">${sgn(r.net)}</td><td class="n">${r.odds ? pct(r.odds.playoffs) : "–"}</td>`
      : `<td class="n">${fx(r.pct, 3).replace(/^0/, "")}</td><td class="n">${r.gb ? fx(r.gb, 1) : "–"}</td><td class="n">${r.home}</td><td class="n">${r.away}</td><td class="n">${r.conf}</td><td class="n">${r.l10}</td><td class="n">${r.streak}</td><td class="n">${sgn(r.pd)}</td><td class="n">${sgn(r.net)}</td><td class="n ${effCls(r.confidence)}">${sgn(r.confidence)}</td><td class="n">${r.odds ? fx(r.odds.wins, 0) : "–"}</td><td>${r.odds ? `<span class="oddsbar"><span style="width:${r.odds.playoffs * 100}%"></span></span>${pct(r.odds.playoffs)}` : "–"}</td><td class="n">${r.odds ? pct(r.odds.top6) : "–"}</td>`;
    return `<tr class="z-${r.zone}${cut}">${base}${rest}</tr>`;
  }).join("");
  return `<div class="tscroll"><table>${cols}${body}</table></div>`;
}

/* ---------------------------------------------------------------- home */
/* ---------------------------------------------------------------- Tonight (home) */
function teamInk(ab) {
  // a team colour that reads on the dark ground: the primary if it is bright enough, else the alternate
  const t = T(ab), lum = c => { const n = parseInt((c || "#555").slice(1), 16); const r = n >> 16 & 255, g = n >> 8 & 255, b = n & 255; return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
  return lum(t.color) >= 60 ? t.color : (lum(t.alt) >= 60 ? t.alt : "#5B6070");
}
const mono = (ab, cls = "") => `<span class="mono ${cls}" style="background:${teamInk(ab)}">${h(T(ab).abbr)}</span>`;
function tnLeg(l) {
  const teams = matchTeams(l), p = effP(l);
  const badge = l.kind === "total" ? `<span class="mono" style="background:#2A2D3A">O/U</span>` : mono(l.team || teams[1]);
  return `<li class="tk-leg">${badge}<div class="body"><p class="meta">${h(KIND[l.kind] || l.kind)} · ${h(T(teams[0]).short)} at ${h(T(teams[1]).short)} · ${tipTime(l.tip)}</p>
    <p class="what">${h(legDesc(l))}</p>${l.story ? `<p class="why">${h(l.story)}</p>` : ""}${l.alert ? `<p class="alert">⚠ ${h(l.alert)}</p>` : ""}${l.swap ? `<p class="swap">Suggested swap: <b>${h(l.swap.desc)}</b> · ${h(l.swap.matchup || "")} · ${pct(l.swap.p)} chance · take at ${fx(l.swap.min_odds || 1.05 / l.swap.p, 2)}+</p>` : ""}</div>
    <div class="take"><p class="k">Take at</p><p class="v num">${fx(1.05 / p, 2)}+</p><p class="s num">${pct(p)} chance</p></div>${addBtn(l)}</li>`;
}
function gameCard(c) {
  const done = c.home_pts != null, ph = c.win_home, pa = 1 - ph;
  const ln = Math.abs(c.margin) < 1 ? "Even" : `${T(c.margin >= 0 ? c.home : c.away).abbr} by ${fx(Math.abs(c.margin), 0)}`;
  const right = (side, p) => done ? `<span class="p num ${(side === "home") === (c.home_pts > c.away_pts) ? "" : "sub"}">${side === "home" ? c.home_pts : c.away_pts}</span>` : `<span class="p num">${pct(p)}</span>`;
  const top = done ? `<span class="num">Final</span><span class="num">Estimate: ${ln} <b class="${c.hit ? "ok-t" : "bad-t"}">${c.hit ? "✓" : "✗"}</b></span>`
    : `<span class="num">${c.live ? `<span class="live">Live${c.live.home_pts != null ? ` ${c.live.away_pts}-${c.live.home_pts}` : ""}</span>` : tipTime(c.tip)}</span><span class="num">${ln} · total ${fx(c.total, 0)}</span>`;
  return `<a class="gm" href="#/game/${h(c.id)}" style="--ga:${teamInk(c.away)};--gh:${teamInk(c.home)}"><div class="top2">${top}</div>
    <div class="teams"><div class="tm">${mono(c.away, "sm")}<span class="nm">${h(T(c.away).short)}<span class="rec">${h(c.away_rec || "")}</span></span>${right("away", pa)}</div>
    <div class="tm">${mono(c.home, "sm")}<span class="nm">${h(T(c.home).short)}<span class="rec">${h(c.home_rec || "")}</span></span>${right("home", ph)}</div></div>
    <div class="split"><span style="width:${pa * 100}%;background:${teamInk(c.away)}"></span><span style="width:${ph * 100}%;background:${teamInk(c.home)}"></span></div>
    ${c.story ? `<p class="story2">${h(c.story)}</p>` : (c.tags && c.tags.length ? `<p class="story2">${h(c.tags.map(t => t.label).join(" · "))}</p>` : "")}</a>`;
}
const tipTime = iso => (iso ? new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false }) : "");
async function home() {
  const [sch, acc, par, pl] = await Promise.all([get("schedule.json"), get("accuracy.json"), get("parlay.json").catch(() => ({})), get("players.json").catch(() => [])]);
  PAR = par;
  setTitle("");
  const days = byDay(sch.upcoming);
  const d1 = [...days.keys()][0];
  const tonight = sch.upcoming.filter(c => c.day === d1).sort((a, b) => a.tip.localeCompare(b.tip));
  const t = par.today && par.today.day === d1 ? par.today : par.today;
  const locked = t && t.locked !== false && t.parlays && t.parlays.length;
  const first = tonight.length ? tonight[0].tip : null;
  const live = acc.live && acc.live.n ? acc.live : null;

  // hero
  const heroTitle = locked ? "Tonight's picks<br>are in." : t && t.locked === false ? "Tonight's picks<br>are on the way." : "Tonight in<br>the NBA.";
  const heroText = locked ? `Chosen once by the full model${t.locked_at ? ` at ${tipTime(t.locked_at)}` : ""}, three hours before the first tip-off, after the main injury news. Locked now: they will not change.`
    : t && t.locked === false ? `The full model picks tonight's tickets once, at ${tipTime(t.lock_at)}, three hours before the first tip-off, when the main injury news is in. Until then, the games and prices below keep updating.`
    : "Win chances, scores and player projections for every game, from team and player ratings, rest, travel, who is missing and a measured psychological layer.";
  const hero = `<section class="tn-hero"><div class="lead"><p class="eyebrow">${d1 ? h(longDay(d1)) : ""}${tonight.length ? ` · ${tonight.length} game${tonight.length > 1 ? "s" : ""}` : ""}</p>
    <h1>${heroTitle}</h1><p class="sublede">${heroText}</p></div>
    <div class="tiles"><div class="tile"><p class="k">First tip-off</p><p class="v num">${first ? tipTime(first) : "–"}</p></div>
    <div class="tile"><p class="k">Live record</p>${live ? `<p class="v num">${Math.round(live.hit * live.n)}/${live.n}</p>` : `<p class="v sm">Starts with tonight's games</p>`}</div></div></section>`;

  // tickets
  let tickets = "";
  if (locked) {
    const [main, ...rest] = t.parlays;
    const long = rest.filter(pr => pr.name === "The daily 6"), side = rest.filter(pr => pr.name !== "The daily 6");
    tickets = `<section class="tk-row" aria-label="Tonight's tickets">
      <article class="tk-main"><span class="tk-tag">Main pick</span> <span class="sub small" style="margin-left:10px">${new Set(main.legs.map(l => l.game)).size} game${main.n_legs > 1 ? "s" : ""}${t.locked_at ? ` · locked ${tipTime(t.locked_at)}` : ""}</span>
        <h2>${h(main.name)}</h2>${main.story ? `<p class="tk-story">${h(main.story)}</p>` : ""}
        <ul class="tk-legs">${main.legs.map(tnLeg).join("")}</ul>
        <div class="tk-foot"><div><p class="k">All land</p><p class="v num">${pct(main.p)}</p></div><div><p class="k">Fair combined odds</p><p class="v num">${fx(main.fair, 2)}</p></div>
          <div><p class="k">Worth placing at</p><p class="v go num">${fx(main.min_odds, 2)}+</p></div>
          <div class="acts"><button type="button" class="pill-btn" data-copy="${h(ticketText(main))}">Copy ticket</button><a class="pill-btn primary" href="#/parlay">Enter Winamax odds</a></div></div></article>
      <div class="tk-side">${side.map(pr => `<a class="tk-mini" href="#/parlay"><div class="hd"><h3>${h(pr.name)}</h3><span class="nums num">${pct(pr.p)} · take ${fx(pr.min_odds, 2)}+</span></div>
          ${pr.story ? `<p>${h(pr.story)}</p>` : ""}<ul>${pr.legs.slice(0, 4).map(l => `<li><span>${h(legDesc(l))}</span><span class="num">${fx(l.min_odds, 2)}+</span></li>`).join("")}</ul></a>`).join("")}
        ${long.map(pr => `<a class="tk-mini tk-long" href="#/parlay"><div><p class="k">Long shot</p><h3>${h(pr.name)}</h3></div><span class="v num">${fx(pr.min_odds, 2)}+</span></a>`).join("")}</div></section>`;
  } else if (t && t.locked === false) {
    tickets = `<section class="tk-row"><div class="tk-wait"><p class="eyebrow">Tonight's tickets</p><h2>Chosen once, then locked</h2><p class="clock num" id="lockclock">${tipTime(t.lock_at)}</p>
      <p class="sub2" style="color:var(--muted);max-width:620px;margin-top:16px">Three hours before the first tip-off, once the main injury reports are in, the full model picks the day's tickets and explains each one in plain words. They never change after that.</p></div></section>`;
  }

  // Winamax vs Pinnacle
  const val = (t && t.value) || [];
  const boosts = t ? LS.get("tipoff.boost." + t.day, {}) : {};
  const anyVal = val.some(v => v.value);
  const vrow = v => {
    const key = v.game + v.side, odds = boosts[key] || v.price, e = v.fair_p == null ? null : odds * v.fair_p - 1;
    const w = e == null ? 0 : Math.min(50, Math.abs(e) * 400);
    return `<div class="vb-row ${v.value ? "val" : ""}"><span class="team"><span class="dotc" style="background:${teamInk(v.team)}"></span><b>${h(T(v.team).short)}</b><span class="sub">vs ${h(T(v.opp).short)}</span></span>
      <span class="r num" style="font-weight:600">${fx(v.price, 2)}</span><span class="r num sub">${v.fair_odds ? fx(v.fair_odds, 2) : "–"}</span>
      <span class="edgebar"><span class="tr"><span class="fl" style="${e != null && e >= 0 ? `left:50%;background:var(--accent)` : "right:50%;background:#5B5F70"};width:${w}%"></span></span><span class="n num ${e != null && e >= 0 ? "ok-t" : "sub"}" data-vedge="${key}">${e == null ? "–" : sgn(e * 100, 1) + "%"}</span></span>
      <span class="r num sub">${v.model_p == null ? "–" : pct(v.model_p)}</span>
      <input class="boostin" data-vid="${key}" data-fair="${v.fair_p ?? ""}" type="number" step="0.01" min="1.01" placeholder="Boost?" value="${boosts[key] || ""}" aria-label="Boosted Winamax odds for ${h(T(v.team).short)}"></div>`;
  };
  const valueSec = val.length ? `<section class="tn-sec" aria-labelledby="vbh"><div class="hd"><div><h2 id="vbh">Winamax vs Pinnacle</h2>
      <p class="sub2">When Winamax pays more than Pinnacle's fair price, the bet pays off in the long run. Got a boosted price? Type it in the last column.</p></div>
      <span class="chip ${anyVal ? "ok" : "warn"}">${anyVal ? `${val.filter(v => v.value).length} with value` : "No value right now"}</span></div>
      <div class="vb"><div class="vb-in"><div class="vb-row head"><span>Winner</span><span class="r">Winamax</span><span class="r">Pinnacle fair</span><span>Edge</span><span class="r">Our model</span><span class="r">Boosted odds</span></div>
      ${val.slice(0, 6).map(vrow).join("")}<div id="vbrest" hidden>${val.slice(6).map(vrow).join("")}</div></div>
      ${val.length > 6 ? `<button type="button" class="vb-more" id="vbmore">Show all ${val.length} winners</button>` : ""}</div></section>` : "";

  // games
  const gamesSec = tonight.length ? `<section class="tn-sec" aria-labelledby="gmh"><div class="hd"><h2 id="gmh">Tonight's games</h2><a href="#/games">All games and estimates</a></div>
      <div class="gm-grid">${tonight.map(gameCard).join("")}</div></section>` : "";

  // last night + players to watch
  const lastDay = sch.results.length ? sch.results[0].day : null;
  const last = sch.results.filter(c => c.day === lastDay);
  const lastHtml = last.length ? `<div><h2 style="font-size:28px;margin:0">Last night</h2><div class="listcard" style="margin-top:16px">${last.map(c => {
      const hw = c.home_pts > c.away_pts;
      return `<a class="row" href="#/game/${h(c.id)}">${mono(hw ? c.home : c.away, "sm")}<span class="grow"><b>${h(T(c.away).short)} ${c.away_pts}</b> <span class="muted">at</span> <b>${h(T(c.home).short)} ${c.home_pts}</b></span>
        <span class="muted">${c.kind === "frozen" ? "Estimate" : "Check"}</span><span class="val ${c.hit ? "ok-t" : "bad-t"}">${c.hit ? "✓" : "✗"}</span></a>`; }).join("")}</div></div>` : "";
  const ids = new Set(tonight.map(c => c.id));
  const top = (pl || []).filter(p => p.next_pts != null && ids.has(p.next_game)).sort((a, b) => b.next_pts - a.next_pts).slice(0, 8);
  const topHtml = top.length ? `<div><h2 style="font-size:28px;margin:0">Players to watch</h2><div class="listcard" style="margin-top:16px">${top.map(p => `<a class="row" href="#/player/${h(p.id)}">${mono(p.team, "sm")}<span class="grow"><b>${h(p.name)}</b><br><span class="muted">${h(T(p.team).short)}${p.status ? ` · ${h(p.status)}` : ""}</span></span><span class="val num">${fx(p.next_pts, 1)}</span><span class="muted">pts</span></a>`).join("")}</div></div>` : "";

  app.innerHTML = `<div class="wrap tn">${demoBanner()}${hero}${tickets}${valueSec}${gamesSec}${lastHtml || topHtml ? `<section class="tn-sec duo2">${lastHtml}${topHtml}</section>` : ""}</div>`;
  const vm = document.getElementById("vbmore");
  if (vm) vm.onclick = () => { document.getElementById("vbrest").hidden = false; vm.remove(); };
  app.oninput = e => {
    const bi = e.target.closest(".boostin[data-vid]");
    if (!bi || !t) return;
    const all = LS.get("tipoff.boost." + t.day, {}), v = parseFloat(bi.value), fair = parseFloat(bi.dataset.fair);
    if (v > 1) all[bi.dataset.vid] = v; else delete all[bi.dataset.vid];
    LS.set("tipoff.boost." + t.day, all);
    const row = val.find(x => x.game + x.side === bi.dataset.vid), cell = app.querySelector(`[data-vedge="${bi.dataset.vid}"]`);
    const ed = isNaN(fair) ? null : (v > 1 ? v : row.price) * fair - 1;
    if (cell) { cell.textContent = ed == null ? "–" : sgn(ed * 100, 1) + "%"; cell.className = "n num " + (ed != null && ed >= 0 ? "ok-t" : "sub"); }
  };
}

/* ---------------------------------------------------------------- games */
const FILTERS = [["all", "All games", () => true], ["mind", "Strong mental edge", c => Math.abs(c.mind || 0) >= 0.75 || (c.tags || []).some(t => t.ev === "strong" || t.ev === "moderate"), "m"],
  ["tv", "National TV", c => c.tv], ["close", "Toss-ups (40-60%)", c => c.win_home >= 0.4 && c.win_home <= 0.6], ["fav", "Big favourites (75%+)", c => Math.max(c.win_home, 1 - c.win_home) >= 0.75],
  ["high", "High totals (232+)", c => c.total >= 232], ["low", "Low totals (under 220)", c => c.total < 220]];
let GFILTER = "all";
async function games(sel) {
  const sch = await get("schedule.json");
  setTitle("Games");
  const fn = (FILTERS.find(f => f[0] === GFILTER) || FILTERS[0])[2];
  const all = [...sch.results].reverse().concat(sch.upcoming).filter(fn);
  const days = byDay(all);
  const keys = [...days.keys()];
  const upDay = sch.upcoming.length ? sch.upcoming[0].day : null;
  const firstUp = (upDay && keys.find(k => k >= upDay)) || keys[keys.length - 1];
  const cur = sel && days.has(sel) ? sel : firstUp;
  const i = keys.indexOf(cur);
  const win = keys.slice(Math.max(0, i - 3), i + 6);
  const list = days.get(cur) || [];
  const fbar = `<div class="filters" id="gf">${FILTERS.map(f => `<button class="${f[3] || ""}" data-f="${f[0]}" aria-pressed="${GFILTER === f[0]}">${f[1]}</button>`).join("")}</div>`;
  app.innerHTML = `<div class="wrap tn">${demoBanner()}<section class="tn-hero" style="padding-bottom:28px"><div class="lead"><p class="eyebrow">Next two weeks · last three weeks</p><h1>Games</h1>
    <p class="sublede">Every estimate updates until tip-off and is then frozen. Results show whether the estimate called the winner.</p></div></section>
    <nav class="daytabs" aria-label="Days">${i > 3 ? `<a href="#/games/${keys[Math.max(0, i - 7)]}" aria-label="Earlier days">←</a>` : ""}${win.map(k => `<a href="#/games/${k}" aria-current="${k === cur ? "page" : "false"}">${day(k)}</a>`).join("")}${i + 6 < keys.length ? `<a href="#/games/${keys[Math.min(keys.length - 1, i + 7)]}" aria-label="Later days">→</a>` : ""}</nav>
    ${fbar}
    ${cur ? `<section class="tn-sec" style="margin-top:36px"><div class="hd"><h2>${h(longDay(cur))}</h2><span class="sub">${list.length} game${list.length === 1 ? "" : "s"}</span></div>
    <div class="gm-grid">${list.map(gameCard).join("")}</div></section>` : `<p class="empty">No game matches this filter.</p>`}</div>`;
  document.getElementById("gf").onclick = e => { const b = e.target.closest("button"); if (!b) return; GFILTER = b.dataset.f; games(sel); };
}

/* ---------------------------------------------------------------- standings */
async function standings() {
  const st = await get("standings.json");
  setTitle("Standings");
  app.innerHTML = `<section class="hero court"><div class="wrap"><h1>Standings</h1><p class="sub" style="margin-top:8px">${h(st.season)} regular season. Net = rating, points better than an average team per game. Conf. = last five games versus what the ratings expected. Playoff chances from 4,000 simulations of the rest of the schedule, play-in included.</p></div></section>
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
    ${teamExtras(t)}
    <section class="section"><h2>Players <span class="sub">this season</span></h2>${teamPlayers(t)}</section>
    <section class="section grid2"><div><h2>Rotation share</h2>${roster}</div><div><h2 class="body">Injury list</h2><div class="panel">${inj}</div></div></section>
  </div>`;
}

function teamPlayers(t) {
  const ps = (t.players || []).filter(p => p.gp > 0);
  if (!ps.length) return `<p class="sub">No box scores yet.</p>`;
  return `<div class="tscroll"><table class="ptable"><tr><th>Player</th><th class="n">GP</th><th class="n">MIN</th><th class="n">PTS</th><th class="n">REB</th><th class="n">AST</th><th class="n">3PM</th><th class="n">STL</th><th class="n">BLK</th><th class="n">TS%</th><th class="n">USG%</th><th class="n">+/-</th><th class="n">Next</th></tr>
    ${ps.map(p => `<tr class="${p.out ? "out" : ""}"><td class="nm">${plink(p.id, p.name)}<span class="sub">${h(p.pos || "")}</span>${ptags(p)}</td><td class="n">${p.gp}</td><td class="n">${fx(p.mpg)}</td><td class="n hl">${fx(p.ppg)}</td><td class="n">${fx(p.rpg)}</td><td class="n">${fx(p.apg)}</td><td class="n">${fx(p.tpm)}</td><td class="n">${fx(p.spg)}</td><td class="n">${fx(p.bpg)}</td><td class="n">${p.ts == null ? "–" : (p.ts * 100).toFixed(1)}</td><td class="n">${fx(p.usg)}</td><td class="n">${sgn(p.pm)}</td><td class="n">${p.next_pts == null ? "–" : fx(p.next_pts)}</td></tr>`).join("")}</table></div>`;
}

function teamExtras(t) {
  const a = t.advanced, o = t.odds, m = t.mood;
  const advHtml = a ? `<div class="adv">${[["Pace", a.pace, a.pace_rank, 1, 1, "possessions / game"], ["Off. rating", a.ortg, a.ortg_rank, 1, 1, "points / 100 poss."], ["Def. rating", a.drtg, a.drtg_rank, 1, 1, "allowed / 100 poss."], ["Net rating", a.nrtg, a.nrtg_rank, 1, 1, "per 100 poss."],
      ["eFG%", a.efg, a.efg_rank, 1, 100, "shooting"], ["Opp. eFG%", a.o_efg, a.o_efg_rank, 1, 100, "allowed"], ["TOV%", a.tov, a.tov_rank, 1, 100, "turnovers / poss."], ["Forced TOV%", a.o_tov, a.o_tov_rank, 1, 100, "opponents"],
      ["OREB%", a.orb, a.orb_rank, 1, 100, "offensive boards"], ["DREB%", a.drb, a.drb_rank, 1, 100, "defensive boards"], ["FT rate", a.ftr, a.ftr_rank, 2, 1, "FTA per FGA"], ["Opp. FT rate", a.o_ftr, a.o_ftr_rank, 2, 1, "allowed"]]
      .map(([l, v, r, d, mu, sub]) => `<div><b>${v == null ? "–" : (v * mu).toFixed(d)}</b>${l} <span class="pill none">#${r ?? "–"}</span><br>${sub}</div>`).join("")}</div>` : `<p class="sub">No box scores yet.</p>`;
  const oddsHtml = o ? `<div class="adv">${[["Playoffs", pct(o.playoffs), "incl. play-in wins"], ["Top 6", pct(o.top6), "no play-in"], ["Play-in", pct(o.playin), "seeds 7-10"], ["#1 seed", pct(o.seed1), "in the conference"], ["Projected wins", fx(o.wins), "of 82"]].map(([l, v, sub]) => `<div><b>${v}</b>${l}<br>${sub}</div>`).join("")}</div>` : "";
  const moodHtml = m ? `<div class="panel mind"><h3>State of mind ${catTag(m.cat)} <span class="sub small">#${m.rank} of 30</span></h3><ul class="why">${(m.why.length ? m.why : ["nothing unusual"]).map(x => `<li>${h(x)}</li>`).join("")}</ul><p class="sub small">Momentum ${sgn(m.score)} · measured mind edge in the next games ${sgn(m.edge)} pts · <a href="#/mind">Mind ranking</a></p></div>` : "";
  return `<section class="section"><h2>Advanced <span class="sub">this season, league rank in each</span></h2>${advHtml}</section>
    ${o ? `<section class="section grid2"><div><h2>Playoff chances <span class="sub">4,000 simulations of the rest of the season</span></h2>${oddsHtml}</div><div><h2 class="mind">Mind</h2>${moodHtml}</div></section>` : moodHtml}`;
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
  const storyBits = [];
  for (const [side, ab] of [["away", A], ["home", H]]) {
    const t = g[side], miss = (t.missing_list || []).map(m => m.name).slice(0, 2);
    if (miss.length && (t.missing || 0) >= 0.06) storyBits.push(`the ${T(ab).short} are without ${miss.join(" and ")}`);
    if (t.b2b) storyBits.push(`the ${T(ab).short} played last night`);
  }
  const storyTxt = storyBits.length ? storyBits.slice(0, 3).join("; ") : "";
  const big = res ? `<div class="gh-score num">${res.away_pts}<span>–</span>${res.home_pts}</div><p class="gh-sub">Final${res.ot ? ` · ${res.ot > 1 ? res.ot : ""}OT` : ""}</p>`
    : g.live ? `<div class="gh-score num">${g.live.away_pts ?? 0}<span>–</span>${g.live.home_pts ?? 0}</div><p class="gh-sub live">${h(g.live.detail || "Live")}</p>`
    : `<div class="gh-score num">${tipTime(g.tip)}</div><p class="gh-sub">${g.tip ? new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long" }).format(new Date(g.tip)) : day(g.day)}</p>`;
  const pa = 1 - e.win_home;
  app.innerHTML = `<section class="gh" style="--ca:${teamInk(A)};--ch:${teamInk(H)}"><div class="wrap">
    <p class="gh-meta"><span class="chip ${g.kind === "estimate" ? "ok" : "warn"}">${h(kind)}</span><span>${h(stypeLabel(g.stype))}${series}</span>${g.venue ? `<span>${h(g.venue)}</span>` : ""}${g.national_tv ? `<span>National TV</span>` : ""}${g.rivalry ? `<span>Division rivals</span>` : ""}${g.refs && g.refs.length ? `<span>Referees: ${h(g.refs.join(", "))}</span>` : ""}</p>
    <div class="gh-main">
      <div class="gh-team">${mono(A, "xl")}<a href="#/team/${A}">${h(T(A).short)}</a><span class="sub">${h(g.away.record)}${g.away.seed ? ` · ${g.away.conf} #${g.away.seed}` : ""}</span></div>
      <div class="gh-mid">${big}</div>
      <div class="gh-team r">${mono(H, "xl")}<a href="#/team/${H}">${h(T(H).short)}</a><span class="sub">${h(g.home.record)}${g.home.seed ? ` · ${g.home.conf} #${g.home.seed}` : ""}</span></div>
    </div>
    <div class="gh-win"><span class="num"><b>${pct(pa)}</b> ${h(T(A).short)}</span><div class="split"><span style="width:${pa * 100}%;background:${teamInk(A)}"></span><span style="width:${e.win_home * 100}%;background:${teamInk(H)}"></span></div><span class="num">${h(T(H).short)} <b>${pct(e.win_home)}</b></span></div>
    ${storyTxt ? `<p class="gh-story">${h(storyTxt.charAt(0).toUpperCase() + storyTxt.slice(1))}.</p>` : ""}
  </div></section>
  <div class="wrap">${demoBanner()}${BANNER}${scored}${gameBuilder(g)}
    <section class="grid">
      <div class="panel"><h3>Score estimate</h3><div class="teampts"><div>${disc(A, "sm")}<b>${fx(e.away_pts, 0)}</b></div><div>${disc(H, "sm")}<b>${fx(e.home_pts, 0)}</b></div></div>
        ${marginChart(e, H, A, am)}<p class="sub small">Likely margins (±${fx(e.sd_margin)} points is one standard deviation).</p>
        <ul class="lines">${e.spread_lines.map(l => `<li class="${am == null ? "" : ((am > l.line) === (l.home_cover >= 0.5) ? "hit" : "miss")}"><span>${h(T(H).abbr)} by ${l.line}+</span><span class="bar"><span style="width:${l.home_cover * 100}%"></span></span><span class="pct">${pct(l.home_cover)}</span></li>`).join("")}</ul></div>
      <div class="panel"><h3>Total points</h3><div class="stat-row"><span class="stat-big">${fx(e.total, 0)}</span><span class="range">80% range ${fx(e.total - 1.28 * e.sd_total, 0)}–${fx(e.total + 1.28 * e.sd_total, 0)}</span>${at != null ? `<span class="actual">actual ${at}</span>` : ""}</div>
        ${linesList(e.total_lines, at, "Over")}
        <p class="sub small" style="margin-top:10px">Base ${fx(e.base.total, 0)} · physical ${sgn(e.physical.total)} · mind ${sgn(e.mind.total)}${e.level_total ? ` · league scoring this season ${sgn(e.level_total)}` : ""}</p></div>
      <div class="panel"><h3>Why</h3><ul class="why">${g.reasoning.map(r => `<li>${h(r)}</li>`).join("")}</ul>${g.analyst ? `<p class="call"><b>Analyst view:</b> ${h(g.analyst.text || g.analyst.overall || "")}</p>` : ""}</div>
    </section>
    ${simSection(g)}
    <section class="section"><h2>How the number was built <span class="sub">points on the margin</span></h2><div class="panel">${buildRows(g)}
      <p class="sub small" style="margin-top:12px">Win chance with the psychological layer: <b>${pct(Math.max(e.win_home, 1 - e.win_home))}</b> ${h(T(e.win_home >= 0.5 ? H : A).abbr)} · without it: <b>${pct(e.win_home_nomind >= 0.5 ? e.win_home_nomind : 1 - e.win_home_nomind)}</b> ${h(T(e.win_home_nomind >= 0.5 ? H : A).abbr)} · plain averages: <b>${pct(Math.max(e.baseline.win_home, 1 - e.baseline.win_home))}</b> ${h(T(e.baseline.win_home >= 0.5 ? H : A).abbr)}</p></div></section>
    <section class="section"><h2 class="mind">The mental game <span class="sub">each team's psychological spots, sized by what they have been worth in past games</span></h2>
      <div class="panel mind grid2">${mindCol("away", A)}${mindCol("home", H)}</div></section>
    <section class="section"><h2 class="body">Body: rest, travel, availability</h2>${news}<div class="panel body grid2">${bodyCol("away", A)}${bodyCol("home", H)}</div></section>
    ${playersSection(g)}
    ${quartersSection(g, res)}
    ${box ? `<section class="section"><h2>Box score</h2>${box}</section>` : ""}
    ${tops ? `<section class="section">${tops}</section>` : ""}
    ${others ? `<section class="section"><h2>Other numbers</h2><div class="grid">${others}</div></section>` : ""}
    ${h2hSection(g)}
    ${g.made_at ? `<p class="sub small section">Estimate made ${ago(g.made_at)}.</p>` : ""}
  </div>`;
}

function simSection(g) {
  const S = g.sim;
  if (!S) return "";
  const H = g.home.abbr, A = g.away.abbr, aw = 1 - S.home_win;
  const fav = S.home_win >= 0.5 ? H : A, dog = fav === H ? A : H;
  const bFav = fav === H ? S.blowout_home : S.blowout_away, bDog = fav === H ? S.blowout_away : S.blowout_home;
  const story = [
    S.close >= 0.33 ? "A tight one in many runs: about a third finish within five points" : `Most runs are settled by more than five points`,
    `the ${T(fav).short} pull clear by 15+ in ${pct(bFav)} of them${bDog >= 0.05 ? `, the ${T(dog).short} in ${pct(bDog)}` : ""}`,
    S.ot >= 0.04 ? `overtime in about ${Math.round(S.ot * 100)} of every 100` : "",
  ].filter(Boolean).join("; ") + ".";
  const ed = S.margin_hist.edges, ps = S.margin_hist.p, mx = Math.max(...ps);
  const lab = i => i === 0 ? `${T(A).abbr} 30+` : i === ps.length - 1 ? `${T(H).abbr} 30+` : (() => { const lo = ed[i - 1], hi = ed[i]; return hi <= 0 ? `${T(A).abbr} ${-hi}–${-lo}` : `${T(H).abbr} ${lo}–${hi}`; })();
  const bars = ps.map((p, i) => { const homeSide = i > 0 && ed[i - 1] >= 0; return `<div class="sb" title="${h(lab(i))}: ${pct(p)}"><span style="height:${(p / mx) * 100}%;background:${teamInk(homeSide ? H : A)}"></span><em>${i % 2 ? "" : h(lab(i).replace(/^\S+ /, ""))}</em></div>`; }).join("");
  const nameOf = {};
  for (const side of ["home", "away"]) for (const x of (g.players || {})[side] || []) nameOf[x.id] = { name: x.name, side };
  const rows = side => Object.entries(S.players).filter(([id]) => (nameOf[id] || {}).side === side)
    .sort((a, b) => b[1].min[1] - a[1].min[1]).slice(0, 7).map(([id, r]) => {
      const rng = st => `<b class="num">${fx(r[st][1], 0)}</b> <span class="num">${fx(r[st][0], 0)}–${fx(r[st][2], 0)}</span>`;
      const ln = Object.entries(r.lines || {}).map(([st, v]) => `${STATS_SHORT[st] || st} ${v.line}: <b>${pct(v.over)}</b>`).join(" · ");
      return `<tr><td><a href="#/player/${h(id)}">${h(nameOf[id].name)}</a>${r.p_play < 0.95 ? ` <span class="chip warn">plays in ${pct(r.p_play)}</span>` : ""}</td><td>${rng("min")}</td><td>${rng("pts")}</td><td>${rng("reb")}</td><td>${rng("ast")}</td><td class="small">${ln || "–"}</td></tr>`;
    }).join("");
  const tbl = (side, ab) => `<div><h4>${disc(ab, "sm")} ${h(T(ab).short)}</h4><table class="simt"><thead><tr><th>Player</th><th>Minutes</th><th>Points</th><th>Rebounds</th><th>Assists</th><th>Clears the line</th></tr></thead><tbody>${rows(side)}</tbody></table></div>`;
  return `<section class="section reveal"><h2>How tonight plays out <span class="sub">${S.n.toLocaleString("en-GB")} simulations of this game before tip-off</span></h2>
    <div class="panel">
      <p class="sim-story">${h(story)}</p>
      <div class="sim-tiles">
        <div><p class="k">${h(T(A).short)} win</p><p class="v num">${pct(aw)}</p></div>
        <div><p class="k">${h(T(H).short)} win</p><p class="v num">${pct(S.home_win)}</p></div>
        <div><p class="k">Within 5 points</p><p class="v num">${pct(S.close)}</p></div>
        <div><p class="k">Blowout (15+)</p><p class="v num">${pct(S.blowout_home + S.blowout_away)}</p></div>
        <div><p class="k">Overtime</p><p class="v num">${pct(S.ot)}</p></div>
        <div><p class="k">Total, 80% range</p><p class="v num">${fx(S.total[0], 0)}–${fx(S.total[2], 0)}</p></div>
      </div>
      <div class="sim-hist">${bars}</div>
      <p class="sub small">Final margins across the runs (left: ${h(T(A).short)} win, right: ${h(T(H).short)} win).</p>
      <div class="sim-players">${tbl("away", A)}${tbl("home", H)}</div>
      <p class="sub small">Bold: the typical run; after it, the middle 80% of runs. Minutes move with blowouts, overtime and night-to-night swings; teammates share the team's points. "Clears the line": share of runs above the Winamax line just under his projection (Winamax lists fixed lines: points 5+, 10+, 15+…; rebounds and assists 3+, 5+, 7+, 10+, 13+, 15+; pts+reb+ast 10+, 15+, 20+…; threes 1+, 2+, 3+…), counting only runs where he plays (Winamax voids the leg if he does not).</p>
    </div></section>`;
}

function playersSection(g) {
  const H = g.home.abbr, A = g.away.abbr;
  if (g.players) {
    const tbl = (side, ab) => {
      const rows = g.players[side] || [];
      if (!rows.length) return `<p class="sub">No rotation data yet.</p>`;
      return `<div class="tscroll"><table class="ptable"><tr><th>${disc(ab, "xs")} ${h(T(ab).short)}</th><th class="n">MIN</th><th class="n">PTS</th><th class="n">REB</th><th class="n">AST</th><th class="n">3PM</th><th class="n">STL</th><th class="n">BLK</th><th class="n">PRA</th></tr>
        ${rows.map((p, i) => p.out ? `<tr class="out"><td class="nm">${plink(p.id, p.name)}<span class="ptag out">${h(p.status || "Out")}</span></td><td class="n" colspan="8">${h(p.detail || "")}</td></tr>`
          : `<tr><td class="nm">${plink(p.id, p.name)}<span class="sub">${h(p.pos || "")}</span>${p.status ? `<span class="ptag q">${h(p.status)}</span>` : ""}${p.lineup ? `<span class="ptag${p.lineup === "starting" ? "" : " q"}">${p.lineup === "starting" ? "Starting" : "Not starting"}</span>` : ""}${p.sit ? `<span class="ptag" title="Before any news: how often a key player in this spot sits (measured). Used in the team-strength estimate until the injury report is in.">Sits ${Math.round(p.sit * 100)}% in this spot</span>` : ""}${(p.spots || []).filter(x => ["former_team", "returning", "contract_year", "without", "vs_opp"].includes(x.key) || (x.key === "hot")).map(x => `<span class="ptag" title="${h(x.text)}">${h(x.label)}</span>`).join("")}</td>
            <td class="n">${fx(p.min, 0)}</td><td class="n hl">${fx(p.pts)}</td><td class="n">${fx(p.reb)}</td><td class="n">${fx(p.ast)}</td><td class="n">${fx(p.tpm)}</td><td class="n">${fx(p.stl)}</td><td class="n">${fx(p.blk)}</td><td class="n">${fx(p.pra)}</td></tr>`).join("")}</table></div>
        <details class="more"><summary>Over/under chances for every player</summary>${rows.filter(p => !p.out && p.lines).map(p => `<h3 style="margin-top:12px">${h(p.name)}</h3>${linesBlock(p.lines)}`).join("")}</details>`;
    };
    return `<section class="section"><h2>Player projections <span class="sub">every rotation player, ${g.kind === "estimate" ? "updated until tip-off" : "as frozen"}</span></h2><div class="grid2"><div>${tbl("away", A)}</div><div>${tbl("home", H)}</div></div></section>`;
  }
  if (g.players_actual) {
    const tbl = (side, ab) => `<div class="tscroll"><table class="ptable"><tr><th>${disc(ab, "xs")} ${h(T(ab).short)}</th><th class="n">MIN</th><th class="n">PTS</th><th class="n">Proj</th><th class="n">REB</th><th class="n">AST</th><th class="n">3PM</th><th class="n">+/-</th></tr>
      ${(g.players_actual[side] || []).map(p => `<tr><td class="nm">${plink(p.id, p.name)}<span class="sub">${h(p.pos || "")}</span></td><td class="n">${p.min}</td><td class="n hl">${p.pts}</td><td class="n sub">${p.proj ? fx(p.proj.pts) : "–"}</td><td class="n">${p.reb}</td><td class="n">${p.ast}</td><td class="n">${p.tpm}</td><td class="n">${sgn(p.pm, 0)}</td></tr>`).join("")}</table></div>`;
    return `<section class="section"><h2>Players <span class="sub">result, with the model-check projection</span></h2><div class="grid2"><div>${tbl("away", A)}</div><div>${tbl("home", H)}</div></div></section>`;
  }
  return "";
}

function quartersSection(g, res) {
  if (!g.quarters) return "";
  const H = T(g.home.abbr).abbr, A = T(g.away.abbr).abbr;
  return `<section class="section"><h2>Quarters and halves <span class="sub">from each team's usual scoring by quarter</span></h2><div class="tscroll"><table class="qtable"><tr><th>Period</th><th class="n">${h(A)}</th><th class="n">${h(H)}</th><th class="n">Total</th><th class="n">${h(H)} wins it</th><th>Over chances</th></tr>
    ${g.quarters.map(q => `<tr><td>${h(q.name)}</td><td class="n">${fx(q.away)}</td><td class="n">${fx(q.home)}</td><td class="n"><b>${fx(q.total)}</b></td><td class="n">${pct(q.win_home)}</td><td class="sub small">${q.lines.map(l => `${l.line}: ${pct(l.over)}`).join(" · ")}</td></tr>`).join("")}</table></div></section>`;
}

function h2hSection(g) {
  if (!g.h2h || !g.h2h.length) return "";
  return `<section class="section"><h2>Head to head <span class="sub">last ${g.h2h.length} meetings</span></h2><ul class="h2hlist">${g.h2h.map(m => {
    const hw = m.home_pts > m.away_pts;
    return `<li><span>${m.season === g.season ? `<a href="#/game/${m.id}">${day(m.day)}</a>` : day(m.day)} · ${m.season - 1}-${String(m.season).slice(2)}${m.stype === 3 ? " playoffs" : ""}</span><span>${h(T(m.away).abbr)} <b class="${hw ? "" : "up"}">${m.away_pts}</b> – <b class="${hw ? "up" : ""}">${m.home_pts}</b> ${h(T(m.home).abbr)}</span></li>`;
  }).join("")}</ul></section>`;
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
  app.innerHTML = `<div class="wrap tn" style="padding-bottom:0"><section class="tn-hero" style="padding-bottom:28px"><div class="lead"><p class="eyebrow">Frozen at tip-off · scored after the buzzer</p><h1>Track record</h1>
    <p class="sublede">Every estimate is locked before the game and checked afterwards, against simpler methods, including the same model without its psychological layer.</p></div></section>
    <section class="rec-tiles">
      <div class="tile big"><p class="k">Live record · winners called</p>${a.live && a.live.n ? `<p class="v num">${Math.round(a.live.hit * a.live.n)}/${a.live.n}</p><p class="s">${pct(a.live.hit)} · frozen estimates only</p>` : `<p class="v" style="font-size:30px;line-height:1.15">Starts tonight</p><p class="s">The first frozen estimates are scored after tonight's games.</p>`}</div>
      <div class="tile"><p class="k">This season (research)</p><p class="v num">${a.checks ? pct(a.checks.hit) : "–"}</p><p class="s">${a.checks ? `winners in ${a.checks.n} games` : ""}</p></div>
      <div class="tile"><p class="k">Win-chance score</p><p class="v num">${a.checks ? fx(a.checks.brier, 4) : "–"}</p><p class="s">Brier, lower is better</p></div>
      <div class="tile"><p class="k">Player points miss</p><p class="v num">${a.players && a.players.track ? fx(a.players.track.mae_pts, 2) : "–"}</p><p class="s">${a.players && a.players.track ? `vs ${fx(a.players.track.mae_pts_base, 2)} for season averages` : ""}</p></div>
    </section></div>
  <div class="wrap">${demoBanner()}
    ${a.live ? block("Live record: the number that counts", liveO, a.live.n, "Estimates frozen at tip-off with only what was known before the game, never changed afterwards.", a.live.calibration) : `<section><h2>Live record: the number that counts</h2><p class="note">No frozen estimates have been scored yet. The record starts with the first games after the site went live (9 November 2026); nothing is ever added afterwards. Everything below is research: made after the fact and, for the player-based checks, knowing who actually played, so it runs a little better than live estimates can.</p></section>`}
    ${verdict}
    ${a.upgrade ? `<section class="section"><h2>Player-based strength <span class="sub">this season, weights fitted on earlier games only (${a.upgrade.games} games)</span></h2><div class="grid">${[["Winners called", "winners", true, v => pct(v)], ["Brier score", "brier", false, v => fx(v, 4)], ["Log loss", "logloss", false, v => fx(v, 4)], ["Margin miss", "mae_margin", false, v => fx(v, 2)]].map(([l, k, up, f]) => `<div class="panel"><h3>${l}</h3><div class="adv"><div><b>${f(a.upgrade.before[k])}</b>results-based only</div><div><b class="${(up ? a.upgrade.after[k] > a.upgrade.before[k] : a.upgrade.after[k] < a.upgrade.before[k]) ? "up" : "down"}">${f(a.upgrade.after[k])}</b>with player strength</div></div></div>`).join("")}</div>${a.market_blend && a.market_blend.n ? `<p class="sub small" style="margin-top:8px">Market blend: ${a.market_blend.on ? "on" : "off"} · model ${fx(a.market_blend.brier_model, 4)} vs Pinnacle ${fx(a.market_blend.brier_market, 4)} vs blend ${fx(a.market_blend.brier_blend, 4)} on ${a.market_blend.n} frozen games</p>` : ""}</section>` : ""}
    ${a.checks ? block("This season's model checks", chkO, a.checks.n, "Research view. Walk-forward: base ratings from games before each week, factor sizes from earlier seasons, and the players who actually played (a live estimate cannot know late scratches). Made after the fact, so not part of the live record.", a.checks.calibration) : ""}
    ${bt && bt.test ? block(`Backtest: ${bt.test_season - 1}-${String(bt.test_season).slice(2)} season`, bt.test, bt.test.n, `Settings tuned on ${bt.tune_season - 1}-${String(bt.tune_season).slice(2)}, tested once on the next season, walk-forward by week. Half-life ${bt.tuned.half_life} days, last-season weight ${bt.tuned.carry}.`) : ""}
    <section class="section"><h2>What each factor is worth <span class="sub">measured on ${a.effects_games.toLocaleString("en-GB")} games</span></h2>
      <p class="sub">Points on the margin for the team in that spot, from one penalised regression of what the base ratings missed on all factors together. ± is the standard error.</p>
      ${factorTable(a.factors, "margin")}<h3 style="margin-top:22px">Effects on total points</h3>${factorTable(a.factors, "total")}</section>
    ${a.players ? `<section class="section"><h2>Player projections</h2>
      ${a.players.track ? `<p class="verdict"><b>This season's model checks:</b> projected points missed by <b>${fx(a.players.track.mae_pts, 2)}</b> on average across ${a.players.track.n.toLocaleString("en-GB")} player-games, versus <b>${fx(a.players.track.mae_pts_base, 2)}</b> for the player's season average so far.</p>` : ""}
      ${(() => {
        const lt = a.players.lines_test || {}, r = lt.real || {}, px = lt.proxy || {};
        const realHtml = r.n ? `<div class="adv"><div><b>${r.n.toLocaleString("en-GB")}</b>real closing lines tested</div><div><b>${fx(r.brier_model, 4)}</b>model Brier<br>market ${fx(r.brier_market, 4)} · 50/50 blend ${fx(r.brier_blend, 4)}</div>${r.bets ? `<div><b>${r.bets.won}/${r.bets.n}</b>model bets won<br>return ${sgn(r.bets.roi * 100, 1)}% at the opening prices</div><div><b>${r.bets.clv_beat}/${r.bets.clv_n}</b>model bets that beat the close</div>` : ""}</div>`
          : `<p class="note">No real prop lines archived yet. With the odds key and ODDS_API_PROPS=1 the site records each game's opening and closing lines, and this test fills in by itself: model vs market chances (Brier score, lower is better), and the return and closing-line value of the bets the model would have made.</p>`;
        const pxHtml = Object.keys(px).length ? `<div class="tscroll"><table><tr><th>Stat</th><th class="n">Player-games</th><th class="n">Right side</th><th class="n">When 60%+ sure</th></tr>${Object.entries(px).map(([k, v]) => `<tr><td>${h({ pts: "Points", reb: "Rebounds", ast: "Assists", tpm: "Threes", pra: "Pts+Reb+Ast" }[k] || k)}</td><td class="n">${v.n.toLocaleString("en-GB")}</td><td class="n">${pct(v.hit)}</td><td class="n">${pct(v.strong_hit)} <span class="sub">(${v.strong_n})</span></td></tr>`).join("")}</table></div>` : "";
        return `<h3 style="margin-top:18px">Against real prop lines</h3>${realHtml}<h3 style="margin-top:18px">Against the season-average line (proxy, this season)</h3><p class="sub small">Books anchor main lines on the season average. When the projection disagreed with that line, how often was it on the right side? Break-even at standard prices is about 52.4%.</p>${pxHtml}`;
      })()}
      ${(() => {
        const ic = a.players.injury_status || {}, keys = Object.keys(ic);
        const lab = { "out": "Out", "ruled out (note)": "Ruled out in the report's note", "doubtful": "Doubtful", "questionable": "Questionable / game-time decision", "day-to-day": "Day-to-day (no more detail)", "probable": "Probable / expected to play" };
        return `<h3 style="margin-top:18px">Injury report check</h3><p class="sub small">Every run writes down each listed player's status before tip-off; after the game it checks whether he played. From 30 cases on, a status's measured rate replaces the default guess in the projections and in the missing-players factor.</p>` + (keys.length
          ? `<div class="tscroll"><table><tr><th>Status before tip-off</th><th class="n">Cases</th><th class="n">Played</th><th class="n">Minutes vs usual, when he played</th></tr>${keys.map(k => `<tr><td>${h(lab[k] || k)}</td><td class="n">${ic[k].n}</td><td class="n">${pct(ic[k].play)}</td><td class="n">${ic[k].min_ratio == null ? "–" : pct(ic[k].min_ratio)}</td></tr>`).join("")}</table></div>`
          : `<p class="note">The log started on 9 November 2026; the first numbers appear once those games are played.</p>`);
      })()}
      <p class="sub" style="margin-top:18px">What each player spot is worth, in % of the projection (minutes and points), measured on every stored player-game.</p>
      <div class="tscroll"><table><tr><th>Factor</th><th>Means</th><th class="n">Minutes</th><th class="n">Points</th><th class="n">Rebounds</th><th class="n">Assists</th><th>Evidence (points)</th></tr>
      ${[...new Set(a.players.factors.map(r => r.key))].map(k => { const f = st => a.players.factors.find(r => r.key === k && r.stat === st) || {}; const P = f("pts");
        return `<tr><td><span class="mk" style="background:${P.layer === "mind" ? "var(--mind)" : "var(--body)"}"></span>${h(P.label)}</td><td class="sub small">${h(P.means)}</td>${["min", "pts", "reb", "ast"].map(st => `<td class="n ${effCls(f(st).pct)}">${f(st).pct == null ? "–" : sgn(f(st).pct) + "%"}</td>`).join("")}<td>${ev(P.evidence || "none")} <span class="sub small">${(P.n || 0).toLocaleString("en-GB")} games${P.applied === false ? " · measured, not applied" : ""}</span></td></tr>`; }).join("")}</table></div><p class="sub small">Applied only where a test on later seasons improved the projections. "Teammates out" is now handled by the minutes model; "Home floor" made projections worse when applied.</p></section>` : ""}
    ${a.recent && a.recent.length ? `<section class="section"><h2>Latest scored</h2><div class="tscroll"><table><tr><th>Day</th><th>Game</th><th class="n">Estimate</th><th class="n">Result</th></tr>${a.recent.map(r => `<tr><td>${day(r.day)}</td><td><a href="#/game/${r.id}">${h(T(r.away).short)} at ${h(T(r.home).short)}</a></td><td class="n">${h(T(r.margin >= 0 ? r.home : r.away).abbr)} by ${fx(Math.abs(r.margin))}</td><td class="n">${r.away_pts}–${r.home_pts}</td></tr>`).join("")}</table></div></section>` : ""}
  </div>`;
}

/* ---------------------------------------------------------------- about */
const ICON = {
  data: '<path d="M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3Z"/><path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6"/><path d="M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
  rate: '<path d="M4 20V10"/><path d="M10 20V4"/><path d="M16 20v-7"/><path d="M22 20H2"/>',
  adjust: '<circle cx="7" cy="7" r="2.5"/><circle cx="17" cy="17" r="2.5"/><path d="M9.5 7H21M3 17h11.5M3 7h1.5M19.5 17H21"/>',
  lock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  team: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3v18M6 5.5c3 3 3 10 0 13M18 5.5c-3 3-3 10 0 13"/>',
  player: '<circle cx="12" cy="7" r="3.5"/><path d="M5 21v-2a5 5 0 0 1 5-5h4a5 5 0 0 1 5 5v2"/>',
  who: '<path d="M9 11l3 3 7-7"/><path d="M20 12v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h9"/>',
  body: '<path d="M12 21s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 11c0 5.6-7 10-7 10Z"/>',
  mind: '<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 0-4 10.5c.7.7 1 1.5 1 2.5h6c0-1 .3-1.8 1-2.5A6 6 0 0 0 12 3Z"/>',
  market: '<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
};
const ic = (k, size = 22) => `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON[k]}</svg>`;

async function about() {
  const a = await get("accuracy.json");
  setTitle("How it works");
  const tuned = META.tuned || {};
  const step = (n, k, title, text) => `<div class="hw-step"><div class="hw-n"><span>${n}</span>${ic(k, 20)}</div><h3>${title}</h3><p>${text}</p></div>`;
  const card = (k, color, title, line, more) => `<details class="hw-card" style="--c:${color}"><summary><span class="hw-ic">${ic(k)}</span><span><b>${title}</b><span class="hw-line">${line}</span></span><span class="hw-plus" aria-hidden="true">+</span></summary><div class="hw-more">${more}</div></details>`;
  const spot = (name, what) => `<div class="hw-spot"><b>${name}</b><span>${what}</span></div>`;
  const proof = (big, label, note) => `<div class="hw-proof"><p class="v">${big}</p><p class="k">${label}</p><p class="s">${note}</p></div>`;
  app.innerHTML = `<div class="wrap tn">${demoBanner()}
  <section class="tn-hero"><div class="lead"><p class="eyebrow">How it works</p><h1>From box scores<br>to tonight's picks.</h1>
    <p class="sublede">Every game goes through the same four steps. Everything that moves a number has been measured on past games, and the model only keeps an idea when it improves results on games it has never seen.</p></div></section>

  <section class="hw-steps" aria-label="The four steps">
    ${step(1, "data", "Collect", "Every result and box score of the last six seasons, tonight's injury report, starting fives, referee crews, and Winamax and Pinnacle prices, refreshed up to every 15 minutes before tip-off.")}
    ${step(2, "rate", "Rate", "How good each team is from its results, and how good the players who will actually play are, each rated alongside his teammates and opponents.")}
    ${step(3, "adjust", "Adjust", "Rest, travel, missing players, shooting luck and the psychological spots that have actually mattered in the past, each sized by the data.")}
    ${step(4, "lock", "Decide", "Blend with Pinnacle's price, simulate every game thousands of times, then choose the day's tickets once, three hours before tip-off, and lock them.")}
  </section>

  <section class="tn-sec"><div class="hd"><div><h2>What goes into a game</h2><p class="sub2">Tap any card for the detail.</p></div></div>
    <div class="hw-grid">
      ${card("team", "#8EC5FF", "Team ratings", "Attack and defence from every result, recent games counting most.",
        `<p>For every game: points = league average + home court + the team's attack − the opponent's defence, fitted on all results at once. Recent games count more (half-life ${tuned.half_life ?? "–"} days), last season is discounted (×${tuned.carry ?? "–"}) because rosters change, and every team is pulled towards average until the evidence is there.</p>`)}
      ${card("player", "#3DF0A5", "Player strength", "The team is the sum of the players who actually play tonight.",
        `<p>Each player carries three ratings: a box-score rating, his plus-minus, and an <b>adjusted plus-minus</b> measured alongside his teammates and opponents, so a bench player is not credited for his starters' work. A team's strength is the sum over tonight's players, weighted by expected minutes, so it reacts to injuries, rest days and trades straight away.</p><p>Tested on later seasons it made the win chances clearly better (2025-26: Brier 0.2029 → 0.1996), most of all in the first weeks of a season, when rosters have changed.</p>`)}
      ${card("who", "#FFB86B", "Who plays", "Injury reports, starting fives and the chance a star sits.",
        `<p>Each game's own injury report is read, and its statuses are checked against who really played, so "questionable" means what it has meant in practice. Once ESPN posts the starting fives, a starter plays whatever the report said.</p><p>Earlier in the day a key player with no news still sits about 6% of the time, about 9% on the second night of a back-to-back and about 13% late in the season. Until the news is in, his minutes count at that chance.</p>`)}
      ${card("body", "#FF8A7A", "Rest and travel", "Back-to-backs, time zones, distance, and who is missing.",
        `<p>Back-to-backs and three games in four nights, days of rest, time zones crossed heading east, distance travelled since the last game, and the share of the team's regular production that is missing tonight.</p>`)}
      ${card("mind", "#B79CFF", "The mind", "Momentum, letdowns, revenge and stakes, sized by what actually happened.",
        `<p>Every story basketball people tell becomes a precise condition, and its size comes from what happened in thousands of past games. A story the data doesn't support ends up worth almost nothing. See the spots below.</p>`)}
      ${card("market", "#5AA9FF", "The market", "Pinnacle's price, the sharpest in the world, blended in.",
        `<p>Pinnacle often prices in news the model can't see. On 1,368 past games, a 40% model / 60% Pinnacle blend of the win chances beat both on their own, so every game with a Pinnacle price shows the blend. Winamax's prices are compared with Pinnacle's fair price on the Tonight page: when Winamax pays more, it's marked as value.</p>`)}
    </div></section>

  <section class="tn-sec"><div class="hd"><div><h2>The mental game</h2><p class="sub2">The psychological spots the model checks before every game. Each one's size is measured, not assumed.</p></div></div>
    <div class="hw-spots">
      ${spot("Streak", "a winning or losing run")}${spot("Confidence", "beating or missing expectations lately")}${spot("Bounce-back", "after a heavy defeat")}
      ${spot("Letdown", "after beating a top team, facing a weak one")}${spot("Revenge", "lost the last meeting")}${spot("Look-ahead", "a big game coming up next")}
      ${spot("Homecoming", "first game home after a long trip")}${spot("Long road trip", "fourth straight game away")}${spot("Stakes", "a race for a playoff place, or nothing left to play for")}
      ${spot("Elimination", "one more loss ends the season")}${spot("Former team", "a player facing his old club")}${spot("Hot hand", "a player beating his projection lately")}
    </div></section>

  <section class="tn-sec"><div class="hd"><div><h2>Proven, not assumed</h2><p class="sub2">Every change is trained on earlier seasons and scored on the next one. These are some of the results.</p></div></div>
    <div class="hw-proofs">
      ${proof("68–70%", "winners called", "on full past seasons; the betting market itself sits around 68–71%")}
      ${proof("4.59", "points missed per player", "on average this season, measured before each game (4.72 before today's changes)")}
      ${proof("1.0", "calibration factor", "player-leg chances need almost no correction: 60% lands about 60% of the time")}
      ${proof("20+", "ideas tested today", "about half were kept; play-style matchups, coaching and a second model type were left out")}
    </div></section>

  <section class="tn-sec"><div class="hd"><div><h2>A day of tickets</h2><p class="sub2">The same rhythm every game day.</p></div></div>
    <ol class="hw-time">
      <li><span class="dot"></span><b>All day</b><span>Estimates and prices update as news comes in.</span></li>
      <li><span class="dot"></span><b>3 hours before tip-off</b><span>The full model picks the tickets once, explains each in plain words, and locks them.</span></li>
      <li><span class="dot"></span><b>Tip-off</b><span>Every estimate is frozen and can never be changed afterwards.</span></li>
      <li><span class="dot"></span><b>After the buzzer</b><span>Everything is scored: winners, tickets, legs, and how your prices compared with Pinnacle's closing price.</span></li>
    </ol></section>

  <section class="tn-sec duo2" style="align-items:start">
    <div><h2 style="font-size:28px;margin:0">Keeping it honest</h2><ul class="hw-checks">
      <li>${ic("check", 18)}<span>Estimates are frozen at tip-off; the public history of the site proves each one existed before the game.</span></li>
      <li>${ic("check", 18)}<span>The model is always compared with plain averages and with itself without the psychological layer.</span></li>
      <li>${ic("check", 18)}<span>Safety checks run before every update; a bad run never reaches the site.</span></li>
      <li>${ic("check", 18)}<span>The live record is the headline number, not the research figures.</span></li></ul></div>
    <div><h2 style="font-size:28px;margin:0">Limits</h2><ul class="hw-checks warn">
      <li>${ic("clock", 18)}<span>Psychology is noisy: most spots are worth a point or two at most.</span></li>
      <li>${ic("clock", 18)}<span>A late scratch after the last refresh isn't in the numbers.</span></li>
      <li>${ic("clock", 18)}<span>About 3 in 10 games go against even the best estimate. That is basketball.</span></li>
      <li>${ic("clock", 18)}<span>Statistical estimates, not advice. 18+.</span></li></ul></div>
  </section>

  <details class="hw-deep"><summary>The full technical detail</summary><div class="prose">
    <p><b>Margins and totals</b> are treated as normally distributed around the estimate with the spread of past misses (${a.sd_margin ?? "–"} points for margins, ${a.sd_total ?? "–"} for totals); the win chance is the share of that distribution on each side of zero.</p>
    <p><b>Factor sizes</b>: the ratings make an out-of-sample prediction for every past game (refit weekly on earlier games only); what they missed is regressed on all factors at once, with a penalty that pulls each towards zero unless the evidence is there. Each gets its size, its uncertainty and a label: strong, moderate, weak or no clear evidence. Current sizes are on the <a href="#/accuracy">Record</a> page.</p>
    <p><b>Players</b>: expected minutes (a minutes model fitted on earlier games, scaled so each team's minutes add up to 240) × per-minute production × the opponent, then the measured player effects (hot hand, matchup history, minutes and points without a key teammate, returns, back-to-backs). Over/under chances use a count distribution fitted to each stat.</p>
    <p><b>Tickets</b>: every winner, handicap, total and player leg is checked; each game is simulated 20,000 times so legs from the same game are priced together; the Value 2 (main pick), Core 3, Same-game 3 and the daily 6 (long shot) are chosen once, three hours before the first tip-off.</p>
    <p><b>Quarters, playoff chances, mind ranking</b>: the estimate split by each team's usual share per quarter; the rest of the season simulated 4,000 times with the play-in; and a description of each team's state next to its measured psychological edge.</p>
  </div></details>
  </div>`;
}

/* ---------------------------------------------------------------- search & routing */
function setupSearch() {
  const f = document.querySelector("[data-search]");
  const input = f.querySelector("input"), drop = f.querySelector(".drop");
  const close = () => { drop.hidden = true; };
  input.addEventListener("input", async () => {
    const q = input.value.trim().toLowerCase();
    if (!q) return close();
    const hits = Object.values(TEAMS).filter(t => (t.name + " " + t.abbr).toLowerCase().includes(q)).slice(0, 5);
    let ps = [];
    if (q.length >= 2) { try { ps = (await get("players.json")).filter(p => p.name.toLowerCase().includes(q)).slice(0, 8); } catch (e) { ps = []; } }
    if (input.value.trim().toLowerCase() !== q) return;
    drop.innerHTML = hits.length || ps.length
      ? hits.map(t => `<a href="#/team/${t.abbr}">${disc(t.abbr, "xs")}${h(t.name)}<span class="sub">${h(t.record)}</span></a>`).join("")
        + ps.map(p => `<a href="#/player/${p.id}">${disc(p.team, "xs")}${h(p.name)}<span class="sub">${fx(p.ppg)} ppg</span></a>`).join("")
      : `<p class="sub" style="padding:8px">Nothing found.</p>`;
    drop.hidden = false;
  });
  f.addEventListener("submit", e => { e.preventDefault(); const a = drop.querySelector("a"); if (a) { location.hash = a.getAttribute("href"); close(); input.value = ""; } });
  document.addEventListener("click", e => { if (!f.contains(e.target)) close(); });
  window.addEventListener("hashchange", () => { close(); input.value = ""; });
}

async function route() {
  app.oninput = app.onchange = app.onclick = null;
  const parts = location.hash.replace(/^#\/?/, "").split("/");
  const [page, arg] = parts;
  document.querySelectorAll("[data-nav]").forEach(a => a.setAttribute("aria-current", a.dataset.nav === (page || "home") || (page === "game" && a.dataset.nav === "games") || (page === "team" && a.dataset.nav === "teams") || (page === "player" && a.dataset.nav === "players") ? "page" : "false"));
  const more = document.querySelector("[data-nav-more]");
  if (more) {
    more.setAttribute("aria-current", document.querySelector(".more-menu [aria-current='page']") ? "page" : "false");
    more.parentElement.open = false;
  }
  // leave: a quick fade of the old page while the next one loads
  app.classList.remove("entering");
  app.classList.add("leaving");
  const leaveDone = new Promise(r => setTimeout(r, REDUCED ? 0 : 140));
  if (!app.firstElementChild || app.querySelector(".loading")) app.innerHTML = skeleton();
  try {
    await leaveDone;
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
    else if (page === "about") await about();
    else await home();
  } catch (err) {
    app.innerHTML = `<div class="wrap" style="padding-top:40px"><p class="empty">Couldn't load this page (${h(err.message)}).</p><p><a href="#/">Back home</a></p></div>`;
  }
  window.scrollTo(0, 0);
  app.classList.remove("leaving");
  void app.offsetWidth;  // restart the entrance animation
  app.classList.add("entering");
  enhance(app);
  syncAddButtons();
  renderSlip();
  app.focus({ preventScroll: true });
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
    pill.innerHTML = `<span class="dot ${bad ? "bad" : ""}"></span>Updated ${hm(META.updated)} · ${blocked ? "showing last good version" : chk ? (chk.ok ? "Safety checks passed" : "Safety checks failed") : "checks pending"}`;
    pill.hidden = false;
  }
}

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
  return LS.get("tipoff.pick." + slipDay(), []).map(id => pool.get(id) || extra[id]).filter(Boolean);
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
const addBtn = (l, label = "") => `<button type="button" class="addleg" data-add="${h(l.id)}"${l._synthetic ? ` data-leg="${h(JSON.stringify(l))}"` : ""} aria-pressed="false" aria-label="Add ${h(legDesc(l))} to your ticket"><span class="plus">+</span><span class="tick">✓</span>${label}</button>`;
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
function ptags(p) {
  return (p.out ? `<span class="ptag out">${h(p.status || "Out")}</span>` : p.status ? `<span class="ptag q">${h(p.status)}</span>` : "")
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

const STATW = { pts: "pts", reb: "reb", ast: "ast", tpm: "3s", pra: "pra" };
function legFor(p, b) {
  // the curated leg for this player and line if tonight's list has it, else one built from his projection
  const hit = [...slipPool().values()].find(l => l.kind === "prop" && String(l.player) === String(p.id) && l.stat === b.stat && Math.abs(l.line - b.line) < 0.01 && l.side === "over");
  return hit || propLeg(p.id, p.name, p.team, p.next_game, p.next_tip, p.next_opp, p.next_home, b.stat, b.line, b.over);
}
function gameBuilder(g) {
  const gid = String(g.id || g.game_id || location.hash.split("/")[2]);
  const legs = [...slipPool().values()].filter(l => String(l.game) === gid).sort((a, b) => b.p - a.p).slice(0, 12);
  if (!legs.length || g.kind !== "estimate") return "";
  return `<section class="section"><h2>Build a ticket from this game <span class="sub">tonight's checked legs; tap + to add</span></h2>
    <div class="bb">${legs.map(l => `<div class="bb-leg"><span class="kind ${l.kind}">${KIND[l.kind] || l.kind}</span><span class="grow">${h(legDesc(l))}</span><span class="num sub">${pct(effP(l))}</span><b class="num">${fx(1.05 / effP(l), 2)}+</b>${addBtn(l)}</div>`).join("")}</div></section>`;
}
function playerCard(p) {
  const ink = teamInk(p.team);
  return `<article class="pc" style="--c:${ink}">
    <div class="pc-top">${mono(p.team, "sm")}<div class="grow"><a class="pc-name" href="#/player/${h(p.id)}">${h(p.name)}</a>
      <span class="sub small">${p.next_home ? "vs" : "at"} ${h(T(p.next_opp).short)} · ${tipTime(p.next_tip)}${p.pos ? ` · ${h(p.pos)}` : ""}</span></div>
      ${p.status ? `<span class="ptag q">${h(p.status)}</span>` : ""}</div>
    <div class="pc-nums">${[["Points", p.next_pts], ["Rebounds", p.next_reb], ["Assists", p.next_ast], ["Threes", p.next_tpm]].map(([k, v]) => `<div><b class="num">${v == null ? "–" : fx(v, 1)}</b><span>${k}</span></div>`).join("")}</div>
    ${(p.next_best || []).length ? `<div class="pc-legs">${p.next_best.map(b => { const l = legFor(p, b); return `<div class="pc-leg"><span>${Math.ceil(b.line)}+ ${STATW[b.stat] || b.stat}</span><b class="num">${pct(b.over)}</b>${addBtn(l)}</div>`; }).join("")}</div>` : ""}
    ${p.sim_lines ? `<p class="pc-sim">In ${Number(p.sim_lines.n).toLocaleString("en-GB")} simulations: ${Object.entries(p.sim_lines).filter(([k]) => k !== "n").slice(0, 2).map(([st, v]) => `${Math.ceil(v.line)}+ ${STATW[st] || st} in <b>${Math.round(v.over * p.sim_lines.n).toLocaleString("en-GB")}</b>`).join(" · ")}</p>` : ""}
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
  const W = 520, H = 150, pad = 22, bw = (W - pad * 2) / g.length;
  const mx = Math.max(10, ...g.map(x => Math.max(x.pts, x.proj ? x.proj.pts : 0))) * 1.1;
  const y = v => H - pad - v / mx * (H - pad * 2);
  return `<svg class="formchart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Points in recent games">
    ${g.map((x, i) => `<rect x="${pad + i * bw + 3}" y="${y(x.pts)}" width="${bw - 6}" height="${H - pad - y(x.pts)}" rx="3" fill="${x.win ? "var(--pos)" : "var(--neg)"}" opacity=".8"><title>${day(x.day)} ${x.home ? "vs" : "at"} ${x.opp}: ${x.pts} pts</title></rect>
      ${x.proj ? `<line x1="${pad + i * bw + 1}" x2="${pad + (i + 1) * bw - 1}" y1="${y(x.proj.pts)}" y2="${y(x.proj.pts)}" stroke="var(--ink)" stroke-width="2.5"/>` : ""}
      <text x="${pad + i * bw + bw / 2}" y="${y(x.pts) - 4}" text-anchor="middle">${x.pts}</text><text x="${pad + i * bw + bw / 2}" y="${H - 6}" text-anchor="middle">${h(T(x.opp).abbr)}</text>`).join("")}
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
    ${p.log.map(r => `<tr><td><a href="#/game/${r.id}">${day(r.day)}</a></td><td>${r.home ? "vs" : "@"} ${h(T(r.opp).abbr)}</td><td class="${r.win ? "up" : "down"}">${r.win ? "W" : "L"} ${h(r.score)}</td><td class="n">${r.min}</td><td class="n hl">${r.pts}</td><td class="n sub">${r.proj ? fx(r.proj.pts) : "–"}</td><td class="n">${r.reb}</td><td class="n">${r.ast}</td><td class="n">${r.tpm ?? "–"}</td><td class="n">${r.stl ?? "–"}</td><td class="n">${r.blk ?? "–"}</td><td class="n">${r.tov ?? "–"}</td><td class="n">${r.fg ?? "–"}</td><td class="n">${r.tp ?? "–"}</td><td class="n">${r.ft ?? "–"}</td><td class="n">${sgn(r.pm, 0)}</td></tr>`).join("")}</table></div>`;
  app.innerHTML = `<section class="gh ph" style="--ca:${teamInk(p.team)};--ch:${teamInk(p.team)}"><div class="wrap">
    <div class="ph-main"><div class="ph-num num">${h(p.jersey ?? p.pos ?? "")}</div>
      <div class="ph-id"><p class="eyebrow">${h(p.pos || "")} · <a href="#/team/${p.team}">${h(t.name)}</a>${p.former.length ? ` · formerly ${p.former.map(x => h(T(x).short)).join(", ")}` : ""}</p><h1>${h(p.name)}</h1></div></div>
    <div class="ph-tiles">${[["Points", fx(c.ppg)], ["Rebounds", fx(c.rpg)], ["Assists", fx(c.apg)], ["Minutes", fx(c.mpg)], ["True shooting", c.ts == null ? "–" : (c.ts * 100).toFixed(1) + "%"], ["Usage", c.usg == null ? "–" : fx(c.usg) + "%"], ["Games", c.gp ?? 0]].map(([k, v]) => `<div class="tile"><p class="k">${k}</p><p class="v num">${v}</p></div>`).join("")}</div>
  </div></section>
  <div class="wrap">${demoBanner()}
    ${p.story.length ? `<p class="call"><b>Storylines:</b> ${p.story.map(h).join(" ")}</p>` : ""}
    <section class="grid2" style="margin-top:14px">${nextHtml}<div class="panel"><h3>Recent games</h3><p class="sub small">Points per game, newest right; bars green in wins, red in losses; the dark line is what the model projected before the game.</p>${formChart(p.log)}</div></section>
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
  app.innerHTML = `<section class="hero court"><div class="wrap"><h1>Mind ranking</h1><p class="sub" style="margin-top:8px">Every team's state of mind right now: momentum from the current streak, the last ten games and how far recent results beat what the ratings expected; plus who is in a race, who is coasting and who is short-handed. On the right, the measured psychological edge each team carries into its next games.</p></div></section>
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

/* ---------------------------------------------------------------- daily parlay */
const KIND = { ml: "Winner", spread: "Handicap", total: "Total", team_total: "Team total", prop: "Player" };
const LS = {
  get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* storage unavailable */ } },
};
let PAR = null;
/* line edits: the chance at whatever line Winamax lists */
function ncdf(x) { const t = 1 / (1 + 0.2316419 * Math.abs(x)), d = 0.3989423 * Math.exp(-x * x / 2); const p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274)))); return x > 0 ? 1 - p : p; }
const lgt = p => Math.log(Math.max(p, 1e-6) / Math.max(1 - p, 1e-6)), sgm = x => 1 / (1 + Math.exp(-x));
const lineOf = l => { const v = LS.get(`tipoff.line.${l.id}`, null); return v == null ? l.line : v; };
/* player counts: negative binomial, mean mu, variance mu x dispersion (as on the server) */
function nbOver(L, mu, disp) {
  mu = Math.max(mu, 0.05); const d = Math.max(disp, 1.02), kMax = Math.floor(L);
  if (kMax < 0) return 1;
  const r = mu / (d - 1), q = 1 / d; let pk = Math.exp(r * Math.log(q)), cdf = pk;
  for (let k = 0; k < kMax; k++) { pk *= (k + r) / (k + 1) * (1 - q); cdf += pk; }
  return Math.min(1, Math.max(0, 1 - cdf));
}
function effP(l) {
  const L = lineOf(l);
  if (!l.dist || L == null || L === l.line) return l.p;
  const d = l.dist;
  let pm;
  if (l.kind === "spread") pm = ncdf((d.mu + L) / d.sd);
  else { const po = d.d ? nbOver(L, d.mu, d.d) : 1 - ncdf((L - d.mu) / d.sd); pm = l.side === "under" ? 1 - po : po; }
  const o = oddsOf(l.id);
  return o ? sgm(0.5 * lgt(sgm(d.model * lgt(pm))) + 0.5 * lgt(1 / (o * 1.05))) : sgm(d.alone * lgt(pm));
}
const STATN = { pts: "points", reb: "rebounds", ast: "assists", tpm: "threes", pra: "pts+reb+ast" };
function legDesc(l) {
  const L = lineOf(l);
  if (l.kind === "prop") return l.side === "over" && Number.isFinite(+L) ? `${l.player_name} ${Math.ceil(+L)}+ ${STATN[l.stat] || l.stat} (over ${fx(L)})` : `${l.player_name} ${l.side} ${fx(L)} ${STATN[l.stat] || l.stat}`;
  if (l.kind === "total") return `${l.side === "over" ? "Over" : "Under"} ${fx(L)} points`;
  if (l.kind === "spread") return `${T(l.team).short} ${L > 0 ? "+" : ""}${fx(L)} handicap`;
  if (l.kind === "ml") return `${T(l.team).short} to win`;
  if (l.kind === "team_total") return `${T(l.team).short} ${l.side} ${fx(l.line)} team points`;
  return l.desc;
}
const matchTeams = l => l.matchup.split(" at ");
const oddsOf = id => LS.get(`tipoff.odds.${id}`, null);
function verdict(p, odds) {
  if (!odds || odds <= 1) return { cls: "", txt: "type the Winamax odds" };
  const ev = p * odds - 1;
  return ev >= 0.02 ? { cls: "up", txt: `Take: ${sgn(ev * 100, 0)}% value` } : ev >= 0 ? { cls: "flat", txt: `Borderline: ${sgn(ev * 100, 1)}%` } : { cls: "down", txt: `Skip: ${sgn(ev * 100, 0)}% value` };
}
function oddsCell(l) {
  const o = oddsOf(l.id), v = verdict(effP(l), o);
  const line = l.dist && l.line != null ? `<input class="linein" type="number" inputmode="decimal" step="0.5" value="${lineOf(l)}" data-leg="${l.id}" title="Type the line Winamax shows" aria-label="Winamax line">` : "";
  return `<span class="oddsbox"><span class="ins">${line}<input class="oddsin" type="number" inputmode="decimal" step="0.01" min="1.01" placeholder="Winamax odds" value="${o ?? ""}" data-leg="${l.id}" aria-label="Winamax odds for ${h(legDesc(l))}"></span><span class="vd ${v.cls}" data-vd="${l.id}">${v.txt}</span></span>`;
}
function legIndex() {
  const t = PAR && PAR.today, m = {};
  if (t) [...(t.parlays || []).flatMap(p => p.legs), ...(t.board || []), ...(t.singles || [])].forEach(l => { m[l.id] = l; });
  return m;
}
function legRow(l, i) {
  const res = l.result ? ` ${l.result}` : "";
  const bookName = b => ({ winamax_fr: "Winamax", pinnacle: "Pinnacle" }[b] || b);
  const mkt = l.price && !l.price_est ? `${bookName(l.book || "market")} ${fx(l.price, 2)}${l.edge != null ? ` (${sgn(l.edge * 100, 0)}% value)` : ""}` : (l.price_est ? `check line ${fx(l.line)}` : "no market price");
  const clv = l.clv ? ` · CLV ${l.clv.p != null ? sgn(l.clv.p * 100, 1) + " pts of chance" : sgn(l.clv.pts) + " pts of line"}` : "";
  return `<li class="${res.trim()}"><span class="no">${i + 1}</span>
    <span class="d"><span class="kind ${l.kind}">${KIND[l.kind] || l.kind}</span><b data-d="${l.id}">${h(legDesc(l))}</b><span class="mflag ${l.mind_flag}">${l.mind_flag === "with" ? "mind with it" : l.mind_flag === "against" ? "mind against" : "mind neutral"}</span>
    <span class="sub"><a href="#/game/${h(l.game)}">${h(T(matchTeams(l)[0]).short)} at ${h(T(matchTeams(l)[1]).short)}</a> · ${tip(l.tip)} · ${h(l.note || "")} · market: ${h(mkt)}${clv}${l.result ? ` · <b class="${l.result === "hit" ? "up" : l.result === "miss" ? "down" : ""}">${l.result}</b>` : ""}${l.story ? `<br><span class="story">${h(l.story)}</span>` : ""}${l.alert ? `<br><b class="down">⚠ ${h(l.alert)}</b>` : ""}${l.swap ? `<br>Suggested swap: <b>${h(l.swap.desc)}</b> (${h(l.swap.matchup || "")}, ${pct(l.swap.p)})` : ""}</span></span>
    <span class="c"><b data-p="${l.id}">${pct(effP(l))}</b><span>chance</span></span><span class="c"><b data-f="${l.id}">${fx(1 / effP(l), 2)}</b><span data-m="${l.id}">fair · take ≥ ${fx(1.05 / effP(l), 2)}</span></span>${oddsCell(l)}</li>`;
}
function jointOf(legs) {
  const lifts = (PAR && PAR.today && PAR.today.lifts) || {};
  let p = 1;
  legs.forEach(l => { p *= effP(l); });
  for (let i = 0; i < legs.length; i++) for (let j = i + 1; j < legs.length; j++) {
    const a = legs[i].id, b = legs[j].id;
    p *= lifts[`${a}|${b}`] || lifts[`${b}|${a}`] || 1;
  }
  return Math.min(p, Math.min(...legs.map(effP)));
}
function ticketValue(legs, p) {
  p = p * legs.reduce((a, l) => a * effP(l) / l.p, 1);
  const odds = legs.map(l => oddsOf(l.id));
  if (odds.some(o => !o)) return `<b>–</b>your combined odds: type Winamax odds for all ${legs.length} legs`;
  const prod = odds.reduce((a, b) => a * b, 1), ev = p * prod - 1;
  return `<b class="${ev >= 0 ? "up" : "down"}">${fx(prod, 2)}</b>your combined odds · chance ${pct(p)} · ${ev >= 0 ? "worth it" : "not worth it"}: ${sgn(ev * 100, 0)}% value`;
}
function ticketText(pr) {
  return `${pr.name} — Tip-Off Numbers\n` + (pr.story ? `${pr.story}\n` : "") + pr.legs.map((l, i) => `${i + 1}. ${legDesc(l)} (${T(matchTeams(l)[0]).abbr} @ ${T(matchTeams(l)[1]).abbr}) — ${pct(l.p)}, take at ${fx(l.min_odds, 2)}+${l.story ? `\n   ${l.story}` : ""}`).join("\n")
    + `\nAll legs: ${pct(pr.p)} · fair combined odds ${fx(pr.fair, 2)} · worth it at ${fx(pr.min_odds, 2)}+`;
}
function ticket(pr, main, idx) {
  return `<div class="ticket ${main ? "main" : ""}"><div class="ticket-head"><div><h3>${h(pr.name)}${pr.result ? ` <span class="cat ${pr.result === "hit" ? "Hot" : "Cold"}">${pr.result}</span>` : ""}</h3><p>${h(pr.why || "")}</p>${pr.story ? `<p class="story"><b>Why this ticket:</b> ${h(pr.story)}</p>` : ""}</div>
    <span><button class="copybtn" data-copy="${h(ticketText(pr))}">Copy ticket</button> <button class="copybtn" data-record="${idx}">Record as my bet</button></span></div>
    <ul class="legs">${pr.legs.map(legRow).join("")}</ul>
    <div class="ticket-foot"><div><b>${pct(pr.p)}</b>chance all ${pr.n_legs} land</div><div><b>${fx(pr.fair, 2)}</b>fair combined odds</div>
      <div class="go"><b>${fx(pr.min_odds, 2)}+</b>worth placing at these combined odds or better</div>
      <div><b>${pr.lift >= 1 ? "+" : ""}${Math.round((pr.lift - 1) * 100)}%</b>correlation lift</div>
      ${pr.games < pr.n_legs && Math.abs(pr.lift - 1) >= 0.03 ? `<p class="lift-note">${pr.lift > 1 ? "In the game simulations these legs land together more often than chance would say" : "In the game simulations these legs tend to pull against each other, so landing all of them is a little less likely than the single chances suggest"}.</p>` : ""}
      <div class="you" data-tv="${idx}">${ticketValue(pr.legs, pr.p)}</div></div></div>`;
}

/* my bets (kept in this browser) */
const BETS_KEY = "tipoff.bets";
function recordBet(name, legs, p) {
  const odds = legs.map(l => oddsOf(l.id));
  const stake = parseFloat((document.getElementById("stake") || {}).value) || null;
  const bets = LS.get(BETS_KEY, []);
  bets.unshift({ at: new Date().toISOString(), name, p, stake, odds: odds.every(Boolean) ? odds.reduce((a, b) => a * b, 1) : null,
    legs: legs.map((l, i) => ({ id: l.id, desc: legDesc(l), kind: l.kind, line: lineOf(l), side: l.side, team: l.team, game: l.game, p: effP(l), odds: odds[i] })) });
  LS.set(BETS_KEY, bets);
}
function betClv(leg) {
  const c = PAR && PAR.leg_close && PAR.leg_close[leg.id];
  if (!c) return null;
  if (leg.odds && c.pin_fair) return { txt: `${sgn((leg.odds * c.pin_fair - 1) * 100, 1)}% vs Pinnacle's closing fair odds ${fx(1 / c.pin_fair, 2)}`, v: leg.odds * c.pin_fair - 1 };
  if (leg.odds && c.price) return { txt: `${sgn((leg.odds / c.price - 1) * 100, 1)}% vs close ${fx(c.price, 2)}`, v: leg.odds / c.price - 1 };
  if (c.line != null && leg.line != null) {
    const d = leg.kind === "spread" ? leg.line - c.line : leg.side === "under" ? leg.line - c.line : c.line - leg.line;
    return { txt: `${sgn(d)} pts vs close ${fx(c.line)}`, v: d };
  }
  return null;
}
function myBets() {
  const bets = LS.get(BETS_KEY, []);
  if (!bets.length) return `<p class="sub">No bets recorded in this browser yet. Type the Winamax odds on a ticket and press "Record as my bet".</p>`;
  const res = (PAR && PAR.leg_results) || {};
  let clvN = 0, clvBeat = 0;
  const rows = bets.map((b, bi) => {
    const lr = b.legs.map(l => res[l.id]);
    const status = lr.some(r => r === "miss") ? "lost" : lr.every(r => r === "hit" || r === "void") && lr.length ? "won" : "open";
    const legs = b.legs.map(l => { const c = betClv(l); if (c) { clvN++; if (c.v > 0) clvBeat++; } return `<span class="${res[l.id] === "hit" ? "up" : res[l.id] === "miss" ? "down" : ""}">${res[l.id] === "hit" ? "✓" : res[l.id] === "miss" ? "✗" : "·"}</span> ${h(l.desc)}${l.odds ? ` @ ${fx(l.odds, 2)}` : ""}${c ? ` <span class="sub">(CLV ${h(c.txt)})</span>` : ""}`; }).join("<br>");
    const ev = b.odds ? b.p * b.odds - 1 : null;
    return `<tr><td class="small">${day(b.at.slice(0, 10))}</td><td>${h(b.name)}</td><td class="small">${legs}</td><td class="n">${b.odds ? fx(b.odds, 2) : "–"}</td><td class="n">${pct(b.p)}</td><td class="n ${ev == null ? "" : ev >= 0 ? "up" : "down"}">${ev == null ? "–" : sgn(ev * 100, 0) + "%"}</td><td class="n">${b.stake ?? "–"}</td><td class="${status === "won" ? "up" : status === "lost" ? "down" : "sub"}">${status}</td><td><button class="copybtn" data-del="${bi}">✕</button></td></tr>`;
  }).join("");
  return `${clvN ? `<p class="verdict"><b>Your closing-line value:</b> you beat the closing price on ${clvBeat} of ${clvN} legs (${pct(clvBeat / clvN)}). For winners the yardstick is Pinnacle's closing price with its margin removed: beating it on more than half of 200+ bets is the earliest reliable sign of a real edge.</p>` : ""}
    <div class="tscroll"><table><tr><th>Day</th><th>Ticket</th><th>Legs</th><th class="n">Odds</th><th class="n">Chance</th><th class="n">Value</th><th class="n">Stake</th><th>Status</th><th></th></tr>${rows}</table></div>`;
}

function custom() {
  const t = PAR && PAR.today;
  if (!t) return "";
  const legs = slipLegs();
  if (!legs.length) return `<p class="sub">Tick legs in the table below, or tap + on any leg anywhere on the site, to build your own ticket; same-game correlation is taken into account.</p>`;
  const p = jointOf(legs);
  return `<ul class="legs">${legs.map(legRow).join("")}</ul><div class="ticket-foot"><div><b>${pct(p)}</b>chance all ${legs.length} land</div><div><b>${fx(1 / p, 2)}</b>fair combined odds</div><div class="go"><b>${fx(1.05 / p, 2)}+</b>worth placing at</div><div class="you" data-tv="custom">${ticketValue(legs, p)}</div><div><button class="copybtn" data-record="custom">Record as my bet</button></div></div>`;
}

function refreshValues() {
  const t = PAR && PAR.today;
  if (!t) return;
  (t.parlays || []).forEach((pr, i) => { const el = app.querySelector(`[data-tv="${i}"]`); if (el) el.innerHTML = ticketValue(pr.legs, pr.p); });
  const cel = document.getElementById("custom");
  if (cel) cel.innerHTML = custom();
}

async function parlayPage() {
  const d = await get("parlay.json");
  PAR = d;
  setTitle("Daily parlay");
  const t = d.today;
  const rec = d.record || {};
  const clv = d.clv || {};
  const recHtml = Object.keys(rec).length ? `<div class="grid">${Object.entries(rec).map(([k, r]) => `<div class="panel"><h3>${h(k)}</h3><div class="adv"><div><b>${r.hits}/${r.n}</b>tickets landed<br>expected ${fx(r.expected, 1)}</div><div><b>${r.leg_hits}/${r.legs}</b>legs landed<br>expected ${fx(r.leg_expected, 1)}</div></div></div>`).join("")}</div>`
    : `<p class="note">No slate has been scored yet. Each day's tickets are frozen at the first tip-off and scored after the last game; nothing is ever changed afterwards.</p>`;
  const clvBox = (title, c, unit) => `<div class="panel"><h3>${title}</h3>${c && c.moved ? `<div class="adv"><div><b>${c.beat}/${c.moved}</b>moved our way<br>${pct(c.beat / c.moved)}</div>${c.avg_p != null ? `<div><b>${sgn(c.avg_p * 100, 2)}</b>avg chance points</div>` : ""}${c.avg_pts != null ? `<div><b>${sgn(c.avg_pts, 2)}</b>avg line points</div>` : ""}</div>` : `<p class="sub small">${unit}</p>`}</div>`;
  const mc = clv.model || {};
  const oa = d.odds_api || {};
  const oddsNote = oa.enabled ? `Real prices: ${h(oa.books || "")}${oa.remaining ? ` · ${h(oa.remaining)} API credits left this month` : ""}` : `Real Winamax prices are off: add a free The Odds API key as the GitHub secret ODDS_API_KEY to switch them on. Until then market prices come from ESPN's US feed.`;
  const hist = (d.history || []).length ? `<div class="tscroll"><table><tr><th>Day</th><th>Ticket</th><th class="n">Chance</th><th class="n">Fair odds</th><th>Legs</th><th>Result</th></tr>${d.history.flatMap(hd => hd.parlays.map(pr => `<tr><td>${day(hd.day)}</td><td>${h(pr.name)}</td><td class="n">${pct(pr.p)}</td><td class="n">${fx(pr.fair, 2)}</td><td class="small">${pr.legs.map(l => `<span class="${l.result === "hit" ? "up" : l.result === "miss" ? "down" : "sub"}">${l.result === "hit" ? "✓" : l.result === "miss" ? "✗" : "–"}</span> ${h(l.kind === "ml" ? T(l.team).short + " win" : l.desc)}`).join(" · ")}</td><td class="${pr.result === "hit" ? "up" : "down"}">${pr.result}</td></tr>`)).join("")}</table></div>` : "";
  const cal = d.calibration || {};
  const calHtml = `<div class="tscroll"><table><tr><th>Stat</th><th class="n">Shrink</th><th class="n">Lines tested</th><th>When we said… it happened</th></tr>${Object.entries(cal).map(([k, c]) => `<tr><td>${h({ pts: "Points", reb: "Rebounds", ast: "Assists", tpm: "Threes", pra: "Pts+Reb+Ast" }[k] || k)}</td><td class="n">${fx(c.t, 2)}</td><td class="n">${(c.n || 0).toLocaleString("en-GB")}</td><td class="small">${(c.bins || []).map(b => `${pct(b.p)} → ${pct(b.hit)}`).join(" · ") || "not enough history yet"}</td></tr>`).join("")}</table></div>`;
  const picked = t ? LS.get("tipoff.pick." + t.day, []) : [];
  const board = t && t.board ? `<div class="tscroll"><table class="ptable"><tr><th></th><th>Leg</th><th>Game</th><th class="n">Chance</th><th class="n">Fair</th><th class="n">Take at</th><th>Winamax line · odds</th><th>Mind</th></tr>${t.board.map(l => `<tr><td><input type="checkbox" class="pick" data-leg="${l.id}" ${picked.includes(l.id) ? "checked" : ""} aria-label="Add to my ticket"></td><td><span class="kind ${l.kind}">${KIND[l.kind]}</span><span data-d="${l.id}">${h(legDesc(l))}</span></td><td class="small"><a href="#/game/${h(l.game)}">${h(l.matchup)}</a></td><td class="n hl" data-p="${l.id}">${pct(effP(l))}</td><td class="n" data-f="${l.id}">${fx(1 / effP(l), 2)}</td><td class="n">${fx(l.min_odds, 2)}</td><td>${oddsCell(l)}</td><td><span class="mflag ${l.mind_flag}">${l.mind_flag}</span></td></tr>`).join("")}</table></div>` : "";
  const vr = d.value_record;
  const boosts = t ? LS.get("tipoff.boost." + t.day, {}) : {};
  const vEdge = (v, odds) => (v.fair_p == null || !odds) ? null : odds * v.fair_p - 1;
  const valueHtml = t && t.value && t.value.length ? `<div class="tscroll"><table class="ptable"><tr><th>Winner</th><th>Game</th><th class="n">Winamax</th><th class="n">Pinnacle fair odds</th><th class="n">Edge</th><th class="n">Our model</th><th>Boosted odds?</th></tr>${t.value.map(v => {
      const key = v.game + v.side, bo = boosts[key], e = vEdge(v, bo || v.price);
      return `<tr class="${v.value ? "hot" : ""}"><td><b>${h(T(v.team).short)}</b>${v.value ? ` <span class="pill strong">value</span>` : ""}</td><td class="small">${h(T(v.team).abbr)} vs ${h(T(v.opp).abbr)}</td><td class="n">${fx(v.price, 2)}</td><td class="n">${v.fair_odds ? fx(v.fair_odds, 2) : "–"}</td><td class="n ${e == null ? "" : e > 0 ? "up" : "down"}" data-vedge="${key}">${e == null ? "–" : sgn(e * 100, 1) + "%"}</td><td class="n">${v.model_p == null ? "–" : pct(v.model_p)}${v.agree === false ? ` <span class="sub small">disagrees</span>` : ""}</td><td><input class="boostin oddsin" data-vid="${key}" data-fair="${v.fair_p ?? ""}" type="number" step="0.01" min="1.01" placeholder="${fx(v.price, 2)}" value="${bo || ""}" aria-label="Boosted Winamax odds"></td></tr>`; }).join("")}</table></div>` : `<p class="sub">No Winamax and Pinnacle prices for this slate yet (they appear with the odds key, refreshed before tip-off).</p>`;
  const valueRec = vr && vr.n ? `<p class="verdict"><b>Track record of the value board:</b> ${vr.won}/${vr.n} won (Pinnacle's fair prices expected ${fx(vr.expected_won, 1)}), ${sgn(vr.profit, 2)} units at Winamax's prices for 1 unit each; ${vr.clv_beat}/${vr.clv_n} beat Pinnacle's closing price (average ${sgn((vr.clv_avg || 0) * 100, 1)}%).</p>` : "";
  const singles = t && t.singles && t.singles.length ? `<div class="ticket"><ul class="legs">${t.singles.map(legRow).join("")}</ul></div>` : `<p class="sub">No single market price is worth taking today.</p>`;
  app.innerHTML = `<section class="hero court"><div class="wrap"><h1>Daily parlay</h1>
    <p class="lede" style="margin-top:10px">${t ? `Slate of ${h(longDay(t.day))} (US date): ${t.games} game${t.games === 1 ? "" : "s"}, ${t.candidates} possible legs checked, ${t.eligible} worth considering. ${t.frozen ? "Frozen at the first tip-off." : `Updates every hour before the first tip-off (${tip(t.first_tip)}).`}` : "No games on the board right now."}</p></div></section>
  <div class="wrap">${demoBanner()}
    <p class="banner">Make every leg match Winamax: if Winamax lists a different line, type its line in the first box (the chance recalculates for that line), then type its odds in the second: the value appears instantly. A leg is worth taking only when its value is positive; if Winamax doesn't list the market at all, leave the leg out. Statistical estimates, not advice; 18+.</p>
    <p class="note">${oddsNote}</p>
    ${t && t.book ? `<p class="verdict"><b>Every leg below is listed on ${t.book === "winamax_fr" ? "Winamax" : h(t.book)}</b>, at its own line and price (from the last refresh: prices move, so check the slip). ${t.not_on_book && t.not_on_book.length ? `Not on ${t.book === "winamax_fr" ? "Winamax" : h(t.book)} yet, so left out: ${t.not_on_book.map(x => h(x.split(" at ").map(a => T(a).short).join(" at "))).join(", ")}.` : ""}</p>` : ""}
    <div class="principles">
      <div><span class="n">1</span><b>Every leg must stand alone</b>A leg goes in only if its chance beats its price. A parlay of bad bets is a worse bet, not a better one.</div>
      <div><span class="n">2</span><b>Fewer legs, less margin</b>The margin compounds with every leg: about 9% with two legs and around 24% with six at standard prices. The Value 2 is the main pick; the daily 6 is the optional long shot.</div>
      <div><span class="n">3</span><b>Beat the closing price</b>The quickest proof of an edge is getting better odds than the final price before tip-off, long before wins and losses can tell.</div>
      <div><span class="n">4</span><b>Psychology both ways</b>Team and player spots are inside the chances, and no leg is picked with a psychological spot working against it.</div>
    </div>
    <section class="section"><h2>Winamax vs Pinnacle <span class="sub">winners where Winamax pays more than the sharpest price</span></h2>
      <p class="sub small">Pinnacle's odds with its margin removed are the best available estimate of the true chance. When Winamax pays more than that, the bet profits in the long run whatever any model says. "Value" = an edge of 2% or more and our model not rating the side clearly lower. Got a boost (<i>cote boostée</i>)? Type the boosted odds: the edge recalculates against Pinnacle's fair price.</p>
      ${valueHtml}${valueRec}</section>
    ${t && t.locked === false ? `<section class="section"><div class="panel"><h3>Today's tickets are chosen at ${tip(t.lock_at)}</h3><p class="sub">Three hours before the first tip-off, once the main injury reports are in, the full model picks the day's tickets once. From then on they never change: no reshuffling on reload. If a player in a locked ticket is ruled out later, his leg is flagged (Winamax voids a leg whose player does not play).</p></div></section>`
      : t && t.parlays && t.parlays.length ? `${t.locked_at ? `<p class="verdict"><b>Locked at ${tip(t.locked_at)}:</b> these are today's tickets and they will not change.</p>` : ""}${t.parlays.map((pr, i) => ticket(pr, i === 0, i)).join("")}` : `<p class="empty">No ticket today: not enough legs pass the filters. That is an answer too.</p>`}
    <section class="section"><h2>Value singles <span class="sub">market prices worth taking on their own — the research favours these over parlays</span></h2>${singles}</section>
    <section class="section"><h2>Build your own ticket</h2><div class="panel"><div id="custom">${custom()}</div><p class="sub small" style="margin-top:10px">Optional stake to record with your bets (for your own log; the site never suggests stakes): <input id="stake" type="number" min="0" step="0.5" class="oddsin" style="width:90px"></p></div></section>
    <section class="section"><h2>My bets <span class="sub">kept in this browser only</span></h2><div id="mybets">${myBets()}</div>
      <p style="margin-top:10px"><button class="copybtn" id="exp">Export my bets</button> <label class="copybtn" style="display:inline-block">Import<input id="imp" type="file" accept="application/json" hidden></label></p></section>
    <section class="section"><h2>Closing-line value <span class="sub">did the market move our way after we published?</span></h2>
      <div class="grid">${clvBox("Ticket legs", clv.tickets, "Measured from the first frozen slate on.")}${clvBox("Every published leg", clv.all_legs, "Measured from the first frozen slate on.")}
      <div class="panel"><h3>Model vs market</h3>${mc.n ? `<div class="adv"><div><b>${mc.with}/${mc.n}</b>games where the closing price moved towards the model<br>${pct(mc.with / mc.n)}</div><div><b>${sgn((mc.avg_move_our_way || 0) * 100, 2)}</b>avg chance points our way</div></div>` : `<p class="sub small">Every game where the model disagreed with the opening price: did the closing price move towards the model? Fills in as games are played.</p>`}</div></div></section>
    <section class="section"><h2 class="mind">The bettor's mind <span class="sub">what research on bettors says goes wrong</span></h2><div class="grid2"><div class="panel mind"><ul class="checklist">
      <li><b>Decide the stake before you look at the payout.</b> Prospect theory: people overweight small chances of big wins, which is exactly what long tickets sell.</li>
      <li><b>Don't add a leg to make the odds look better.</b> Every extra leg adds margin; if a leg wasn't worth taking alone, it isn't worth taking in a ticket.</li>
      <li><b>No chasing.</b> After a loss, bettors take riskier bets to win it back; after a win, they feel skilled. Both change the bet, not the chances.</li>
      <li><b>Streaks are not memory.</b> A team or player being "due" is the gambler's fallacy; a hot hand is only real here if the measured effect says so.</li>
      <li><b>Distrust the story you like.</b> Confirmation bias makes the leg you want feel safer. The chance on this page doesn't know which team you support.</li>
      <li><b>Judge yourself on closing prices, not results.</b> A month of wins or losses is mostly luck; beating the closing price is skill.</li></ul></div>
      <div class="panel"><h3>How sure are the player chances?</h3><p class="sub small">Model chances are shrunk towards 50% by a factor fitted on past player-games (1.00 = no change needed), so "80%" should land about 80% of the time.</p>${calHtml}</div></div></section>
    <section class="section"><h2>Track record</h2>${recHtml}${hist}</section>
    <section class="section"><h2>All strong legs today <span class="sub">tick to build your own ticket</span></h2>${board}</section></div>`;
  app.oninput = e => {
    const bi = e.target.closest(".boostin[data-vid]");
    if (bi && t) {
      const all = LS.get("tipoff.boost." + t.day, {}), v = parseFloat(bi.value), fair = parseFloat(bi.dataset.fair);
      if (v > 1) all[bi.dataset.vid] = v; else delete all[bi.dataset.vid];
      LS.set("tipoff.boost." + t.day, all);
      const cell = app.querySelector(`[data-vedge="${bi.dataset.vid}"]`), row = t.value.find(x => x.game + x.side === bi.dataset.vid);
      const odds = v > 1 ? v : row.price, ed = isNaN(fair) ? null : odds * fair - 1;
      if (cell) { cell.textContent = ed == null ? "–" : sgn(ed * 100, 1) + "%"; cell.className = "n " + (ed == null ? "" : ed > 0 ? "up" : "down"); }
      return;
    }
    const inp = e.target.closest(".oddsin[data-leg], .linein[data-leg]");
    if (!inp) return;
    const id = inp.dataset.leg, v = parseFloat(inp.value);
    if (inp.classList.contains("linein")) LS.set(`tipoff.line.${id}`, isNaN(v) ? null : v);
    else LS.set(`tipoff.odds.${id}`, v > 1 ? v : null);
    const l = legIndex()[id];
    if (!l) return;
    const p = effP(l), vd = verdict(p, oddsOf(id));
    app.querySelectorAll(`[data-vd="${id}"]`).forEach(x => { x.className = `vd ${vd.cls}`; x.textContent = vd.txt; });
    app.querySelectorAll(`[data-p="${id}"]`).forEach(x => { x.textContent = pct(p); });
    app.querySelectorAll(`[data-f="${id}"]`).forEach(x => { x.textContent = fx(1 / p, 2); });
    app.querySelectorAll(`[data-m="${id}"]`).forEach(x => { x.textContent = `fair · take ≥ ${fx(1.05 / p, 2)}`; });
    app.querySelectorAll(`[data-d="${id}"]`).forEach(x => { x.textContent = legDesc(l); });
    app.querySelectorAll(`.${inp.classList.contains("linein") ? "linein" : "oddsin"}[data-leg="${id}"]`).forEach(x => { if (x !== inp) x.value = inp.value; });
    clearTimeout(app._t); app._t = setTimeout(refreshValues, 150);
  };
  app.onchange = e => {
    const cb = e.target.closest(".pick");
    if (cb && t) {
      const k = "tipoff.pick." + t.day;
      let p = LS.get(k, []);
      p = cb.checked ? [...new Set([...p, cb.dataset.leg])] : p.filter(x => x !== cb.dataset.leg);
      LS.set(k, p);
      document.getElementById("custom").innerHTML = custom();
      renderSlip();
      syncAddButtons();
    }
    if (e.target.id === "imp" && e.target.files[0]) {
      e.target.files[0].text().then(txt => { try { const inc = JSON.parse(txt); const cur = LS.get(BETS_KEY, []); const seen = new Set(cur.map(b => b.at)); LS.set(BETS_KEY, cur.concat(inc.filter(b => !seen.has(b.at)))); document.getElementById("mybets").innerHTML = myBets(); } catch (err) { /* bad file */ } });
    }
  };
  app.onclick = e => {
    const r = e.target.closest("[data-record]");
    if (r && t) {
      const k = r.dataset.record;
      if (k === "custom") { const legs = slipLegs(); if (legs.length) recordBet("My ticket", legs, jointOf(legs)); }
      else { const pr = t.parlays[+k]; recordBet(pr.name, pr.legs, pr.p * pr.legs.reduce((a, l) => a * effP(l) / l.p, 1)); }
      document.getElementById("mybets").innerHTML = myBets();
      r.textContent = "Recorded";
    }
    const del = e.target.closest("[data-del]");
    if (del) { const b = LS.get(BETS_KEY, []); b.splice(+del.dataset.del, 1); LS.set(BETS_KEY, b); document.getElementById("mybets").innerHTML = myBets(); }
    if (e.target.id === "exp") {
      const blob = new Blob([JSON.stringify(LS.get(BETS_KEY, []), null, 1)], { type: "application/json" });
      const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "tipoff-my-bets.json"; a.click();
    }
  };
}
