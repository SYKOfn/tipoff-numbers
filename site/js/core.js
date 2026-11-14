/* Tip-Off Numbers: Data loading, helpers and the pieces every page uses (team discs, cards, tables).
   Plain scripts loaded in order (index.html); they share one global scope, no build step. */
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
// the league's usual three-letter codes for labels (the feed uses GS, SA, NO, NY, WSH, UTAH)
const lab3 = ab => ({ UTAH: "UTA", GS: "GSW", SA: "SAS", NO: "NOP", NY: "NYK", WSH: "WAS" })[ab] || ab;
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
  if (t.logo) return `<span class="disc logo ${size}" style="--tc:${teamInk(ab)}"><img src="${h(logoDark(t))}" alt="" loading="lazy" decoding="async"></span>`;
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
