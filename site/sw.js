// 데이터 캐시: data/*?v=버전 요청을 브라우저에 저장해 두고, 버전(=빌드)이 같으면 다시 받지 않음
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', e => {
  const u = new URL(e.request.url);
  if (e.request.method !== 'GET' || u.origin !== location.origin || !u.pathname.includes('/data/') || !u.searchParams.get('v')) return;
  e.respondWith(handle(e.request, u));
});
async function handle(req, u) {
  const name = 'data-' + u.searchParams.get('v'), range = req.headers.get('range') || '';
  const key = u.href + (range ? (u.search ? '&' : '?') + '_r=' + encodeURIComponent(range) : '');
  let c;
  try { c = await caches.open(name); const hit = await c.match(key); if (hit) return hit; } catch (e) { return fetch(req); }
  caches.keys().then(ks => ks.forEach(k => k.startsWith('data-') && k !== name && caches.delete(k)));  // 지난 버전 정리
  const res = await fetch(req);
  if (res.ok) {
    const body = await res.clone().arrayBuffer(), h = new Headers(res.headers);
    h.delete('content-encoding'); h.delete('content-range'); h.set('content-length', body.byteLength);
    c.put(key, new Response(body, { status: 200, headers: h })).catch(() => {});  // 206은 저장이 안 돼서 200으로
  }
  return res;
}
