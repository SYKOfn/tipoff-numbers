/* Tip-Off Numbers: Pages: Tonight, games, standings, teams, a game, model accuracy, how it works.
   Plain scripts loaded in order (index.html); they share one global scope, no build step. */
"use strict";

/* ---------------------------------------------------------------- home */
/* ---------------------------------------------------------------- Tonight (home) */
function teamInk(ab) {
  // a team colour that reads on the dark ground: the primary if it is bright enough, else the alternate
  const t = T(ab), lum = c => { const n = parseInt((c || "#555").slice(1), 16); const r = n >> 16 & 255, g = n >> 8 & 255, b = n & 255; return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
  return lum(t.color) >= 60 ? t.color : (lum(t.alt) >= 60 ? t.alt : "#5B6070");
}
// team badge: dark letters on bright team colours, white on deep ones (always 4.5:1 or better)
const monoText = bg => { const n = parseInt(bg.slice(1), 16), f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
  const L = 0.2126 * f(n >> 16 & 255) + 0.7152 * f(n >> 8 & 255) + 0.0722 * f(n & 255); return (L + 0.05) / 0.05 > 1.05 / (L + 0.05) ? "#0A0B0F" : "#fff"; };
// team badge: the team's logo (ESPN's dark-background version) on a tile lit in the team colour; letters if no logo
const logoDark = t => t.logo ? t.logo.replace("/500/", "/500-dark/") : null;
const mono = (ab, cls = "") => { const t = T(ab), bg = teamInk(ab), lg = logoDark(t);
  return lg ? `<span class="mono lg ${cls}" style="--tc:${bg}" title="${h(t.name || t.abbr)}"><img src="${h(lg)}" alt="${h(t.abbr)}" loading="lazy" decoding="async"></span>`
    : `<span class="mono ${cls}" style="background:${bg};color:${monoText(bg)}">${h(t.abbr)}</span>`; };
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

/* ---------------------------------------------------------------- Tonight cards (one answer per card, details on tap) */
function dots(p, label = "nights like this") {
  const n = Math.max(0, Math.min(100, Math.round(p * 100)));
  return `<div class="dots" role="img" aria-label="Lands in ${n} of 100 ${label}"><div class="dg">${Array.from({ length: 100 }, (_, i) => `<i class="${i < n ? "on" : ""}"></i>`).join("")}</div>
    <p class="dc">Lands on <b>${n} of 100</b> ${label}</p></div>`;
}
function twLeg(l) {
  const teams = matchTeams(l), p = effP(l);
  return `<li class="tw-leg${l.alert ? " warn" : ""}"><details><summary><span class="w"><b>${h(legDesc(l))}</b><span class="m">${h(T(teams[0]).short)} at ${h(T(teams[1]).short)} · ${tipTime(l.tip)}</span></span><span class="c num">${pct(p)}</span></summary>
    ${l.story ? `<p class="why">${h(l.story)}</p>` : ""}${l.alert ? `<p class="alert">⚠ ${h(l.alert)}</p>` : ""}${l.swap ? `<p class="swap">Suggested swap: <b>${h(l.swap.desc)}</b> · ${h(l.swap.matchup || "")} · ${pct(l.swap.p)}</p>` : ""}
    <p class="m">Worth taking alone at ${fx(1.05 / p, 2)}+ · <a href="#/game/${h(l.game)}">game page</a></p></details></li>`;
}
function twCard(pr, i, main) {
  const head = `<div class="tw-hd"><div><p class="tw-tag">${main ? "Main pick" : pr.name === "The daily 6" ? "Six safe legs" : /^Long shot/.test(pr.name) ? "Long shot" : pr.name === "Same-game 3" ? "One game" : "Also tonight"}</p><h2>${h(pr.name)}</h2></div>
    <div class="tw-big"><b class="num">${fx(pr.min_odds, 2)}+</b><span>place at these odds or better</span>${pr.winamax_est ? `<span class="small sub">Winamax usually pays about ${fx(pr.winamax_est, 2)}</span>` : ""}</div></div>`;
  const body = `${dots(tkP(pr))}${tkBox(pr, i)}<ul class="tw-legs">${pr.legs.map(twLeg).join("")}</ul>
    ${pr.story ? `<p class="tw-story">${h(pr.story)}</p>` : ""}
    <div class="tw-acts"><button type="button" class="pill-btn" data-copy="${h(ticketText(pr))}">Copy ticket</button><a class="pill-btn" href="#/parlay">Ticket details</a></div>`;
  const warn = pr.legs.some(l => l.alert) ? ` <span class="chip warn">⚠ late news</span>` : "";
  if (main) return `<article class="tw-card main">${head}${body}</article>`;
  return `<details class="tw-card"><summary>${head.replace("</h2>", `${warn}</h2>`)}<span class="tw-mini num">${Math.round(tkP(pr) * 100)} in 100 · ${pr.n_legs} legs</span></summary>${body}</details>`;
}

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
    const hit = t.parlays.flatMap(pr => pr.legs.filter(l => l.alert).map(l => ({ pr: pr.name, l })));
    const seenA = new Set(), hitU = hit.filter(x => !seenA.has(x.l.id) && seenA.add(x.l.id));
    if (hitU.length) tickets += `<section class="late-banner" role="alert"><p class="eyebrow">Late news since the lock</p>
      <ul>${hitU.map(x => `<li><b>${h(legDesc(x.l))}</b> (${h(t.parlays.filter(pr => pr.legs.some(l => l.id === x.l.id)).map(pr => pr.name).join(", "))}): ${h(x.l.alert)}${x.l.swap ? `<br><span class="swapline">Suggested swap: <b>${h(x.l.swap.desc)}</b> · ${h(x.l.swap.matchup || "")} · ${pct(x.l.swap.p)}</span>` : ""}</li>`).join("")}</ul></section>`;
    let gt = "";
    if (t.game_tickets && t.game_tickets.length) gt = `<section class="tn-sec"><div class="hd"><div><h2>One ticket per game</h2><p class="sub2">Each game's five legs most likely to land together, from 20,000 simulations of the game. A combined bet: the book keeps a bigger cut, so it loses on average.</p></div><a class="pill-btn" href="#/parlay">All picks</a></div><div class="slips">${t.game_tickets.map(gameTicket).join("")}</div></section>`;
    tickets += gt + recStrip(par);
    if (t.singles && t.singles.length) tickets += `<section class="tn-sec"><div class="hd"><div><h2>Tonight's singles</h2><p class="sub2">Each bet on its own. Take one only at the "take ≥" odds or better.</p></div><a class="pill-btn" href="#/parlay">All picks</a></div><div class="ticket"><ul class="legs">${t.singles.map(legRow).join("")}</ul></div></section>`;
    tickets += BANNER;
    tickets += `<details class="tn-sec"><summary><b>Parlays</b> <span class="sub">set aside (they lose more on average)</span></summary><section class="tw" aria-label="Tonight's tickets">${t.parlays.map((pr, i) => twCard(pr, i, i === 0)).join("")}</section></details>`;
  } else if (t && t.locked === false) {
    tickets = `<section class="tk-row"><div class="tk-wait"><p class="eyebrow">Tonight's singles</p><h2>Chosen once, then locked</h2><p class="clock num" id="lockclock">${tipTime(t.lock_at)}</p><p class="lockin num" data-at="${h(t.lock_at)}"></p>
      <p class="sub2" style="color:var(--muted);max-width:620px;margin-top:16px">Three hours before the first tip-off, once the main injury reports are in, the full model picks one ticket per game and the night's singles, and explains each one in plain words. They never change after that.</p></div></section>` + recStrip(par);
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
      <span class="chip ${anyVal ? "ok" : "warn"}">${anyVal ? `${val.filter(v => v.value).length} with value` : "No value right now"}</span></div>${anyVal ? "" : `<p class="sub2">Winamax pays less than Pinnacle's fair price on every winner right now. Prices move during the day.</p>`}
      ${anyVal ? "" : `<details class="vb-fold"><summary>Show tonight's prices</summary>`}
      <div class="vb"><div class="vb-in"><div class="vb-row head"><span>Winner</span><span class="r">Winamax</span><span class="r">Pinnacle fair</span><span>Edge</span><span class="r">Our model</span><span class="r">Boosted odds</span></div>
      ${val.slice(0, 6).map(vrow).join("")}<div id="vbrest" hidden>${val.slice(6).map(vrow).join("")}</div></div>
      ${val.length > 6 ? `<button type="button" class="vb-more" id="vbmore">Show all ${val.length} winners</button>` : ""}</div>${anyVal ? "" : "</details>"}</section>` : "";

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
  tickClocks();
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
  app.innerHTML = `<section class="hero court"><div class="wrap"><h1>Standings</h1><p class="sub" style="margin-top:8px">${h(st.season)} regular season, with playoff chances from 4,000 simulations of the rest of the schedule.</p></div></section>
  <div class="wrap">${demoBanner()}${["East", "West"].map(cf => `<section class="section" style="margin-top:0;margin-bottom:34px"><h2>${cf}ern Conference</h2>${standingsTable(st[cf])}</section>`).join("")}
  <div class="legend"><span><i style="background:var(--pos)"></i>Playoff spots (1-6)</span><span><i style="background:var(--body)"></i>Play-in (7-10)</span></div>
  <p class="note small">Net: points better than an average team per game. Conf.: last five games against what the ratings expected.</p></div>`;
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
  app.innerHTML = `<section class="thero" style="--tc:${col}"><div class="wrap">${disc(t.abbr, "lg")}
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
  <div class="wrap">${demoBanner()}${scored}
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
    ${gameBuilder(g)}
    <section class="section"><h2>How the number was built <span class="sub">points on the margin</span></h2><div class="panel">${buildRows(g)}
      <p class="sub small" style="margin-top:12px">Win chance with the psychological layer: <b>${pct(Math.max(e.win_home, 1 - e.win_home))}</b> ${h(T(e.win_home >= 0.5 ? H : A).abbr)} · without it: <b>${pct(e.win_home_nomind >= 0.5 ? e.win_home_nomind : 1 - e.win_home_nomind)}</b> ${h(T(e.win_home_nomind >= 0.5 ? H : A).abbr)} · plain averages: <b>${pct(Math.max(e.baseline.win_home, 1 - e.baseline.win_home))}</b> ${h(T(e.baseline.win_home >= 0.5 ? H : A).abbr)}</p></div></section>
    <section class="section"><h2 class="mind">The mental game <span class="sub">each team's psychological spots, sized by what they have been worth in past games</span></h2>
      <div class="panel mind grid2">${mindCol("away", A)}${mindCol("home", H)}</div></section>
    <section class="section"><h2 class="body">Body: rest, travel, availability</h2>${news}<div class="panel body grid2">${bodyCol("away", A)}${bodyCol("home", H)}</div></section>
    ${matchupSection(g)}
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

function matchupSection(g) {
  const M = g.matchup;
  if (!M || !(M.slots || []).length) return "";
  const H = g.home.abbr, A = g.away.abbr;
  const v = (x, d = 1) => x === null || x === undefined ? "–" : fx(x, d);
  const p3 = x => x ? `${Math.round(x * 100)}%` : "–";
  const body = (pl) => {
    const s = pl.per36 || {};
    return `<div class="mu-p"><p class="mu-n">${plink(pl.id, pl.name)} <span class="sub">${h(pl.pos || "")}</span></p>
      <p class="mu-phys small">${[pl.height, pl.weight_lb ? `${Math.round(pl.weight_lb)} lb` : "", pl.age ? `${pl.age} yrs` : "", pl.exp !== null && pl.exp !== undefined ? `${pl.exp} seasons` : ""].filter(Boolean).map(h).join(" · ") || '<span class="sub">size not in yet</span>'}</p>
      <p class="mu-load small">Last 7 days: <b>${v(pl.min7, 0)}</b> min in ${v(pl.g7, 0)} games${pl.rest_days === 0 ? ' · <span class="chip warn">played yesterday</span>' : pl.rest_days !== null && pl.rest_days !== undefined ? ` · ${pl.rest_days} days rest` : ""}</p>
      <table class="mu-t"><tr><td>PTS</td><td>REB</td><td>AST</td><td>3P%</td><td>TS%</td><td>TOV</td><td>STL+BLK</td></tr>
        <tr><td class="num">${v(s.pts)}</td><td class="num">${v(s.reb)}</td><td class="num">${v(s.ast)}</td><td class="num">${p3(pl.p3)}</td><td class="num">${p3(pl.ts)}</td><td class="num">${v(s.tov)}</td><td class="num">${v(pl.stocks36)}</td></tr></table></div>`;
  };
  const tm = (t, ab) => t ? `${disc(ab, "xs")} ${h(T(ab).short)}: ${[t.height ? `avg ${t.height}` : "", t.weight_lb ? `${Math.round(t.weight_lb)} lb` : "", t.age ? `${fx(t.age, 1)} yrs` : "", `${fx(t.min7, 0)} min last 7 days`, t.p3 ? `3P ${p3(t.p3)}` : ""].filter(Boolean).map(h).join(" · ")}` : "";
  return `<section class="section reveal"><h2>Player matchups <span class="sub">likely starters paired by role: size, age, workload and skills</span></h2>
    <div class="panel">
      <p class="small">${tm(M.teams.away, A)}<br>${tm(M.teams.home, H)}</p>
      ${M.slots.map(sl => `<div class="mu-row"><div>${body(sl.away)}</div><div class="mu-vs">vs</div><div>${body(sl.home)}</div>
        ${(sl.edges || []).length ? `<ul class="mu-e small">${sl.edges.map(e => `<li>${h(e)}</li>`).join("")}</ul>` : ""}</div>`).join("")}
      <p class="sub small">Per 36 minutes, this season. TS%: points per shot attempt, free throws included. Size and age from ESPN rosters. Pairing is by role (guards, forwards, centers), not a promise of who guards whom.</p>
    </div></section>`;
}

function playersSection(g) {
  const H = g.home.abbr, A = g.away.abbr;
  if (g.players) {
    const tbl = (side, ab) => {
      const rows = g.players[side] || [];
      if (!rows.length) return `<p class="sub">No rotation data yet.</p>`;
      const pp = p => p.p_play == null ? 1 : p.p_play;
      const ord = [...rows.filter(p => !p.out && pp(p) >= 0.5), ...rows.filter(p => !p.out && pp(p) < 0.5), ...rows.filter(p => p.out)];
      const ex = k => rows.filter(p => !p.out).reduce((t, p) => t + (p[k] || 0) * pp(p), 0);
      return `<div class="tscroll"><table class="ptable"><tr><th>${disc(ab, "xs")} ${h(T(ab).short)}</th><th class="n">MIN</th><th class="n">PTS</th><th class="n">REB</th><th class="n">AST</th><th class="n">3PM</th><th class="n">STL</th><th class="n">BLK</th><th class="n">PRA</th></tr>
        ${ord.map((p, i) => p.out ? `<tr class="out"><td class="nm">${plink(p.id, p.name)}<span class="ptag out">${h(p.status || "Out")}</span></td><td class="n" colspan="8">${h(p.detail || "")}</td></tr>`
          : `<tr${pp(p) < 0.5 ? ' class="unlikely"' : ""}><td class="nm">${plink(p.id, p.name)}<span class="sub">${h(p.pos || "")}</span>${pp(p) < 0.95 ? `<span class="ptag q">plays ${pct(pp(p))}</span>` : ""}${newsTag(p.news)}${p.status ? `<span class="ptag q">${h(p.status)}</span>` : ""}${p.lineup ? `<span class="ptag${p.lineup === "starting" ? "" : " q"}">${p.lineup === "starting" ? "Starting" : "Not starting"}</span>` : ""}${p.sit ? `<span class="ptag" title="Before any news: how often a key player in this spot sits (measured). Used in the team-strength estimate until the injury report is in.">Sits ${Math.round(p.sit * 100)}% in this spot</span>` : ""}${(p.spots || []).filter(x => ["former_team", "returning", "contract_year", "without", "vs_opp"].includes(x.key) || (x.key === "hot")).map(x => `<span class="ptag" title="${h(x.text)}">${h(x.label)}</span>`).join("")}</td>
            <td class="n">${fx(p.min, 0)}</td><td class="n hl">${fx(p.pts)}</td><td class="n">${fx(p.reb)}</td><td class="n">${fx(p.ast)}</td><td class="n">${fx(p.tpm)}</td><td class="n">${fx(p.stl)}</td><td class="n">${fx(p.blk)}</td><td class="n">${fx(p.pra)}</td></tr>`).join("")}
        <tr class="ttot"><td class="nm">Team, expected<span class="sub">weighted by chance of playing</span></td><td class="n">${fx(ex("min"), 0)}</td><td class="n hl">${fx(ex("pts"))}</td><td class="n">${fx(ex("reb"))}</td><td class="n">${fx(ex("ast"))}</td><td class="n">${fx(ex("tpm"))}</td><td class="n">${fx(ex("stl"))}</td><td class="n">${fx(ex("blk"))}</td><td class="n">${fx(ex("pra"))}</td></tr></table></div>
        <details class="more"><summary>Over/under chances for every player</summary>${rows.filter(p => !p.out && p.lines).map(p => `<h3 style="margin-top:12px">${h(p.name)}</h3>${linesBlock(p.lines)}`).join("")}</details>`;
    };
    return `<section class="section"><h2>Player projections <span class="sub">each line assumes the player plays · ${g.kind === "estimate" ? "updated until tip-off" : "as frozen"}</span></h2><div class="grid2"><div>${tbl("away", A)}</div><div>${tbl("home", H)}</div></div></section>`;
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

/* our player projections against Pinnacle's closing player lines, scored every night (pipeline/vsmarket.py) */
function vsMarketHtml(v) {
  if (!v || !v.n) return "";
  const wr = v.lean ? v.lean_wins / v.lean : 0, prog = Math.min(1, v.games / v.target_games), good = wr > v.break_even && v.games >= v.target_games;
  const name = { pts: "Points", reb: "Rebounds", ast: "Assists", tpm: "Threes", pra: "Pts+reb+ast" };
  return `<section class="section" id="vs-market"><h2>Player projections vs Pinnacle <span class="sub">the sharpest bookmaker, scored every night</span></h2>
    <div class="rs-sum">
      <div class="tile"><p class="k">Average miss on the stat</p><p class="v num">${fx(v.mae_ours, 2)} <span class="sub" style="font-size:16px">vs ${fx(v.mae_line, 2)}</span></p><p class="sub small">ours vs Pinnacle's line, lower is better</p></div>
      <div class="tile"><p class="k">When we disagree with the line</p><p class="v num ${good ? "up" : ""}">${pct(wr)}</p><p class="sub small">our side won ${v.lean_wins} of ${v.lean}; about ${pct(v.break_even)} breaks even</p></div>
      <div class="tile"><p class="k">Evidence so far</p><p class="v num">${v.games} <span class="sub" style="font-size:16px">of ${v.target_games} games</span></p><span class="vm-bar"><span style="width:${Math.round(prog * 100)}%"></span></span><p class="sub small">since ${h(longDay(v.since))}</p></div>
    </div>
    <div class="tscroll"><table><tr><th>Stat</th><th class="n">Lines</th><th class="n">Our miss</th><th class="n">Pinnacle's miss</th><th class="n">Our side won</th></tr>
      ${Object.entries(v.by_stat).map(([k, r]) => `<tr><td>${name[k] || h(k)}</td><td class="n">${r.n}</td><td class="n ${r.mae_ours < r.mae_line ? "up" : ""}">${fx(r.mae_ours, 2)}</td><td class="n">${fx(r.mae_line, 2)}</td><td class="n">${r.lean ? pct(r.lean_wins / r.lean) : "–"}</td></tr>`).join("")}</table></div>
    <p class="note small">Our projections are frozen at tip-off and compared with Pinnacle's last player line before the game. Players in the same game rise and fall together, so until about ${v.target_games} games the win rate is mostly noise: read the trend, not the number. Pinnacle is the benchmark here, not where you bet; Winamax lines and prices are usually worse.</p></section>`;
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
  app.innerHTML = `<div class="wrap tn" style="padding-bottom:0"><section class="tn-hero" style="padding-bottom:28px"><div class="lead"><p class="eyebrow">Frozen at tip-off · scored after the buzzer</p><h1>Track record</h1><nav class="daytabs seg" aria-label="Whose record"><a href="#/accuracy" aria-current="page">The model</a><a href="#/you" aria-current="false">Your bets</a></nav>
    <p class="sublede">Every estimate is locked before the game and checked afterwards, against simpler methods, including the same model without its psychological layer.</p></div></section>
    <section class="rec-tiles">
      <div class="tile big"><p class="k">Live record · winners called</p>${a.live && a.live.n ? `<p class="v num">${Math.round(a.live.hit * a.live.n)}/${a.live.n}</p><p class="s">${pct(a.live.hit)} · frozen estimates only</p>` : `<p class="v" style="font-size:30px;line-height:1.15">Starts tonight</p><p class="s">The first frozen estimates are scored after tonight's games.</p>`}</div>
      <div class="tile"><p class="k">This season (research)</p><p class="v num">${a.checks ? pct(a.checks.hit) : "–"}</p><p class="s">${a.checks ? `winners in ${a.checks.n} games` : ""}</p></div>
      <div class="tile"><p class="k">Calibration</p><p class="v num">${a.checks && a.checks.calibration ? (() => { const c = a.checks.calibration.filter(x => x.n >= 10); const p_ = c.reduce((s_, x) => s_ + x.p * x.n, 0), h_ = c.reduce((s_, x) => s_ + x.hit * x.n, 0), n_ = c.reduce((s_, x) => s_ + x.n, 0); return n_ ? `${pct(p_ / n_)} → ${pct(h_ / n_)}` : "–"; })() : "–"}</p><p class="s">favourites' stated chance → how often they won</p></div>
      <div class="tile"><p class="k">Player points miss</p><p class="v num">${a.players && a.players.track ? fx(a.players.track.mae_pts, 2) : "–"}</p><p class="s">${a.players && a.players.track ? `vs ${fx(a.players.track.mae_pts_base, 2)} for season averages` : ""}</p></div>
    </section></div>
  <div class="wrap">${demoBanner()}
    ${a.live ? block("Live record: the number that counts", liveO, a.live.n, `Estimates frozen at tip-off with only what was known before the game, never changed afterwards.${a.live.n < 150 ? ` With only ${a.live.n} games, luck dominates: any method, even plain averages, can look better or worse than it really is. Judge it after a few hundred games.` : ""}`, a.live.calibration) : `<section><h2>Live record: the number that counts</h2><p class="note">No frozen estimates have been scored yet. The record starts with the first games after the site went live (9 November 2026); nothing is ever added afterwards. Everything below is research: made after the fact and, for the player-based checks, knowing who actually played, so it runs a little better than live estimates can.</p></section>`}
    ${verdict}
    ${vsMarketHtml(a.vs_market)}
    <section class="section"><details class="howto"><summary>Research details: how each part of the model is tested</summary>
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
    </details></section>
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
  const [a, rp] = await Promise.all([get("accuracy.json"), get("replay.json").catch(() => null)]);
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
    <p><b>Tickets</b>: every winner, handicap, total and player leg is checked; each game is simulated 20,000 times so legs from the same game are priced together; the Value 2 (main pick), Core 3, the daily 6 and three long shots are chosen once, three hours before the first tip-off. A leg only goes into a ticket when the projection, the season average and the last 5 games all agree it is likely, and no bet appears in two tickets. A leg's chance then weighs the three as past results say: the projection counts most, heavy-minute players land more often, and lines of 2 or more threes land less often than the raw count says.</p>
    <p><b>Singles</b> (the main picks since November 2026): every winner, handicap, total and agreed player leg is valued at the odds Winamax is expected to pay: its real odds for winners; for handicaps and totals Pinnacle's fair odds times Winamax's measured discount (it pays 0.81 to 0.93 of the fair odds, less the longer the shot); for player legs a Winamax chance halfway between ours and the one from the player's season average. The five best positive values are listed. No real Winamax price for a player bet has ever been in our feed, so player bets are never listed as value: a single needs a price actually seen at the book. Take a single only at the \"take ≥\" odds or better.</p>
    <p><b>Quarters, playoff chances, mind ranking</b>: the estimate split by each team's usual share per quarter; the rest of the season simulated 4,000 times with the play-in; and a description of each team's state next to its measured psychological edge.</p>
  </div></details>
  ${testedHtml(rp)}
  </div>`;
}
/* what was tried: kept and rejected ideas, with the replay result that decided each */
function testedHtml(r) {
  if (!r || !r.rejected) return "";
  const row = (cls, [what, why]) => `<li class="${cls}"><b>${h(what)}</b><span>${h(why)}</span></li>`;
  return `<section class="tn-sec tested" aria-labelledby="tested-h"><h2 id="tested-h">What was tried, and what was kept</h2>
    <p class="sub">An idea goes live only when the replay of past seasons lands more tickets at the same chances. Most don't. The full list, as of ${h(day(r.updated))}:</p>
    <ul class="tested-l">${(r.kept || []).map(x => row("kept", x)).join("")}${r.rejected.map(x => row("rej", x)).join("")}</ul>
    ${r.market ? `<p class="note small">Against the betting market (${h(r.market.source)}: ${r.market.n.toLocaleString("en-GB")} lines, ${h(r.market.period)}): model ${fx(r.market.logloss_model, 4)}, market ${fx(r.market.logloss_market, 4)}, the blend the site uses ${fx(r.market.logloss_live_blend, 4)} (log loss, lower is better). The market knows things the model doesn't and the other way round: where they disagreed by 10 points or more, the model's side won ${pct(r.market.disagree_won)} of ${r.market.disagree_n.toLocaleString("en-GB")} lines.</p>` : ""}
  </section>`;
}
