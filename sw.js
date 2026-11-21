const C="photomaton-v16", F=["./","index.html","manifest.json","icon.svg","voz/1.mp3","voz/2.mp3","voz/3.mp3","voz/4.mp3","voz/5.mp3","voz/patata.mp3","marcos/marcos.json",
  ...["mailen","confeti","polaroid","pelicula","neon","dorado"].map(m=>"marcos/png/"+m+".png")];
self.addEventListener("install",e=>{e.waitUntil(caches.open(C).then(c=>c.addAll(F)));self.skipWaiting()});
self.addEventListener("activate",e=>e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==C).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener("fetch",e=>{
  if(new URL(e.request.url).pathname.endsWith("version.json")) return; // siempre a la red
  e.respondWith(fetch(e.request).then(r=>{const k=r.clone();caches.open(C).then(c=>c.put(e.request,k));return r}).catch(()=>caches.match(e.request,{ignoreSearch:true})));
});
