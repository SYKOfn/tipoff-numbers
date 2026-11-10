/* Tip-Off Numbers offline support. Everything is fetched fresh from the network first (the data changes
   every 15 minutes and must never be stale); the last good copy is kept and used only when there is no signal. */
const CACHE = "tipoff-v1";
const SHELL = ["./", "./index.html", "./styles.css", "./app.js", "./manifest.webmanifest", "./icons/icon-192.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET" || new URL(req.url).origin !== location.origin) return;
  e.respondWith(
    fetch(req).then(res => {
      if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(stripVersion(req), copy)); }
      return res;
    }).catch(() => caches.match(stripVersion(req)).then(r => r || caches.match("./index.html")))
  );
});
// app.js?v=123 and app.js are the same file for the offline copy
function stripVersion(req) {
  const u = new URL(req.url);
  if (u.searchParams.has("v") || u.searchParams.has("t")) { u.searchParams.delete("v"); u.searchParams.delete("t"); return new Request(u.toString()); }
  return req;
}
