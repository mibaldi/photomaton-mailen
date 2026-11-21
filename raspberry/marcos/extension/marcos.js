// Marcos del photomatón: se carga en el quiosco (Chromium --load-extension) sobre photobooth-app.
// El marco y el modo (foto / tira / boomerang) los guarda marcos-servicio.py (127.0.0.1:8010),
// que también usan los mandos y el BLE.
(() => {
  const API = "http://127.0.0.1:8010";
  let est = { actual: 0, modo: "foto", marcos: [] }, bloqueado = 0, tNombre = null;
  const MODO = { foto: "📷 Foto", tira: "🎞 Tira de 4", boomerang: "🔁 Boomerang" };
  const PISTA = { tira: "🎞 4 fotos seguidas", boomerang: "🔁 Vídeo de ida y vuelta" };
  const BLOQUEO = { foto: 7000, tira: 22000, boomerang: 16000 };

  const el = (tag, id, txt) => { const e = document.createElement(tag); e.id = id; if (txt) e.textContent = txt; document.body.appendChild(e); return e; };
  const marco = el("img", "pm-marco");
  const ant = el("button", "pm-ant", "‹"), sig = el("button", "pm-sig", "›"), disparo = el("button", "pm-disparo", "📷");
  const nombre = el("div", "pm-nombre");
  const bModo = el("button", "pm-modo"), pista = el("div", "pm-pista");
  [ant, sig, disparo, bModo].forEach(b => b.classList.add("pm-ctl"));

  async function llamar(ruta, metodo = "POST") {
    const r = await fetch(API + ruta, { method: metodo, cache: "no-store" });
    return r.json();
  }
  function aplicar(nuevo, avisar) {
    const cambio = nuevo.actual !== est.actual || nuevo.marcos.length !== est.marcos.length;
    const cambioModo = nuevo.modo !== est.modo;
    est = nuevo;
    bModo.textContent = MODO[est.modo] || est.modo;
    if (cambioModo && avisar !== false) mostrarNombre(MODO[est.modo]);
    const m = est.marcos[est.actual];
    if (m && (cambio || !marco.src)) marco.src = `${API}/png/${m.archivo}`;
    if (m && cambio && avisar !== false) mostrarNombre(m.nombre);
  }
  function mostrarNombre(t) {
    nombre.textContent = t.startsWith("📷") || t.startsWith("🎞") || t.startsWith("🔁") ? t : `🖼 ${t}`; nombre.classList.add("on");
    clearTimeout(tNombre); tNombre = setTimeout(() => nombre.classList.remove("on"), 1500);
  }
  const cambiar = ruta => async e => {
    e.preventDefault(); e.stopPropagation();
    try { aplicar(await llamar(ruta)); } catch {}
  };
  bModo.addEventListener("click", cambiar("/modo_sig"));
  ant.addEventListener("click", cambiar("/anterior"));
  sig.addEventListener("click", cambiar("/siguiente"));
  disparo.addEventListener("click", async e => {
    e.preventDefault(); e.stopPropagation();
    bloqueado = Date.now() + (BLOQUEO[est.modo] || 7000); colocar();
    try { await llamar("/disparar"); } catch {}
  });

  // La previsualización en directo: photobooth-app 9 la pinta en un <canvas> dentro de .canvas-stack
  // (el otro canvas de la pila es el fondo difuminado); versiones antiguas usaban un <img> MJPEG
  function buscarStream() {
    for (const c of document.querySelectorAll(".canvas-stack canvas")) {
      if (c.width >= 320 && c.offsetWidth > 50 && c.offsetHeight > 50) return c;
    }
    for (const i of document.querySelectorAll("img")) {
      if (/stream\.mjpg|aquisition/.test(i.src) && i.offsetWidth > 50 && i.offsetHeight > 50) return i;
    }
    return null;
  }
  function cajaContenido(img) {
    // rectángulo real de la imagen dentro del <img> (object-fit: contain / cover)
    const r = img.getBoundingClientRect(), fit = getComputedStyle(img).objectFit;
    const lienzo = img.tagName === "CANVAS";
    const nw = (lienzo ? img.width : img.naturalWidth) || 16, nh = (lienzo ? img.height : img.naturalHeight) || 9;
    if (fit !== "contain" && fit !== "cover") return r;
    const esc = (fit === "contain" ? Math.min : Math.max)(r.width / nw, r.height / nh);
    const w = nw * esc, h = nh * esc;
    return { left: r.left + (r.width - w) / 2, top: r.top + (r.height - h) / 2, width: w, height: h };
  }
  function enInicio() { return location.hash === "" || location.hash === "#/" || location.hash === "#"; }

  function colocar() {
    const s = buscarStream();
    const ver = !!s && enInicio(), foto = est.modo === "foto";
    const m = est.marcos[est.actual];
    if (s) s.style.filter = foto && m && m.filtro ? "grayscale(1)" : "";
    if (ver && foto) {
      const c = cajaContenido(s);
      Object.assign(marco.style, { left: c.left + "px", top: c.top + "px", width: c.width + "px", height: c.height + "px", display: est.marcos.length ? "block" : "none" });
    } else marco.style.display = "none";
    const ctl = ver && Date.now() > bloqueado;
    ant.style.display = sig.style.display = ctl && foto && est.marcos.length > 1 ? "flex" : "none";
    disparo.style.display = bModo.style.display = ctl ? "flex" : "none";
    pista.textContent = PISTA[est.modo] || "";
    pista.style.display = ctl && !foto ? "block" : "none";
  }

  async function sincronizar() {
    try { aplicar(await llamar("/estado", "GET")); } catch {}
  }
  sincronizar();
  setInterval(sincronizar, 1000);      // por si se cambia el marco desde el móvil
  setInterval(colocar, 250);
  addEventListener("resize", colocar);
})();
