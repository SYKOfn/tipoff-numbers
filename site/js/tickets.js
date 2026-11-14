/* Tip-Off Numbers: Tickets: the daily game tickets, your bets, the public record, live legs, the Tickets page sections.
   Plain scripts loaded in order (index.html); they share one global scope, no build step. */
"use strict";

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
  if (l.kind === "prop") return l.side === "over" && Number.isFinite(+L) ? `${l.player_name} ${Math.ceil(+L)}+ ${STATN[l.stat] || l.stat}` : `${l.player_name} ${l.side} ${fx(L)} ${STATN[l.stat] || l.stat}`;
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
  if (t) [...(t.parlays || []).flatMap(p => p.legs), ...(t.game_tickets || []).flatMap(p => p.legs), ...(t.board || []), ...(t.singles || [])].forEach(l => { m[l.id] = l; });
  return m;
}
function legRow(l, i) {
  const res = l.result ? ` ${l.result}` : "";
  const bookName = b => ({ winamax_fr: "Winamax", pinnacle: "Pinnacle" }[b] || b);
  const mkt = l.price && !l.price_est ? `${bookName(l.book || "market")} ${fx(l.price, 2)}${l.edge != null ? ` (${sgn(l.edge * 100, 0)}% value)` : ""}` : (l.price_est ? `check line ${fx(l.line)}` : "no market price");
  const clv = l.clv ? ` · CLV ${l.clv.p != null ? sgn(l.clv.p * 100, 1) + " pts of chance" : sgn(l.clv.pts) + " pts of line"}` : "";
  return `<li class="${res.trim()}"><span class="no">${i + 1}</span>
    <span class="d"><span class="kind ${l.kind}">${KIND[l.kind] || l.kind}</span><b data-d="${l.id}">${h(legDesc(l))}</b><span class="mflag ${l.mind_flag}">${l.mind_flag === "with" ? "mind with it" : l.mind_flag === "against" ? "mind against" : "mind neutral"}</span>
    <span class="sub"><a href="#/game/${h(l.game)}">${h(T(matchTeams(l)[0]).short)} at ${h(T(matchTeams(l)[1]).short)}</a> · ${tip(l.tip)}<span class="tech"> · ${h(l.note || "")} · market: ${h(mkt)}${clv}</span>${l.result ? ` · <b class="${l.result === "hit" ? "up" : l.result === "miss" ? "down" : ""}">${l.result}</b>` : ""}${l.story ? `<br><span class="story">${h(l.story)}</span>` : ""}${l.alert ? `<br><b class="down">⚠ ${h(l.alert)}</b>` : ""}${l.swap ? `<br>Suggested swap: <b>${h(l.swap.desc)}</b> (${h(l.swap.matchup || "")}, ${pct(l.swap.p)})` : ""}</span></span>
    <span class="cwrap">${l.wmx ? `<span class="c"><b>${fx(l.wmx, 2)}</b><span>Winamax ${l.wmx_real ? "odds" : "expected"} · value ${sgn(l.ev * 100, 0)}%</span></span>` : ""}<span class="c"><b data-p="${l.id}">${pct(effP(l))}</b><span>chance</span></span><span class="c"><b data-f="${l.id}">${fx(1 / effP(l), 2)}</b><span data-m="${l.id}">fair · take ≥ ${fx(1.05 / effP(l), 2)}</span></span></span>${oddsCell(l)}</li>`;
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
function untilText(iso) {
  const ms = new Date(iso) - Date.now();
  if (!(ms > 0)) return "any minute now";
  const m = Math.round(ms / 60000), hh = Math.floor(m / 60);
  return `in ${hh ? `${hh} h ` : ""}${m % 60} min`;
}
function tickClocks() { document.querySelectorAll(".lockin[data-at]").forEach(x => { x.textContent = untilText(x.dataset.at); }); }
setInterval(tickClocks, 30000);
document.addEventListener("input", e => {
  const tk = e.target.closest && e.target.closest(".tkodds[data-tk]");
  if (!tk || !(PAR && PAR.today && PAR.today.parlays)) return;
  const pr = tkOf(PAR.today, tk.dataset.tk), v = parseFloat(tk.value);
  LS.set(tkKey(pr), v > 1 ? v : null);
  document.querySelectorAll(`[data-tkv="${tk.dataset.tk}"]`).forEach(el => { el.innerHTML = tkVerdict(pr); });
});
const tkKey = pr => `tipoff.tk.${(PAR && PAR.today && PAR.today.day) || ""}.${pr.name}`;
const tkP = pr => pr.p * pr.legs.reduce((a, l) => a * effP(l) / l.p, 1);
function tkVerdict(pr) {
  const o = LS.get(tkKey(pr), null), p = tkP(pr), worth = 1.05 / p;
  if (!o) return `<span class="tk-hint">Type the combined odds Winamax shows for this ticket. It's worth placing at <b>${fx(worth, 2)}</b> or more.</span>`;
  const ev = p * o - 1;
  if (o >= worth) return `<span class="tk-v up"><b>Place</b> Winamax pays ${fx(o, 2)}, at or above the ${fx(worth, 2)} needed (fair ${fx(1 / p, 2)} plus a 5% safety margin): about ${sgn(ev * 100, 0)}% in your favour.</span>`;
  if (ev >= 0) return `<span class="tk-v flat"><b>Borderline</b> Winamax pays ${fx(o, 2)}: above the fair ${fx(1 / p, 2)} but below the ${fx(worth, 2)} with the safety margin. Too thin an edge to rely on.</span>`;
  return `<span class="tk-v down"><b>Skip</b> Winamax pays ${fx(o, 2)}, less than the ${fx(1 / p, 2)} this ticket is worth: the bookmaker's margin takes ${Math.round(-ev * 100)}% of your stake on average. Look for better odds or skip it.</span>`;
}
function tkBox(pr, idx) {
  if (pr.result) return "";
  const o = LS.get(tkKey(pr), null);
  return `<div class="tkbox"><label>Winamax combined odds <input class="tkodds" type="number" inputmode="decimal" step="0.01" min="1.01" placeholder="e.g. ${fx(1.1 / tkP(pr), 2)}" value="${o ?? ""}" data-tk="${idx}"></label><div class="tkv" data-tkv="${idx}">${tkVerdict(pr)}</div></div>`;
}
function ticketText(pr) {
  return `${pr.name} — Tip-Off Numbers\n` + (pr.story ? `${pr.story}\n` : "") + pr.legs.map((l, i) => `${i + 1}. ${legDesc(l)} (${T(matchTeams(l)[0]).abbr} @ ${T(matchTeams(l)[1]).abbr}) — ${pct(l.p)}, take at ${fx(l.min_odds, 2)}+${l.story ? `\n   ${l.story}` : ""}`).join("\n")
    + `\nAll legs: ${pct(pr.p)} · fair combined odds ${fx(pr.fair, 2)} · worth it at ${fx(pr.min_odds, 2)}+${pr.winamax_est ? ` · Winamax usually about ${fx(pr.winamax_est, 2)}` : ""}`;
}
const tkOf = (t, k) => t && (String(k)[0] === "g" ? (t.game_tickets || [])[+String(k).slice(1)] : (t.parlays || [])[+k]);
/* a chance as a ring: the arc fills to the chance */
function ring(p, size = 40, cls = "") {
  const r = size / 2 - 3, c = 2 * Math.PI * r, v = Math.max(0, Math.min(1, p || 0));
  return `<svg class="ring ${cls}" viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" aria-hidden="true"><circle cx="${size / 2}" cy="${size / 2}" r="${r}" class="ring-bg"/><circle cx="${size / 2}" cy="${size / 2}" r="${r}" class="ring-fg" stroke-dasharray="${(v * c).toFixed(1)} ${c.toFixed(1)}" transform="rotate(-90 ${size / 2} ${size / 2})"/></svg>`;
}
/* one leg of a game ticket: a single tight line, the details open on tap */
function slipLeg(l, i) {
  const p = effP(l), mark = l.result === "hit" ? `<span class="sl-res up" aria-label="landed">✓</span>` : l.result === "miss" ? `<span class="sl-res down" aria-label="missed">✗</span>` : "";
  const odds = l.wmx ? `<b>${fx(l.wmx, 2)}</b><span>${l.wmx_real ? "Winamax" : "Winamax est."}</span>` : `<b data-f="${l.id}">${fx(1 / p, 2)}</b><span>fair</span>`;
  const team = l.team ? T(l.team).short : "";
  const mind = l.mind_flag === "with" ? `<span class="sl-tag with">mind with it</span>` : l.mind_flag === "against" ? `<span class="sl-tag against">mind against</span>` : "";
  return `<li class="sl ${l.result || ""}" data-lid="${l.id}" style="--i:${i}"><details><summary>
      <span class="sl-p">${ring(p, 42)}<b data-p="${l.id}">${pct(p)}</b></span>
      <span class="sl-d"><b data-d="${l.id}">${h(legDesc(l))}</b><span class="sl-m">${KIND[l.kind] || l.kind}${team ? ` · ${h(team)}` : ""}${mind}</span><span class="sl-live" data-live="${l.id}" hidden></span></span>
      <span class="sl-o">${odds}</span>${mark}<span class="sl-chev" aria-hidden="true"></span></summary>
    <div class="sl-x">
      <dl class="sl-nums"><div><dt>Chance</dt><dd data-p="${l.id}">${pct(p)}</dd></div><div><dt>Fair odds</dt><dd data-f="${l.id}">${fx(1 / p, 2)}</dd></div><div><dt>Take at</dt><dd data-m="${l.id}">fair · take ≥ ${fx(1.05 / p, 2)}</dd></div>${l.wmx ? `<div><dt>Value at Winamax</dt><dd class="${l.ev >= 0 ? "up" : "down"}">${sgn(l.ev * 100, 0)}%</dd></div>` : ""}</dl>
      ${l.note ? `<p class="sl-note">${h(l.note)}</p>` : ""}${l.story ? `<p class="story">${h(l.story)}</p>` : ""}${l.alert ? `<p class="down"><b>⚠ ${h(l.alert)}</b></p>` : ""}
      <p class="sl-game"><a href="#/game/${h(l.game)}">${h(T(matchTeams(l)[0]).short)} at ${h(T(matchTeams(l)[1]).short)}</a> · ${tip(l.tip)}</p>
      ${oddsCell(l)}
    </div></details></li>`;
}
function gameTicket(pr, i) {
  const sc = pr.scenarios || {}, lab = { close: "Close game (6 pts or less)", normal: "Normal margin", blowout: "Blowout (15+)", home_wins: "Home team wins", away_wins: "Away team wins", overtime: "Overtime" };
  const rows = Object.entries(lab).filter(([k]) => sc[k]).map(([k, t]) => `<li><span>${t}</span><span class="bar"><span style="width:${Math.round(sc[k].lands * 100)}%"></span></span><b>${pct(sc[k].lands)}</b><span class="sub">${pct(sc[k].share)} of games</span></li>`).join("");
  const [aw, hm] = String(pr.name || "").split(" at ");
  const tipAt = pr.legs[0] && pr.legs[0].tip;
  const res = pr.result ? `<span class="slip-stamp ${pr.result === "hit" ? "up" : "down"}">${pr.result === "hit" ? "Landed" : "Missed"}</span>` : "";
  const today = PAR && PAR.today, draft = today && today.locked === false && today.game_tickets && today.game_tickets.includes(pr);
  const draftTag = draft ? `<span class="slip-draft">Draft · final at ${tipTime(today.lock_at)}</span>` : "";
  return `<article class="slip" data-tilt${pr.result ? "" : ` data-game="${h(pr.game)}" data-tip="${h(tipAt || "")}"`}>
    <header class="slip-head">
      <div class="slip-teams">${aw && hm ? `${disc(aw, "sm")}<span class="slip-at">at</span>${disc(hm, "sm")}` : ""}<div><h3>${aw && hm ? `${h(T(aw).short)} <i>at</i> ${h(T(hm).short)}` : h(pr.name)}</h3><p>${tipAt ? tip(tipAt) + " · " : ""}${pr.n_legs} legs<span class="long">, priced together on 20,000 simulated games</span></p></div></div>
      ${draftTag}<span class="slip-live" role="status" aria-live="polite" hidden></span><div class="slip-chance">${ring(tkP(pr), 74, "big")}<div><b>${pct(tkP(pr))}</b><span>chance</span></div></div>${res}
    </header>
    <div class="perf" aria-hidden="true"></div>
    <ol class="slip-legs">${pr.legs.map(slipLeg).join("")}</ol>
    ${rows ? `<details class="slip-sc"><summary>How it lands in each kind of game</summary><ul>${rows}</ul></details>` : ""}
    <div class="perf" aria-hidden="true"></div>
    <footer class="slip-foot">
      <div class="slip-figs"><div><span>Fair odds</span><b>${fx(pr.fair, 2)}</b></div><div class="go"><span>Place at</span><b>${fx(pr.min_odds, 2)}+</b></div>${pr.winamax_est ? `<div><span>Winamax usually</span><b>≈ ${fx(pr.winamax_est, 2)}</b></div>` : ""}</div>
    </footer>
    ${draft ? `<div class="slip-bar slip-wait"><p>This ticket can still change until ${tipTime(today.lock_at)}, when the model picks the final legs with the latest injury news. Record and share it once it's locked.</p></div>` : `<div class="slip-bar"><span class="slip-bar-name">${aw && hm ? `${h(T(aw).short)} at ${h(T(hm).short)}` : h(pr.name)}</span>${tkBox(pr, "g" + i)}
      <div class="slip-acts"><button class="copybtn" data-copy="${h(ticketText(pr))}">Copy</button>${PAR && PAR.today && PAR.today.day && pr.game ? `<button class="copybtn" data-share="t/${h(PAR.today.day)}-${h(pr.game)}.html" data-title="${h(pr.name)}">Share</button>` : ""}<button class="copybtn primary" data-record="g${i}">Record as my bet</button></div></div>`}
  </article>`;
}
function ticket(pr, main, idx) {
  return `<div class="ticket ${main ? "main" : ""}"><div class="ticket-head"><div><h3>${h(pr.name)}${pr.result ? ` <span class="cat ${pr.result === "hit" ? "Hot" : "Cold"}">${pr.result}</span>` : ""}</h3><p>${h(pr.why || "")}</p>${pr.story ? `<p class="story"><b>Why this ticket:</b> ${h(pr.story)}</p>` : ""}</div>
    <span><button class="copybtn" data-copy="${h(ticketText(pr))}">Copy ticket</button> <button class="copybtn" data-record="${idx}">Record as my bet</button></span></div>
    <div class="tk-dots">${dots(tkP(pr))}</div>${tkBox(pr, idx)}
    <ul class="legs">${pr.legs.map(legRow).join("")}</ul>
    <p class="techsw"><button type="button" class="linkbtn" data-tech>Show the numbers behind it</button></p>
    <div class="ticket-foot"><div><b>${pct(pr.p)}</b>chance all ${pr.n_legs} land</div><div><b>${fx(pr.fair, 2)}</b>fair combined odds</div>
      <div class="go"><b>${fx(pr.min_odds, 2)}+</b>worth placing at these combined odds or better</div>
      <div><b>${pr.lift >= 1 ? "+" : ""}${Math.round((pr.lift - 1) * 100)}%</b>correlation lift</div>
      ${pr.games < pr.n_legs && Math.abs(pr.lift - 1) >= 0.03 ? `<p class="lift-note">${pr.lift > 1 ? "In the game simulations these legs land together more often than chance would say" : "In the game simulations these legs tend to pull against each other, so landing all of them is a little less likely than the single chances suggest"}.</p>` : ""}
      <div class="you" data-tv="${idx}">${ticketValue(pr.legs, pr.p)}</div></div></div>`;
}

/* my bets (kept in this browser) */
const BETS_KEY = "tipoff.bets";
function recordBet(name, legs, p, combined) {
  const odds = legs.map(l => oddsOf(l.id));
  const stake = parseFloat((document.getElementById("stake") || {}).value) || null;
  const bets = LS.get(BETS_KEY, []);
  bets.unshift({ at: new Date().toISOString(), name, p, stake, odds: combined || (odds.every(Boolean) ? odds.reduce((a, b) => a * b, 1) : null),
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


/* ---------------------------------------------------------------- your bets (kept on this phone only) */
async function yourBets() {
  const par = await get("parlay.json").catch(() => ({}));
  PAR = par;
  setTitle("Your bets");
  const res = par.leg_results || {};
  const bets = LS.get(BETS_KEY, []).map(b => {
    const lr = b.legs.map(l => res[l.id]);
    const status = lr.some(r => r === "miss") ? "lost" : lr.length && lr.every(r => r === "hit" || r === "void") ? "won" : "open";
    return { ...b, lr, status };
  });
  const done = bets.filter(b => b.status !== "open").reverse();  // oldest first
  const won = done.filter(b => b.status === "won").length, exp = done.reduce((a, b) => a + (b.p || 0), 0);
  const priced = done.filter(b => b.odds);
  const avgVal = priced.length ? priced.reduce((a, b) => a + (b.p * b.odds - 1), 0) / priced.length : null;
  const staked = done.filter(b => b.stake && b.odds);
  const net = staked.reduce((a, b) => a + (b.status === "won" ? b.stake * (b.odds - 1) : -b.stake), 0);
  // landed against expected, bet by bet
  let cw = 0, ce = 0;
  const pts = done.map(b => { cw += b.status === "won" ? 1 : 0; ce += b.p || 0; return [cw, ce]; });
  const W = 320, Hh = 110, mx = Math.max(1, ...pts.map(x => Math.max(x[0], x[1])));
  const path = k => pts.map((x, i) => `${i ? "L" : "M"}${(pts.length < 2 ? 0 : i / (pts.length - 1)) * W},${Hh - (x[k] / mx) * Hh}`).join(" ");
  const chart = pts.length >= 2 ? `<svg class="yb-chart" viewBox="-4 -4 ${W + 8} ${Hh + 8}" role="img" aria-label="Tickets landed against expected">
      <path d="${path(1)}" fill="none" stroke="#5B5F70" stroke-width="2" stroke-dasharray="4 4"/><path d="${path(0)}" fill="none" stroke="#3DF0A5" stroke-width="2.5"/></svg>
      <p class="sub small"><span style="color:#3DF0A5">━</span> tickets landed &nbsp; <span style="color:#8b8f9c">┅</span> what the chances said</p>` : "";
  const card = (b, i) => `<article class="yb-item ${b.status}"><div class="yb-top"><span class="sub small">${day(b.at.slice(0, 10))}</span>
      <span class="chip ${b.status === "won" ? "ok" : b.status === "lost" ? "warn" : ""}">${b.status === "won" ? "Landed" : b.status === "lost" ? "Missed" : "Open"}</span></div>
    <h3>${h(b.name)}</h3>
    <ul>${b.legs.map((l, j) => `<li><span class="${b.lr[j] === "hit" ? "up" : b.lr[j] === "miss" ? "down" : "sub"}">${b.lr[j] === "hit" ? "✓" : b.lr[j] === "miss" ? "✗" : "·"}</span> ${h(l.desc)}</li>`).join("")}</ul>
    <p class="sub small">${pct(b.p)} chance${b.odds ? ` · your odds ${fx(b.odds, 2)} (fair ${fx(1 / b.p, 2)}: ${sgn((b.p * b.odds - 1) * 100, 0)}% ${b.p * b.odds >= 1 ? "in your favour" : "against you"})` : ""}${b.stake ? ` · stake ${fx(b.stake, 2)}` : ""}</p>
    <button type="button" class="linkbtn" data-ydel="${i}">Remove</button></article>`;
  app.innerHTML = `<div class="wrap tn"><section class="tn-hero" style="padding-bottom:18px"><div class="lead"><p class="eyebrow">Kept on this phone only</p><h1>Track record</h1>
      <nav class="daytabs seg" aria-label="Whose record"><a href="#/accuracy" aria-current="false">The model</a><a href="#/you" aria-current="page">Your bets</a></nav></div></section>
    ${bets.length ? `<section class="rec-tiles">
      <div class="tile big"><p class="k">Tickets landed</p><p class="v num">${won}/${done.length}</p><p class="s">the chances said about ${fx(exp, 1)}</p></div>
      <div class="tile"><p class="k">Your odds vs fair</p><p class="v num ${avgVal == null ? "" : avgVal >= 0 ? "up" : "down"}">${avgVal == null ? "–" : sgn(avgVal * 100, 0) + "%"}</p><p class="s">the real measure of skill: getting more than the fair price</p></div>
      ${staked.length ? `<div class="tile"><p class="k">Net, recorded stakes</p><p class="v num ${net >= 0 ? "up" : "down"}">${sgn(net, 2)}</p><p class="s">${staked.length} settled bets with a stake</p></div>` : ""}
      <div class="tile"><p class="k">Open</p><p class="v num">${bets.length - done.length}</p><p class="s">waiting for results</p></div></section>
      ${chart ? `<section class="tn-sec"><div class="panel">${chart}</div></section>` : ""}
      ${done.length && done.length < 30 ? `<p class="note small">${done.length} settled ticket${done.length === 1 ? "" : "s"} is far too few to judge anything: a few weeks of results start to mean something.</p>` : ""}
      <section class="tn-sec yb">${bets.map(card).join("")}</section>
      <p class="sub small yb-backup"><button type="button" class="linkbtn" id="ybexp">Download a backup</button> · <label class="linkbtn">Restore a backup<input type="file" accept="application/json" id="ybimp" hidden></label>
        <br>Your bets live in this browser only: download a backup now and then, and restore it on a new phone or after clearing the browser.</p>`
    : `<section class="tn-sec"><div class="panel"><h3>No bets recorded yet</h3><p class="sub small"><label class="linkbtn">Restore a backup<input type="file" accept="application/json" id="ybimp" hidden></label></p><p class="sub">On a ticket, type the combined odds Winamax gives you and press "Record as my bet". Your tickets, their results and the odds you got against the fair price appear here. Nothing leaves this phone.</p><p><a class="pill-btn" href="#/parlay">Tonight's tickets</a></p></div></section>`}</div>`;
  const imp = document.getElementById("ybimp");
  if (imp) imp.onchange = async () => {
    try {
      const got = JSON.parse(await imp.files[0].text());
      if (!Array.isArray(got)) throw new Error("not a bets file");
      const have = LS.get(BETS_KEY, []), seen = new Set(have.map(b => b.at + b.name));
      LS.set(BETS_KEY, [...have, ...got.filter(b => b && b.at && b.legs && !seen.has(b.at + b.name))].sort((a, b) => b.at.localeCompare(a.at)));
      yourBets();
    } catch (err) { alert("That file is not a Tip-Off bets backup."); }
  };
  app.onclick = e => {
    const d = e.target.closest("[data-ydel]");
    if (d) { const all = LS.get(BETS_KEY, []); all.splice(+d.dataset.ydel, 1); LS.set(BETS_KEY, all); yourBets(); }
    if (e.target.id === "ybexp") {
      const blob = new Blob([JSON.stringify(LS.get(BETS_KEY, []), null, 1)], { type: "application/json" });
      const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `tipoff-my-bets-${new Date().toISOString().slice(0, 10)}.json`; a.click();
    }
  };
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
  const selR = rec._selection;
  const selHtml = selR && selR.ticket_legs.n ? `<p class="sub small" style="margin-top:12px">Legs that went into tickets: <b>${selR.ticket_legs.hits}/${selR.ticket_legs.n}</b> landed (expected ${fx(selR.ticket_legs.expected, 1)}) · every other leg the model rated: <b>${selR.other_legs.hits}/${selR.other_legs.n}</b> (expected ${fx(selR.other_legs.expected, 1)}). If ticket legs keep falling short while the rest do not, the way tickets are chosen is biased.${selR.ticket_by_source ? " By source: " + [["team", "team legs"], ["prop_priced", "player legs with a real price"], ["prop_estimated", "player legs with an estimated price"]].filter(([k]) => (selR.ticket_by_source[k] || {}).n).map(([k, lab]) => `${lab} <b>${selR.ticket_by_source[k].hits}/${selR.ticket_by_source[k].n}</b> (expected ${fx(selR.ticket_by_source[k].expected, 1)})`).join(" · ") + "." : ""}</p>` : "";
  const recHtml = Object.keys(rec).filter(k => !k.startsWith("_")).length ? `<div class="grid">${Object.entries(rec).filter(([k]) => !k.startsWith("_")).map(([k, r]) => `<div class="panel"><h3>${h(k)}</h3><div class="adv"><div><b>${r.hits}/${r.n}</b>tickets landed<br>expected ${fx(r.expected, 1)}</div><div><b>${r.leg_hits}/${r.legs}</b>legs landed<br>expected ${fx(r.leg_expected, 1)}</div>${r.profit_est != null ? `<div><b>${sgn(r.profit_est, 1)}</b>units at the estimated Winamax payout<br>${sgn(r.profit_fair, 1)} at fair odds · 1 unit a ticket</div>` : ""}</div>${r.by_kind ? `<p class="small">${Object.entries(r.by_kind).map(([k, b]) => `${h(KIND[k] || k)}: ${b.hits}/${b.legs} (expected ${fx(b.expected, 1)})`).join(" · ")}</p>` : ""}</div>`).join("")}</div>`
    : `<p class="note">No slate has been scored yet. Each day's tickets are frozen at the first tip-off and scored after the last game; nothing is ever changed afterwards.</p>`;
  const clvBox = (title, c, unit) => `<div class="panel"><h3>${title}</h3>${c && c.moved ? `<div class="adv"><div><b>${c.beat}/${c.moved}</b>moved our way<br>${pct(c.beat / c.moved)}</div>${c.avg_p != null ? `<div><b>${sgn(c.avg_p * 100, 2)}</b>avg chance points</div>` : ""}${c.avg_pts != null ? `<div><b>${sgn(c.avg_pts, 2)}</b>avg line points</div>` : ""}</div>` : `<p class="sub small">${unit}</p>`}</div>`;
  const mc = clv.model || {};
  const oa = d.odds_api || {};
  const oddsNote = oa.enabled ? `Prices from ${h(String(oa.books || "").split(",").map(b => ({ winamax_fr: "Winamax", pinnacle: "Pinnacle" }[b.trim()] || b.trim())).join(" and "))}, refreshed with every update.` : `Real Winamax prices are off: add a free The Odds API key as the GitHub secret ODDS_API_KEY to switch them on. Until then market prices come from ESPN's US feed.`;
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
  const singles = t && t.singles && t.singles.length ? `<div class="ticket"><ul class="legs">${t.singles.map(legRow).join("")}</ul></div>` : t && t.locked === false ? `<p class="sub">Tonight's singles are chosen at ${tip(t.lock_at)}, with the tickets.</p>` : `<p class="sub">No single is worth taking today.</p>`;
  const lockLine = !t ? "No games on the board right now." : t.locked && t.locked_at ? `${h(longDay(t.day))} · ${t.games} game${t.games === 1 ? "" : "s"} · locked at ${tip(t.locked_at)}, they will not change`
    : `${h(longDay(t.day))} · ${t.games} game${t.games === 1 ? "" : "s"} · chosen once at ${tip(t.lock_at)}, three hours before the first tip-off`;
  app.innerHTML = `<section class="hero court"><div class="wrap"><h1>Tonight's tickets</h1>
    <p class="lede" style="margin-top:10px">${lockLine}</p></div></section>
  <div class="wrap">${demoBanner()}
    <nav class="segs" aria-label="Tickets page sections">${[["tickets", "Game tickets"], ["singles", "Singles"], ["value", "Value"], ["build", "Build your own"], ["record", "Record & method"]].map(([k, v]) => `<button type="button" data-seg="${k}">${v}</button>`).join("")}</nav>
    <p class="note small" data-pane="tickets">Every player line is one Winamax lists (5+, 10+, 15+ …). Type the combined odds Winamax shows in each ticket to see Place or Skip. Statistical estimates, not advice; 18+.</p>
    <section class="section" data-pane="tickets"><h2>One ticket per game <span class="sub">the main picks: each game's five legs most likely to land together</span></h2>
      <p class="sub small">Each game is simulated 20,000 times, so legs that win and lose together are priced together. A combined bet still loses more on average than a single: Winamax pays about half its fair winnings.</p>
      ${t && t.game_tickets && t.game_tickets.length ? `<div class="slips">${t.game_tickets.map(gameTicket).join("")}</div>` : t && t.locked === false ? `<p class="sub">Chosen at ${tip(t.lock_at)}, with the singles.</p>` : `<p class="sub">No game ticket today.</p>`}</section>
    <section class="section" data-pane="singles"><h2>Tonight's singles <span class="sub">each bet on its own, Winamax's margin paid once</span></h2>
      <p class="sub small">The night's best values among winners, handicaps, totals and player legs: our chance times the odds Winamax is expected to pay (its real odds for winners; for the rest, its usual discount, about 0.87 to 0.93 of the fair odds). Only positive values are listed. Bet one only if Winamax shows at least the "take ≥" odds.</p>${singles}</section>

    <details class="section" data-pane="build"><summary><h2 style="display:inline">Parlays <span class="sub">set aside: a combiné pays about half its fair winnings, so it loses more on average</span></h2></summary>
    ${t && t.locked === false ? `<section class="section"><div class="panel"><h3>Today's tickets are chosen at ${tip(t.lock_at)}</h3><p class="sub">Three hours before the first tip-off, once the main injury reports are in, the full model picks the day's tickets once. From then on they never change: no reshuffling on reload. If a player in a locked ticket is ruled out later, his leg is flagged (Winamax voids a leg whose player does not play).</p></div></section>`
      : t && t.parlays && t.parlays.length ? `${t.parlays.map((pr, i) => ticket(pr, i === 0, i)).join("")}` : `<p class="empty">No ticket today: not enough legs pass the filters. That is an answer too.</p>`}
    </details>
    <section class="section" data-pane="build"><h2>Build your own ticket</h2><div class="panel"><div id="custom">${custom()}</div><p class="sub small" style="margin-top:10px">Optional stake to record with your bets (for your own log; the site never suggests stakes): <input id="stake" type="number" min="0" step="0.5" class="oddsin" style="width:90px"></p></div></section>
    <section class="section" data-pane="record"><h2>My bets <span class="sub">kept in this browser only</span></h2><div id="mybets">${myBets()}</div>
      <p style="margin-top:10px"><button class="copybtn" id="exp">Export my bets</button> <label class="copybtn" style="display:inline-block">Import<input id="imp" type="file" accept="application/json" hidden></label></p></section>
    <section class="section" data-pane="value"><h2>Winamax vs Pinnacle <span class="sub">winners where Winamax pays more than the sharpest price</span></h2>
      <p class="sub small">Pinnacle's odds with its margin removed are the best available estimate of the true chance. When Winamax pays more than that, the bet profits in the long run whatever any model says. "Value" = an edge of 2% or more and our model not rating the side clearly lower. Got a boost (<i>cote boostée</i>)? Type the boosted odds: the edge recalculates against Pinnacle's fair price.</p>
      ${valueHtml}${valueRec}</section>
    <section class="section" data-pane="record"><h2>Closing-line value <span class="sub">did the market move our way after we published?</span></h2>
      <div class="grid">${clvBox("Ticket legs", clv.tickets, "Measured from the first frozen slate on.")}${clvBox("Every published leg", clv.all_legs, "Measured from the first frozen slate on.")}
      <div class="panel"><h3>Model vs market</h3>${mc.n ? `<div class="adv"><div><b>${mc.with}/${mc.n}</b>games where the closing price moved towards the model<br>${pct(mc.with / mc.n)}</div><div><b>${sgn((mc.avg_move_our_way || 0) * 100, 2)}</b>avg chance points our way</div></div>` : `<p class="sub small">Every game where the model disagreed with the opening price: did the closing price move towards the model? Fills in as games are played.</p>`}</div></div></section>
    <section class="section" data-pane="record"><h2 class="mind">The bettor's mind <span class="sub">what research on bettors says goes wrong</span></h2><div class="grid2"><div class="panel mind"><ul class="checklist">
      <li><b>Decide the stake before you look at the payout.</b> Prospect theory: people overweight small chances of big wins, which is exactly what long tickets sell.</li>
      <li><b>Don't add a leg to make the odds look better.</b> Every extra leg adds margin; if a leg wasn't worth taking alone, it isn't worth taking in a ticket.</li>
      <li><b>No chasing.</b> After a loss, bettors take riskier bets to win it back; after a win, they feel skilled. Both change the bet, not the chances.</li>
      <li><b>Streaks are not memory.</b> A team or player being "due" is the gambler's fallacy; a hot hand is only real here if the measured effect says so.</li>
      <li><b>Distrust the story you like.</b> Confirmation bias makes the leg you want feel safer. The chance on this page doesn't know which team you support.</li>
      <li><b>Judge yourself on closing prices, not results.</b> A month of wins or losses is mostly luck; beating the closing price is skill.</li></ul></div>
      <div class="panel"><h3>How sure are the player chances?</h3><p class="sub small">Model chances are shrunk towards 50% by a factor fitted on past player-games (1.00 = no change needed), so "80%" should land about 80% of the time.</p>${calHtml}</div></div></section>
    <section class="section" data-pane="record"><h2>Track record</h2>${recHtml}${selHtml}${hist}</section>
    <section class="section" data-pane="build"><h2>All strong legs today <span class="sub">tick to build your own ticket</span></h2>${board}</section>
    <section class="section" data-pane="record"><details class="howto"><summary>How tickets are chosen</summary>
    <div class="principles">
      <div><span class="n">1</span><b>Every leg must stand alone</b>A leg goes in only if its chance beats its price. A parlay of bad bets is a worse bet, not a better one.</div>
      <div><span class="n">2</span><b>Fewer legs, less margin</b>The margin compounds with every leg: about 9% with two legs and around 24% with six at standard prices. The Value 2 is the main pick; the three long shots pay far more and land far less.</div>
      <div><span class="n">3</span><b>Beat the closing price</b>The quickest proof of an edge is getting better odds than the final price before tip-off, long before wins and losses can tell.</div>
      <div><span class="n">4</span><b>Psychology both ways</b>Team and player spots are inside the chances, and no leg is picked with a psychological spot working against it.</div>
    </div>
    ${t && t.book ? `<p class="verdict"><b>Every leg below is listed on ${t.book === "winamax_fr" ? "Winamax" : h(t.book)}</b>, at its own line and price (from the last refresh: prices move, so check the slip). ${t.not_on_book && t.not_on_book.length ? `Not on ${t.book === "winamax_fr" ? "Winamax" : h(t.book)} yet, so left out: ${t.not_on_book.map(x => h(x.split(" at ").map(a => T(a).short).join(" at "))).join(", ")}.` : ""}</p>` : ""}
    <p class="note small">${oddsNote}</p></details></section></div>`;
  showSeg(LS.get("tipoff.seg", "tickets"));
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
    if (e.target.closest(".tkodds")) return;  // handled globally
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
      else { const pr = tkOf(t, k); if (!pr) return; recordBet(pr.name, pr.legs, tkP(pr), LS.get(tkKey(pr), null)); }
      document.getElementById("mybets").innerHTML = myBets();
      r.textContent = "Recorded";
    }
    const del = e.target.closest("[data-del]");
    if (del) { const b = LS.get(BETS_KEY, []); b.splice(+del.dataset.del, 1); LS.set(BETS_KEY, b); document.getElementById("mybets").innerHTML = myBets(); }
    if (e.target.id === "exp") {
      const blob = new Blob([JSON.stringify(LS.get(BETS_KEY, []), null, 1)], { type: "application/json" });
      const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `tipoff-my-bets-${new Date().toISOString().slice(0, 10)}.json`; a.click();
    }
  };
}

/* ---------------------------------------------------------------- the public record: every ticket ever issued */
function tallyHist(hist) {
  const z = () => ({ n: 0, hits: 0, exp: 0, legs: 0, leg_hits: 0, leg_exp: 0 });
  const out = { game: z(), single: z() };
  (hist || []).forEach(d => {
    (d.game_tickets || []).filter(t => t.result === "hit" || t.result === "miss").forEach(t => {
      const a = out.game; a.n++; a.hits += t.result === "hit"; a.exp += t.p;
      t.legs.filter(l => l.result === "hit" || l.result === "miss").forEach(l => { a.legs++; a.leg_hits += l.result === "hit"; a.leg_exp += l.p; });
    });
    (d.singles || []).filter(l => l.result === "hit" || l.result === "miss").forEach(l => { const a = out.single; a.n++; a.hits += l.result === "hit"; a.exp += l.p; });
  });
  return out;
}
function recStrip(par) {
  const hist = (par && par.history) || [], last = hist.find(d => (d.game_tickets || []).some(t => t.result));
  const all = tallyHist(hist).game;
  if (!all.n) return "";
  const lt = last ? last.game_tickets.filter(t => t.result) : [];
  return `<section class="rec-strip" aria-label="Our record">
    ${last ? `<div><span>${h(longDay(last.day))}</span><b>${lt.filter(t => t.result === "hit").length} of ${lt.length}</b><em>game tickets landed</em></div>` : ""}
    <div><span>All game tickets so far</span><b>${all.hits} of ${all.n}</b><em>landed · we said ${fx(all.exp, 1)}</em></div>
    <div><span>Legs</span><b>${pct(all.leg_hits / Math.max(all.legs, 1))}</b><em>landed · we said ${pct(all.leg_exp / Math.max(all.legs, 1))}</em></div>
    <a class="pill-btn" href="#/results">Every ticket, every result</a></section>`;
}
/* the replay of two past seasons: what the tickets would have done, and what they would have paid */
function replayPanel(r) {
  if (!r || !r.seasons) return "";
  const S = r.seasons, sum = k => S.reduce((a, x) => a + x[k], 0);
  const n = sum("tickets"), land = sum("landed"), exp = sum("expected"), fair = sum("fair"), wmx = sum("winamax");
  return `<section class="section rp"><h2>Before going live: two past seasons replayed</h2>
    <p class="sub">${h(r.note)}</p>
    <div class="rp-grid">
      <div class="tile"><p class="k">Tickets landed</p><p class="v num">${land.toLocaleString("en-GB")} of ${n.toLocaleString("en-GB")}</p><p class="sub small">the chances said ${fx(exp, 0)} (${pct(exp / n)}): ${land >= exp ? "a little more landed than stated" : "a little fewer landed than stated"}</p></div>
      <div class="tile"><p class="k">Legs landed</p><p class="v num">${pct(sum("legs_landed") / sum("legs"))}</p><p class="sub small">${sum("legs_landed").toLocaleString("en-GB")} of ${sum("legs").toLocaleString("en-GB")}; stated ${pct(sum("legs_expected") / sum("legs"))}</p></div>
      <div class="tile"><p class="k">At fair odds</p><p class="v num up">${sgn(fair, 1)}</p><p class="sub small">units over ${n.toLocaleString("en-GB")} tickets (${sgn(fair / n * 100, 1)}% a ticket)</p></div>
      <div class="tile"><p class="k">At Winamax's estimated payout</p><p class="v num down">${sgn(wmx, 1)}</p><p class="sub small">units (${sgn(wmx / n * 100, 0)}% a ticket)</p></div>
    </div>
    <p class="verdict"><b>What this means.</b> The chances are honest and the tickets land a little more often than stated, so at fair odds they would make a small profit. But combined bets are where bookmakers take the most: if Winamax pays about half the fair winnings, as assumed here, the same tickets lose about a third of every stake. That payout is an estimate. The odds you record on your tickets (<a href="#/you">Your bets</a>) are what settles it: place a ticket only when Winamax's odds reach the "Place at" figure.</p>
    <div class="tscroll"><table class="rp-t"><tr><th>Season</th><th class="n">Tickets</th><th class="n">Landed</th><th class="n">Stated</th><th class="n">Fair odds</th><th class="n">Winamax est.</th></tr>
      ${S.map(x => `<tr><td>${h(x.season)}</td><td class="n">${x.tickets}</td><td class="n">${x.landed}</td><td class="n">${fx(x.expected, 1)}</td><td class="n up">${sgn(x.fair, 1)}</td><td class="n down">${sgn(x.winamax, 1)}</td></tr>`).join("")}</table></div>
  </section>`;
}
async function results() {
  const [par, rp] = await Promise.all([get("parlay.json"), get("replay.json").catch(() => null)]);
  PAR = par;
  setTitle("Results");
  const hist = par.history || [], tl = tallyHist(hist), g = tl.game, s1 = tl.single;
  const badge = r => r === "hit" ? `<span class="rs-b up">Landed</span>` : r === "miss" ? `<span class="rs-b down">Missed</span>` : `<span class="rs-b">Pending</span>`;
  const legMark = r => r === "hit" ? `<b class="up">✓</b>` : r === "miss" ? `<b class="down">✗</b>` : r === "void" ? `<b class="sub">void</b>` : `<b class="sub">·</b>`;
  const days = hist.filter(d => (d.game_tickets || []).length || (d.singles || []).length).map(d => {
    const gts = d.game_tickets || [], sg = d.singles || [], landed = gts.filter(t => t.result === "hit").length, done = gts.filter(t => t.result).length;
    return `<section class="rs-day"><header><h2>${h(longDay(d.day))}</h2><p class="sub">${gts.length ? `${done ? `${landed} of ${done} game tickets landed` : "game tickets pending"}` : ""}${sg.length ? ` · ${sg.filter(l => l.result === "hit").length} of ${sg.filter(l => l.result === "hit" || l.result === "miss").length} singles` : ""}</p></header>
      ${gts.length ? `<ul class="rs-list">${gts.map(t => `<li><details><summary><span class="rs-name">${h(String(t.name).split(" at ").length === 2 ? String(t.name).split(" at ").map(x => T(x).short).join(" at ") : t.name)}</span><span class="rs-p"><b>${pct(t.p)}</b><span>stated</span></span><span class="rs-p"><b>${fx(t.fair, 2)}</b><span>fair odds</span></span>${badge(t.result)}</summary>
        <ul class="rs-legs">${t.legs.map(l => `<li>${legMark(l.result)}<span>${h(l.desc)}</span><span class="sub">${pct(l.p)}</span></li>`).join("")}</ul></details></li>`).join("")}</ul>` : ""}
      ${sg.length ? `<details class="rs-singles"><summary>Singles (${sg.length})</summary><ul class="rs-legs">${sg.map(l => `<li>${legMark(l.result)}<span>${h(l.desc)}</span><span class="sub">${pct(l.p)}${l.wmx ? ` · ${fx(l.wmx, 2)}` : ""}</span></li>`).join("")}</ul></details>` : ""}
    </section>`;
  }).join("");
  app.innerHTML = `<section class="hero court"><div class="wrap"><h1>Every ticket, every result</h1>
    <p class="lede" style="margin-top:10px">Each night's tickets are frozen when they're chosen and scored after the last game. Nothing is removed or edited afterwards, wins or losses.</p></div></section>
  <div class="wrap">${demoBanner()}
    <div class="rs-sum">
      <div class="tile"><p class="k">Game tickets landed</p><p class="v num">${g.n ? `${g.hits} of ${g.n}` : "–"}</p><p class="sub small">${g.n ? `we said ${fx(g.exp, 1)} (${pct(g.exp / g.n)}), it was ${pct(g.hits / g.n)}` : "scored after tonight's games"}</p></div>
      <div class="tile"><p class="k">Ticket legs landed</p><p class="v num">${g.legs ? pct(g.leg_hits / g.legs) : "–"}</p><p class="sub small">${g.legs ? `${g.leg_hits} of ${g.legs}; we said ${pct(g.leg_exp / g.legs)}` : ""}</p></div>
      <div class="tile"><p class="k">Singles landed</p><p class="v num">${s1.n ? `${s1.hits} of ${s1.n}` : "–"}</p><p class="sub small">${s1.n ? `we said ${fx(s1.exp, 1)}` : ""}</p></div>
    </div>
    <p class="note small">A ticket's chance is the share of the time it should land. When we say 37%, about 37 of 100 such tickets should land; landing more or less over a few nights is mostly luck. Combined bets lose money on average at usual bookmaker prices, which is why every ticket shows the odds it is worth placing at. Statistical estimates, not advice; 18+.</p>
    ${days || `<p class="empty">The first tickets are scored after tonight's games.</p>`}
    ${replayPanel(rp)}
  </div>`;
}

document.addEventListener("click", e => {
  const pn = e.target.closest && e.target.closest("a.pc-name[href^='#/player/']");
  if (pn && document.startViewTransition && !REDUCED) { LAST_PLAYER = null; pn.style.viewTransitionName = "player-name"; return; }
  const card = e.target.closest && e.target.closest("a.gm[href^='#/game/'], a[href^='#/game/'] > .gm");
  if (card && document.startViewTransition && !REDUCED) { LAST_GAME = null; card.style.viewTransitionName = "game-hero"; }
}, true);

/* ---------------------------------------------------------------- live tickets: legs follow the game as it is played */
// Straight from ESPN's public game feed in the browser (it allows it), every 45 s while the page is open and a
// ticket's game is on. Nothing is stored: the official results still come from the nightly scoring.
let liveTimer = null;
const LIVE_NAME = { pts: "pts", reb: "reb", ast: "ast", tpm: "threes", pra: "pts+reb+ast" };
function stopLive() { clearInterval(liveTimer); liveTimer = null; }
function startLive() { stopLive(); if (app.querySelector(".slip[data-game]")) { liveTick(); liveTimer = setInterval(liveTick, 45000); } }
async function liveGame(gid) {
  const j = await fetch(`https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=${encodeURIComponent(gid)}`).then(r => r.json());
  const comp = j.header.competitions[0], st = comp.status.type;
  const side = k => comp.competitors.find(c => c.homeAway === k) || {};
  const g = { state: st.state, final: st.completed, clock: st.shortDetail, players: {},
              home: { abbr: side("home").team.abbreviation, pts: +side("home").score || 0 }, away: { abbr: side("away").team.abbreviation, pts: +side("away").score || 0 } };
  for (const tm of (j.boxscore && j.boxscore.players) || []) for (const blk of tm.statistics || []) for (const a of blk.athletes || []) {
    const v = a.stats || [];
    if (!v.length) continue;
    const r = { min: +v[0] || 0, pts: +v[1] || 0, reb: +v[5] || 0, ast: +v[6] || 0, tpm: +String(v[3] || "0").split("-")[0] || 0 };
    r.pra = r.pts + r.reb + r.ast;
    g.players[String(a.athlete.id)] = r;
  }
  return g;
}
function liveLeg(l, g) {
  const fin = g.final, mine = l.team === g.home.abbr ? g.home : g.away, opp = l.team === g.home.abbr ? g.away : g.home;
  const over = l.side !== "under", L = l.kind === "prop" ? lineOf(l) : l.line;
  if (l.kind === "prop") {
    const r = g.players[String(l.player)];
    if (!r) return { state: fin ? "void" : "live", txt: fin ? "did not play" : "not on the floor yet" };
    const v = r[l.stat] ?? 0, ok = over ? v > L : v < L;
    return { state: over ? (ok ? "hit" : fin ? "miss" : "live") : (!ok ? "miss" : fin ? "hit" : "live"), txt: `${v} ${LIVE_NAME[l.stat] || l.stat} · needs ${over ? Math.floor(L) + 1 : "under " + L}`, prog: Math.min(1, v / Math.max(L + 0.5, 1)) };
  }
  if (l.kind === "ml") { const d = mine.pts - opp.pts; return { state: fin ? (d > 0 ? "hit" : "miss") : "live", txt: `${mine.abbr} ${mine.pts}-${opp.pts}` }; }
  if (l.kind === "spread") { const d = mine.pts - opp.pts + L; return { state: fin ? (d > 0 ? "hit" : d < 0 ? "miss" : "void") : "live", txt: `${mine.abbr} ${mine.pts}-${opp.pts}, covering by ${fx(d, 1)}` }; }
  if (l.kind === "total" || l.kind === "team_total") {
    const t = l.kind === "total" ? g.home.pts + g.away.pts : mine.pts, ok = over ? t > L : t < L;
    return { state: over ? (ok ? "hit" : fin ? "miss" : "live") : (!ok ? "miss" : fin ? "hit" : "live"), txt: `${t} points · line ${fx(L, 1)}`, prog: Math.min(1, t / L) };
  }
  return { state: "live", txt: "" };
}
async function liveTick() {
  if (document.hidden) return;
  const slips = [...app.querySelectorAll(".slip[data-game]")];
  if (!slips.length) return stopLive();
  const idx = legIndex(), now = Date.now();
  for (const slip of slips) {
    const tipAt = Date.parse(slip.dataset.tip || "");
    if (!(tipAt <= now + 60000) || slip.dataset.done) continue;
    let g;
    try { g = await liveGame(slip.dataset.game); } catch (e) { continue; }
    if (g.state === "pre") continue;
    let hit = 0, miss = 0, n = 0;
    slip.querySelectorAll(".sl[data-lid]").forEach(li => {
      const l = idx[li.dataset.lid]; if (!l) return;
      const r = liveLeg(l, g), el = li.querySelector("[data-live]");
      n++; hit += r.state === "hit" || r.state === "void"; miss += r.state === "miss";
      li.classList.remove("hit", "miss", "inplay"); li.classList.add(r.state === "void" || r.state === "live" ? "inplay" : r.state);
      if (el) { el.hidden = false; el.innerHTML = `<i style="--prog:${r.prog ?? (r.state === "hit" ? 1 : 0)}"></i>${h(r.txt)}`; }
    });
    const head = slip.querySelector(".slip-live");
    if (head) { head.hidden = false; head.className = `slip-live ${miss ? "down" : hit === n ? "up" : ""}`;
      head.textContent = miss ? `Lost · ${g.clock}` : hit === n ? (g.final ? "Landed" : `All ${n} in · ${g.clock}`) : `${hit} of ${n} in · ${g.clock}`; }
    if (g.final) slip.dataset.done = "1";
  }
}

/* share a ticket: the phone's share sheet, or the link copied (the link opens as a picture of the slip) */
document.addEventListener("click", async e => {
  const b = e.target.closest && e.target.closest("[data-share]");
  if (!b) return;
  const url = new URL(b.dataset.share, location.href.split("#")[0]).href;
  try {
    if (navigator.share) await navigator.share({ title: b.dataset.title || "Tip-Off Numbers ticket", url });
    else { await navigator.clipboard.writeText(url); b.textContent = "Link copied"; setTimeout(() => { b.textContent = "Share"; }, 2000); }
  } catch (err) { /* share sheet closed */ }
});

/* ---------------------------------------------------------------- Tickets page: one section at a time */
function showSeg(k) {
  const panes = app.querySelectorAll("[data-pane]");
  if (!panes.length) return;
  if (![...panes].some(p => p.dataset.pane === k)) k = "tickets";
  panes.forEach(p => { p.hidden = p.dataset.pane !== k; });
  app.querySelectorAll("[data-seg]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.seg === k)));
  LS.set("tipoff.seg", k);
}
document.addEventListener("click", e => {
  const b = e.target.closest && e.target.closest("[data-seg]");
  if (!b) return;
  showSeg(b.dataset.seg);
  const nav = b.closest(".segs");
  if (nav && nav.getBoundingClientRect().top < 0) nav.scrollIntoView({ block: "start" });
});
