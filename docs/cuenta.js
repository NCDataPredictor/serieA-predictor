/* NCData Predictor · Cuenta y rendimiento de tus picks (26-nov, pedido de Nicolas)
   Un solo archivo para todo el sitio (se sirve en /cuenta.js; lo cargan la portada, /nba/, /serie-a/, /premier/ y
   /champions/). Hace tres cosas:
   1. Botón de cuenta arriba (#cuenta-btn de cada página): entrar con correo y contraseña, o con un enlace al correo, vía Supabase.
   2. Sincroniza tus picks guardados (las claves de localStorage de cada liga) con tu cuenta, para verlos en cualquier
      celular o computador. Sin sesión todo sigue funcionando como antes, solo en este navegador.
   3. Rendimiento: cada liga deja aquí la lista liquidada de tus picks (clave ncdp-rend-<liga>, ver NCDP.rend) y este
      archivo pinta la franja "Tus picks en esta liga" ([data-ncdp-tira]) y la sección general de la portada
      ([data-ncdp-resumen]).
   Supabase: tabla public.ncdp_datos (user_id, clave, valor jsonb, actualizado) con RLS; esquema en supabase/esquema.sql. */
(function () {
  "use strict";
  // Proyecto de Supabase. La clave "anon" es pública (va en el navegador); la seguridad la ponen las políticas RLS.
  const CFG = { url: "https://uewkpclgdjdefaubdbhq.supabase.co", anon: "sb_publishable_3UGyFjVA6sBuxRPBpMGYig_eaLgeria", google: false };
  const SB_JS = "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.118.0/dist/umd/supabase.js";

  const LIGAS = {
    "nba": { nombre: "NBA", url: "/nba/", logo: "/logos/nba-logoman.svg", c: "#1d428a", claves: ["nbap-mine"] },
    "serie-a": { nombre: "Serie A", url: "/serie-a/", logo: "/logos/serie-a.png", c: "#0032a0", claves: ["sap-mine", "sap-combis"] },
    "premier": { nombre: "Premier League", url: "/premier/", logo: "/logos/premier.png", c: "#5b0a63", claves: ["epl-mine", "epl-combis"] },
    "champions": { nombre: "Champions League", url: "/champions/", logo: "/logos/champions.png", c: "#1b2a7a", claves: ["ucl-mine", "ucl-combis"] },
  };
  const REND = l => "ncdp-rend-" + l;
  const SYNC = new Set(Object.entries(LIGAS).flatMap(([id, L]) => [...L.claves, REND(id)]));
  const META_K = "ncdp-sync";
  const me = document.currentScript;
  const LIGA = (me && me.dataset.liga) || (location.pathname.match(/^\/(nba|serie-a|premier|champions)\//) || [])[1] || null;

  const ST = localStorage;
  const get = k => { try { return ST.getItem(k); } catch (e) { return null; } };
  let setOrig = null;
  const setRaw = (k, v) => { try { (setOrig || Storage.prototype.setItem).call(ST, k, v); } catch (e) {} };
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const jparse = (s, d) => { try { const x = JSON.parse(s); return x == null ? d : x; } catch (e) { return d; } };
  const hash = s => { let h = 5381; s = String(s ?? ""); for (let i = 0; i < s.length; i++) h = (h * 33 ^ s.charCodeAt(i)) >>> 0; return h.toString(36) + "." + s.length; };
  const canon = s => s == null ? null : JSON.stringify(jparse(s, null));

  /* ---------- 1. cambios locales: cualquier escritura de una clave sincronizada agenda una subida ---------- */
  try {
    setOrig = Storage.prototype.setItem;
    const remOrig = Storage.prototype.removeItem;
    Storage.prototype.setItem = function (k, v) { setOrig.call(this, k, v); if (this === ST && SYNC.has(k)) cambio(k); };
    Storage.prototype.removeItem = function (k) { remOrig.call(this, k); if (this === ST && SYNC.has(k)) cambio(k); };
  } catch (e) {}
  const oyentes = new Set();
  function cambio(k) { if (k.startsWith("ncdp-rend-")) avisar(); agendar(); }
  function avisar() { oyentes.forEach(f => { try { f(); } catch (e) {} }); pintarTodo(); }

  /* ---------- 2. rendimiento ---------- */
  // Cada liga llama NCDP.rend(liga, picks) con sus picks y combinadas ya liquidados:
  // [{f: "AAAA-MM-DD", e: "g"|"p"|"n"|"x" (ganado, perdido, nulo, pendiente), u: unidades, c: cuota}]
  function rend(liga, picks) {
    const v = JSON.stringify((picks || []).map(x => ({ f: String(x.f || "").slice(0, 10), e: x.e, u: +(+x.u || 0).toFixed(3), c: +(+x.c || 0).toFixed(2) })));
    const cur = get(REND(liga));
    if (cur == null && v === "[]") return;
    if (canon(cur) !== v) ST.setItem(REND(liga), v);
  }
  function stats(ps) {
    const t = { n: ps.length, g: 0, p: 0, nulo: 0, pend: 0, u: 0 };
    ps.forEach(x => { if (x.e === "g") t.g++; else if (x.e === "p") t.p++; else if (x.e === "n") t.nulo++; else t.pend++; if (x.e === "g" || x.e === "p") t.u += x.u; });
    t.dec = t.g + t.p; t.pct = t.dec ? t.g / t.dec : null; t.roi = t.dec ? t.u / t.dec : null;
    return t;
  }
  function resumen() {
    const por = {};
    for (const id of Object.keys(LIGAS)) { const ps = jparse(get(REND(id)), []); if (Array.isArray(ps) && ps.length) por[id] = { ps, s: stats(ps) }; }
    const todos = Object.values(por).flatMap(x => x.ps);
    return { por, total: stats(todos), todos };
  }
  const fu = u => `${u > 0 ? "+" : u < 0 ? "−" : ""}${Math.abs(u).toFixed(2).replace(".", ",")} u`;
  const fp = (x, d = 0) => x == null ? "–" : (100 * x).toFixed(d).replace(".", ",") + "%";
  const froi = r => r == null ? "–" : `${r > 0 ? "+" : r < 0 ? "−" : ""}${Math.abs(100 * r).toFixed(1).replace(".", ",")}%`;
  const cls = u => u > 0 ? "pos" : u < 0 ? "neg" : "";
  const rec = s => `${s.g}–${s.p}${s.nulo ? "–" + s.nulo : ""}`;

  const ICO = {
    user: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="8.5" r="4"/><path d="M4 21c.8-4 4.2-6.5 8-6.5s7.2 2.5 8 6.5"/></svg>`,
    chart: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 17l5-5 4 3 8-8"/><path d="M15 7h5v5"/></svg>`,
    cloud: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 18a4.5 4.5 0 01-.6-9A6 6 0 0118 9.5 4 4 0 0117.5 18z"/><path d="M9.5 13.5l2 2 3.5-3.5"/></svg>`,
    mail: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3.5 6.5L12 13l8.5-6.5"/></svg>`,
  };

  /* ---------- 3. estilos (usan los colores de cada página, con alternativa) ---------- */
  const CSS = `
.nc-av { display: inline-grid; place-items: center; width: 22px; height: 22px; border-radius: 50%; background: var(--good, #00a346); color: #fff; font: 700 12px/1 var(--display, system-ui); text-transform: uppercase }
#cuenta-btn.on .nc-ico { display: none } #cuenta-btn:not(.on) .nc-av { display: none }
#cuenta-btn .nc-ico svg { width: 19px; height: 19px; display: block }
dialog.nc-dlg { border: 1px solid var(--line, #dfe1ea); border-radius: 18px; padding: 0; width: min(440px, calc(100vw - 32px)); max-width: none; max-height: min(88dvh, 760px);
  background: var(--surface, #fff); color: var(--ink, #10122a); box-shadow: 0 24px 60px rgba(0,0,0,.35); font: 15px/1.45 var(--body, system-ui) }
dialog.nc-dlg[open] { display: flex; flex-direction: column; animation: nc-up .3s cubic-bezier(.2,.7,.2,1) both }
dialog.nc-dlg::backdrop { background: rgba(5,6,25,.55); backdrop-filter: blur(2px) }
@keyframes nc-up { from { opacity: 0; transform: translateY(14px) } to { opacity: 1; transform: none } }
.nc-hd { display: flex; align-items: center; gap: 10px; padding: 16px 18px 12px; border-bottom: 1px solid var(--line, #dfe1ea) }
.nc-hd h2 { margin: 0; flex: 1; font: 700 20px/1.1 var(--display, system-ui); text-transform: uppercase; letter-spacing: .04em }
.nc-x { width: 34px; height: 34px; border-radius: 50%; border: 1px solid var(--line, #dfe1ea); background: transparent; color: inherit; font-size: 18px; cursor: pointer }
.nc-bd { padding: 14px 18px 18px; overflow: auto; display: grid; gap: 14px }
.nc-bd h3 { margin: 0 0 6px; font: 600 13px var(--display, system-ui); letter-spacing: .08em; text-transform: uppercase; color: var(--muted, #5c6079); display: flex; align-items: center; gap: 6px }
.nc-bd h3 svg { width: 16px; height: 16px }
.nc-bd p { margin: 0; color: var(--muted, #5c6079); font-size: 14px }
.nc-in { width: 100%; padding: 11px 12px; border-radius: 10px; border: 1px solid var(--line, #dfe1ea); background: var(--bg, #f6f7fb); color: inherit; font: 16px var(--body, system-ui) }
.nc-in:focus-visible, .nc-b:focus-visible, .nc-x:focus-visible { outline: 2px solid var(--accent-2, var(--accent, #0578ff)); outline-offset: 2px }
.nc-in.code { font: 600 22px var(--mono, monospace); letter-spacing: .4em; text-align: center }
.nc-b { display: inline-flex; align-items: center; justify-content: center; gap: 8px; padding: 11px 16px; border-radius: 999px; border: 0; cursor: pointer; font: 600 14px var(--display, system-ui);
  letter-spacing: .08em; text-transform: uppercase; background: var(--accent, #0578ff); color: var(--on-accent, #fff); text-decoration: none }
.nc-b.sec { background: transparent; color: inherit; border: 1px solid var(--line, #dfe1ea) }
.nc-b[disabled] { opacity: .55; cursor: default }
.nc-b svg { width: 18px; height: 18px }
.nc-row { display: flex; gap: 8px; flex-wrap: wrap } .nc-row > .nc-in { flex: 1 1 200px }
.nc-pw { display: grid; gap: 8px }
.nc-links { display: flex; flex-wrap: wrap; gap: 6px 16px; margin-top: 10px }
.nc-links button { background: none; border: 0; padding: 4px 0; color: var(--accent-2, var(--accent, #0578ff)); font: 500 13.5px var(--body, system-ui); text-decoration: underline; text-underline-offset: 3px; cursor: pointer }
.nc-links button:focus-visible { outline: 2px solid currentColor; outline-offset: 2px }
.nc-cod summary { cursor: pointer; font-size: 13.5px; color: var(--muted, #5c6079) }
.nc-msg { font-size: 13.5px; padding: 8px 10px; border-radius: 10px; background: var(--good-soft, #dcf3e5); color: var(--ink, #10122a) } .nc-msg.err { background: var(--bad-soft, #fbe2e6) }
.nc-who { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border: 1px solid var(--line, #dfe1ea); border-radius: 12px }
.nc-who .nc-av { width: 34px; height: 34px; font-size: 16px; flex: none } .nc-who b { display: block; overflow-wrap: anywhere } .nc-who small { color: var(--muted, #5c6079); font-size: 12.5px }
.nc-kpi { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 6px }
.nc-kpi > div { border: 1px solid var(--line, #dfe1ea); border-radius: 10px; padding: 7px 8px; min-width: 0 }
.nc-kpi span { display: block; font: 500 10.5px var(--mono, monospace); letter-spacing: .04em; text-transform: uppercase; color: var(--muted, #5c6079); white-space: nowrap; overflow: hidden; text-overflow: clip }
.nc-kpi b { display: block; font: 700 17px/1.2 var(--display, system-ui); white-space: nowrap }
.nc-dlg .pos, .nc-tira .pos, .nc-res .pos { color: var(--good, #00a346) } .nc-dlg .neg, .nc-tira .neg, .nc-res .neg { color: var(--bad, #db052b) }
.nc-off { font-size: 13px; color: var(--muted, #5c6079); border: 1px dashed var(--line, #dfe1ea); border-radius: 12px; padding: 10px 12px }
/* franja de cada liga */
.nc-tira { display: flex; align-items: center; flex-wrap: wrap; gap: 8px 14px; margin: 0 0 16px; padding: 10px 14px; border-radius: 14px; background: var(--surface, #fff);
  border: 1px solid var(--line, #dfe1ea); border-left: 4px solid var(--nc-c, var(--accent, #0578ff)); color: var(--ink, #10122a); text-decoration: none; animation: nc-up .4s cubic-bezier(.2,.7,.2,1) both }
.nc-tira:hover { border-color: var(--nc-c, var(--accent, #0578ff)) }
.nc-tira .t { display: flex; align-items: center; gap: 8px; font: 600 13px var(--display, system-ui); letter-spacing: .08em; text-transform: uppercase }
.nc-tira .t svg { width: 18px; height: 18px; color: var(--nc-c, var(--accent, #0578ff)) }
.nc-tira .m { display: flex; flex-wrap: wrap; gap: 4px 14px; font: 500 13px var(--mono, monospace); color: var(--muted, #5c6079) } .nc-tira .m b { color: var(--ink, #10122a); font-weight: 600 }
.nc-tira .m b.pos { color: var(--good, #00a346) } .nc-tira .m b.neg { color: var(--bad, #db052b) }
.nc-tira .go { margin-left: auto; font: 600 12.5px var(--display, system-ui); letter-spacing: .08em; text-transform: uppercase; color: var(--nc-c, var(--accent, #0578ff)) }
/* sección de la portada */
.nc-res { display: grid; gap: 14px }
.nc-res .tiles { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 150px), 1fr)) }
.nc-res .tile { background: var(--surface, #fff); border: 1px solid var(--line, #dfe1ea); border-radius: 12px; padding: 12px 14px; animation: nc-up .45s cubic-bezier(.2,.7,.2,1) both }
.nc-res .tile span { display: block; font: 500 11px var(--mono, monospace); letter-spacing: .08em; text-transform: uppercase; color: var(--muted, #5c6079) }
.nc-res .tile b { display: block; font: 700 28px/1.15 var(--display, system-ui) } .nc-res .tile small { color: var(--muted, #5c6079); font-size: 12.5px }
.nc-res .card { background: var(--surface, #fff); border: 1px solid var(--line, #dfe1ea); border-radius: 14px; padding: 14px; animation: nc-up .45s cubic-bezier(.2,.7,.2,1) both }
.nc-res .card h3 { margin: 0 0 2px; font: 600 15px var(--display, system-ui); letter-spacing: .06em; text-transform: uppercase }
.nc-res .card p { margin: 0 0 8px; color: var(--muted, #5c6079); font-size: 13px }
.nc-res svg.curva { width: 100%; height: auto; display: block; overflow: visible }
.nc-res svg.curva text { font: 500 11px var(--mono, monospace); fill: var(--muted, #5c6079) }
.nc-res .curva .linea { fill: none; stroke-width: 2.5; stroke-linejoin: round; stroke-dasharray: var(--len); stroke-dashoffset: var(--len); animation: nc-draw .6s ease-out forwards }
@keyframes nc-draw { to { stroke-dashoffset: 0 } }
.nc-res .ligas { display: grid; gap: 8px }
.nc-res .liga { display: grid; grid-template-columns: 34px minmax(0, 1fr) auto; align-items: center; gap: 4px 12px; padding: 10px 12px; border-radius: 12px; border: 1px solid var(--line, #dfe1ea);
  border-left: 4px solid var(--nc-c); text-decoration: none; color: inherit; background: var(--surface, #fff); transition: transform .15s }
.nc-res .liga:hover, .nc-res .liga:focus-visible { transform: translateY(-1px); outline: none; border-color: var(--nc-c) }
.nc-res .liga .lg { width: 34px; height: 34px; border-radius: 8px; background: #fff; display: grid; place-items: center; padding: 4px; box-shadow: 0 1px 3px rgba(0,0,0,.2) }
.nc-res .liga .lg img { max-width: 100%; max-height: 100%; display: block }
.nc-res .liga .lg.inv { background: var(--nc-c) } .nc-res .liga .lg.inv img { filter: brightness(0) invert(1) }
.nc-res .liga b { font: 600 16px var(--display, system-ui); letter-spacing: .03em; text-transform: uppercase }
.nc-res .liga small { display: block; font: 500 12px var(--mono, monospace); color: var(--muted, #5c6079) }
.nc-res .liga .u { font: 700 18px var(--display, system-ui); text-align: right; white-space: nowrap } .nc-res .liga .u small { text-align: right }
.nc-res .bar { grid-column: 2 / 4; height: 6px; border-radius: 999px; background: var(--line, #dfe1ea); overflow: hidden; display: flex }
.nc-res .bar i { display: block; height: 100%; transform-origin: left; animation: nc-grow .6s cubic-bezier(.2,.7,.2,1) both } .nc-res .bar .g { background: var(--good, #00a346) } .nc-res .bar .p { background: var(--bad, #db052b) }
@keyframes nc-grow { from { transform: scaleX(0) } }
.nc-res .vacio { background: var(--surface, #fff); border: 1px dashed var(--line, #dfe1ea); border-radius: 14px; padding: 16px; color: var(--muted, #5c6079) }
.nc-res .vacio b { color: var(--ink, #10122a) }
.nc-res .acc { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; justify-content: space-between; background: var(--surface, #fff); border: 1px solid var(--line, #dfe1ea); border-radius: 14px; padding: 12px 14px }
.nc-res .acc p { margin: 0; color: var(--muted, #5c6079); font-size: 14px; flex: 1 1 240px }
@media (max-width: 420px) { .nc-kpi { grid-template-columns: repeat(2, minmax(0, 1fr)) } .nc-tira .go { margin-left: 0 } }
@media (prefers-reduced-motion: reduce) { dialog.nc-dlg[open], .nc-tira, .nc-res .tile, .nc-res .card, .nc-res .bar i { animation: none } .nc-res .curva .linea { animation: none; stroke-dashoffset: 0 } }`;

  /* ---------- 4. Supabase (se carga solo si hace falta) ---------- */
  const activo = !!(CFG.url && CFG.anon);
  let sb = null, sbP = null, USER = null, ULT = null, ESTADO = "", sincronizando = false, otraVez = false, tAg = null;
  // Enlace del correo: Supabase vuelve a esta página con #access_token=…&refresh_token=… (flujo implícito: sirve
  // aunque el enlace se abra en otro navegador, p. ej. el de la app de Gmail). Se lee y se borra del # antes de que la
  // página lo tome por una ruta (#partido, #mis-picks…). Si el enlace venció llega #error=…&error_description=….
  let TOK = null, TOKERR = "";
  try {
    const h = new URLSearchParams(location.hash.slice(1));
    if (h.get("access_token") && h.get("refresh_token")) TOK = { access_token: h.get("access_token"), refresh_token: h.get("refresh_token"), tipo: h.get("type") || "" };
    else if (h.get("error") || h.get("error_code")) TOKERR = h.get("error_description") || h.get("error") || "enlace no válido";
    if (TOK || TOKERR) history.replaceState(history.state, "", location.pathname + location.search);
  } catch (e) {}
  const hayCode = !!TOK;
  function cargar() {
    if (!activo) return Promise.resolve(null);
    if (sbP) return sbP;
    sbP = new Promise((ok, mal) => {
      if (window.supabase && window.supabase.createClient) return ok();
      const s = document.createElement("script"); s.src = SB_JS; s.async = true; s.onload = ok; s.onerror = () => mal(new Error("No se pudo cargar Supabase")); document.head.appendChild(s);
    }).then(() => {
      sb = window.supabase.createClient(CFG.url, CFG.anon, { auth: { flowType: "implicit", detectSessionInUrl: false, persistSession: true, autoRefreshToken: true, storageKey: "ncdp-auth" } });
      sb.auth.onAuthStateChange((ev, s) => {
        const u = s && s.user || null, antes = USER && USER.id;
        USER = u; pintarBtn();
        if (u && u.id !== antes) setTimeout(sincronizar, 0);
        if (ev === "SIGNED_OUT") { const m = jparse(get(META_K), {}); setRaw(META_K, JSON.stringify({ ...m, uid: null })); }
        pintarDlg();
      });
      return (TOK ? sb.auth.setSession({ access_token: TOK.access_token, refresh_token: TOK.refresh_token }) : Promise.resolve(null)).then(r => {
        if (TOK) {
          const rec = TOK.tipo === "recovery"; TOK = null;
          if (r && r.error) PASO = { fase: "mail", email: "", msg: traducir(r.error), err: true };
          else if (rec) PASO = { fase: "nueva", email: "", msg: "", recien: false, abrir: true };
          else PASO.recien = true;
        }
        return sb.auth.getSession();
      }).then(r => {
        USER = (r.data.session && r.data.session.user) || null;
        pintarBtn();
        if (PASO.recien || PASO.err || PASO.abrir) { PASO.abrir = false; abrir(); }
        return sb;
      });
    }).catch(e => { sbP = null; ESTADO = "err:" + e.message; pintarDlg(); return null; });
    return sbP;
  }
  const sesionGuardada = () => { try { return !!ST.getItem("ncdp-auth"); } catch (e) { return false; } };

  /* ---------- 5. sincronización ---------- */
  // Cada clave guarda en ncdp-sync la huella de lo último sincronizado (h) y la versión remota (rev). Si solo cambió
  // un lado, gana ese lado; si cambiaron los dos (o es la primera vez de esta cuenta en este navegador), se unen sin
  // duplicar (por key / k / cid). Lo derivado (ncdp-rend-*) no se une: lo recalcula cada liga.
  const idDe = x => x && (x.key || x.k || x.cid) || JSON.stringify(x);
  function unir(k, a, b) {
    if (k.startsWith("ncdp-rend-")) return (Array.isArray(a) && a.length ? a : b) || [];
    if (!Array.isArray(a)) return Array.isArray(b) ? b : a;
    if (!Array.isArray(b)) return a;
    const vistos = new Set(a.map(idDe));
    return a.concat(b.filter(x => !vistos.has(idDe(x))));
  }
  function agendar() { if (!USER) return; clearTimeout(tAg); tAg = setTimeout(sincronizar, 1200); }
  async function sincronizar() {
    if (!sb || !USER) return;
    if (sincronizando) { otraVez = true; return; }
    sincronizando = true; ESTADO = "sync"; pintarDlg();
    try {
      const uid = USER.id, meta = jparse(get(META_K), {}), nueva = meta.uid !== uid, M = nueva ? {} : (meta.claves || {});
      const r = await sb.from("ncdp_datos").select("clave, valor, actualizado");
      if (r.error) throw r.error;
      const REM = Object.fromEntries(r.data.filter(x => SYNC.has(x.clave)).map(x => [x.clave, x]));
      const subir = [], cambiadas = [];
      for (const k of SYNC) {
        const L = canon(get(k)), R = REM[k], Rv = R ? JSON.stringify(R.valor) : null, m = M[k] || {};
        const locSucio = L != null && hash(L) !== m.h, remNueva = !!R && R.actualizado !== m.rev;
        let fin = L;
        if (nueva || (locSucio && remNueva)) fin = L == null ? Rv : Rv == null ? L : JSON.stringify(unir(k, jparse(L), jparse(Rv)));
        else if (remNueva) fin = Rv;
        if (fin == null) continue;
        if (fin !== L) { setRaw(k, fin); cambiadas.push(k); }
        if (fin !== Rv) subir.push({ user_id: uid, clave: k, valor: JSON.parse(fin) });
        M[k] = { h: hash(fin), rev: R ? R.actualizado : null };
      }
      if (subir.length) {
        const w = await sb.from("ncdp_datos").upsert(subir, { onConflict: "user_id,clave" }).select("clave, actualizado");
        if (w.error) throw w.error;
        w.data.forEach(x => { if (M[x.clave]) M[x.clave].rev = x.actualizado; });
      }
      setRaw(META_K, JSON.stringify({ uid, claves: M, at: Date.now() }));
      ULT = Date.now(); ESTADO = "";
      if (cambiadas.length) {
        cambiadas.forEach(k => { try { dispatchEvent(new StorageEvent("storage", { key: k, newValue: get(k), storageArea: ST })); } catch (e) {} });
        dispatchEvent(new CustomEvent("ncdp-sync", { detail: { claves: cambiadas } }));
        avisar();
      }
    } catch (e) { ESTADO = "err:" + (e.message || e); }
    sincronizando = false; pintarDlg();
    if (otraVez) { otraVez = false; sincronizar(); }
  }
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible" && USER) sincronizar(); });

  /* ---------- 6. interfaz: botón, panel, franja de la liga, sección de la portada ---------- */
  let BTN = null, DLG = null, PASO = { fase: "mail", email: "", msg: "", err: false };
  const inicial = u => ((u && u.email) || "?").trim()[0];
  function pintarBtn() {
    if (!BTN) return;
    const on = !!USER;
    BTN.classList.toggle("on", on);
    const av = BTN.querySelector(".nc-av"); if (av) av.textContent = inicial(USER);
    const t = BTN.querySelector(".nc-t"); if (t) t.textContent = on ? "Cuenta" : "Entrar";
    const lbl = on ? `Tu cuenta (${USER.email})` : "Entrar o crear cuenta";
    BTN.setAttribute("aria-label", lbl); BTN.title = lbl;
  }
  function kpiHtml(s) {
    return `<div class="nc-kpi"><div><span>Unidades</span><b class="${cls(s.u)}">${fu(s.u)}</b></div><div><span>Gan.–perd.</span><b>${rec(s)}</b></div>
      <div><span>% acierto</span><b>${fp(s.pct)}</b></div><div><span>ROI</span><b class="${cls(s.roi)}">${froi(s.roi)}</b></div></div>`;
  }
  function hace(t) { const s = Math.round((Date.now() - t) / 1000); return s < 60 ? "hace un momento" : s < 3600 ? `hace ${Math.round(s / 60)} min` : `hace ${Math.round(s / 3600)} h`; }
  function pintarDlg() {
    if (!DLG || !DLG.open) return;
    const R = resumen(), aqui = LIGA && R.por[LIGA], L = LIGA && LIGAS[LIGA];
    const rendHtml = (aqui ? `<section><h3>${ICO.chart}Tus picks en ${esc(L.nombre)}</h3>${kpiHtml(aqui.s)}${aqui.s.pend ? `<p style="margin-top:6px">${aqui.s.pend} pendiente${aqui.s.pend > 1 ? "s" : ""} de resultado.</p>` : ""}</section>` : "")
      + (R.total.n ? `<section><h3>${ICO.chart}En todas las ligas</h3>${kpiHtml(R.total)}</section>` : `<p>Aún no guardaste picks. Toca <b>Lo tomo</b> en un pick para seguir su rendimiento.</p>`)
      + `<div class="nc-row">${LIGA ? `<a class="nc-b sec" href="#mis-picks" data-nc-close>Mis picks</a>` : ""}<a class="nc-b sec" href="/#tus-picks" data-nc-close>Rendimiento general</a></div>`;
    let auth;
    const bien = PASO.recien && USER ? `<div class="nc-msg">Listo, entraste. Tus picks de este navegador ya se están guardando en tu cuenta.</div>` : "";
    if (!activo) auth = `<div class="nc-off">El inicio de sesión se activa en cuanto el sitio tenga su cuenta de Supabase. Mientras tanto tus picks se guardan en este navegador.</div>`;
    else if (USER && PASO.fase === "nueva") {
      auth = `<section><h3>${ICO.cloud}${PASO.cambiar ? "Cambia tu contraseña" : "Crea tu nueva contraseña"}</h3><p>Con ella entras con <b>${esc(USER.email)}</b> en cualquier dispositivo, sin esperar correos. Mínimo 6 caracteres.</p>
        <form data-nc="nueva" class="nc-row" style="margin-top:10px"><input class="nc-in" type="password" name="p" autocomplete="new-password" minlength="6" required placeholder="Nueva contraseña" aria-label="Nueva contraseña"><button class="nc-b" type="submit">Guardar</button></form>
        ${PASO.msg ? `<div class="nc-msg${PASO.err ? " err" : ""}" style="margin-top:8px">${esc(PASO.msg)}</div>` : ""}
        <div class="nc-row" style="margin-top:8px"><button type="button" class="nc-b sec" data-nc="otro">Ahora no</button></div></section>`;
    } else if (USER) {
      const st = ESTADO === "sync" ? "Sincronizando…" : ESTADO.startsWith("err:") ? "No se pudo sincronizar: " + ESTADO.slice(4) : ULT ? "Sincronizado " + hace(ULT) : "Conectado";
      auth = `<section><h3>${ICO.cloud}Tu cuenta</h3><div class="nc-who"><span class="nc-av">${esc(inicial(USER))}</span><div><b>${esc(USER.email)}</b><small>${esc(st)}</small></div></div>
        <p style="margin-top:8px">Tus picks y combinadas de todas las ligas se guardan en tu cuenta: los ves en cualquier celular o computador donde entres.</p>
        <div class="nc-row" style="margin-top:10px"><button type="button" class="nc-b sec" data-nc="sync">Sincronizar ahora</button><button type="button" class="nc-b sec" data-nc="clave">Crear o cambiar contraseña</button><button type="button" class="nc-b sec" data-nc="salir">Cerrar sesión</button></div>
        ${PASO.msg ? `<div class="nc-msg${PASO.err ? " err" : ""}" style="margin-top:8px">${esc(PASO.msg)}</div>` : ""}</section>`;
    } else if (PASO.fase === "code") {
      auth = `<section><h3>${ICO.mail}Revisa tu correo</h3><p>Te enviamos un enlace a <b>${esc(PASO.email)}</b>. Ábrelo y vuelves a esta página ya con tu cuenta. Puede tardar un minuto; si no llega, mira en spam o promociones.</p>
        ${PASO.msg ? `<div class="nc-msg${PASO.err ? " err" : ""}" style="margin-top:8px">${esc(PASO.msg)}</div>` : ""}
        <div class="nc-row" style="margin-top:10px"><button type="button" class="nc-b sec" data-nc="reenviar">Enviar otra vez</button><button type="button" class="nc-b sec" data-nc="otro">Usar otro correo</button></div>
        <details class="nc-cod" style="margin-top:10px"><summary>¿Te llegó un código de 6 dígitos?</summary>
        <form data-nc="code" class="nc-row" style="margin-top:8px"><input class="nc-in code" name="t" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6,8}" maxlength="8" required aria-label="Código del correo" placeholder="000000"><button class="nc-b" type="submit">Entrar</button></form></details></section>`;
    } else {
      auth = `<section><h3>${ICO.cloud}Guarda tus picks en tu cuenta</h3><p>Entra y tus picks de todas las ligas te siguen a cualquier celular o computador. Lo que ya guardaste en este navegador se suma a tu cuenta.</p>
        <form data-nc="clave" class="nc-pw" style="margin-top:10px"><input class="nc-in" type="email" name="e" autocomplete="email" required placeholder="tu@correo.com" aria-label="Correo" value="${esc(PASO.email)}">
          <input class="nc-in" type="password" name="p" autocomplete="current-password" minlength="6" required placeholder="Contraseña" aria-label="Contraseña">
          <div class="nc-row"><button class="nc-b" type="submit" name="modo" value="entrar">Entrar</button><button class="nc-b sec" type="submit" name="modo" value="crear">Crear cuenta</button></div></form>
        ${PASO.msg ? `<div class="nc-msg${PASO.err ? " err" : ""}" style="margin-top:8px">${esc(PASO.msg)}</div>` : ""}
        <div class="nc-links"><button type="button" data-nc="olvide">Olvidé mi contraseña</button><button type="button" data-nc="enlace">Entrar sin contraseña (enlace al correo)</button></div>
        ${CFG.google ? `<div class="nc-row" style="margin-top:8px"><button type="button" class="nc-b sec" data-nc="google">Entrar con Google</button></div>` : ""}</section>`;
    }
    DLG.querySelector(".nc-bd").innerHTML = bien + auth + rendHtml;
  }
  function abrir() {
    if (!DLG) {
      DLG = document.createElement("dialog"); DLG.className = "nc-dlg"; DLG.setAttribute("aria-labelledby", "nc-t");
      DLG.innerHTML = `<div class="nc-hd"><h2 id="nc-t">Tu cuenta</h2><button type="button" class="nc-x" data-nc="cerrar" aria-label="Cerrar">✕</button></div><div class="nc-bd"></div>`;
      document.body.appendChild(DLG);
      DLG.addEventListener("click", async e => {
        if (e.target === DLG || e.target.closest("[data-nc-close]")) { DLG.close(); return; }
        const b = e.target.closest("button[data-nc]"); if (!b) return;
        const a = b.dataset.nc;
        if (a === "cerrar") { DLG.close(); PASO.recien = false; }
        else if (a === "reenviar") { b.disabled = true; await cargar(); if (sb) { const r = await sb.auth.signInWithOtp({ email: PASO.email, options: { emailRedirectTo: location.origin + location.pathname, shouldCreateUser: true } }); PASO = { ...PASO, msg: r.error ? traducir(r.error) : "Listo, te enviamos otro enlace.", err: !!r.error }; } pintarDlg(); }
        else if (a === "clave") { PASO = { fase: "nueva", email: "", msg: "", cambiar: true }; pintarDlg(); const i = DLG.querySelector(".nc-in"); if (i) i.focus(); }
        else if (a === "olvide" || a === "enlace") {
          const i = DLG.querySelector('input[name="e"]'), email = i && i.value.trim();
          if (!email || !i.checkValidity()) { PASO = { fase: "mail", email: email || "", msg: "Escribe primero tu correo arriba.", err: true }; pintarDlg(); return; }
          b.disabled = true; await cargar(); if (!sb) return;
          const vuelta = location.origin + location.pathname;
          const r = a === "olvide" ? await sb.auth.resetPasswordForEmail(email, { redirectTo: vuelta })
            : await sb.auth.signInWithOtp({ email, options: { emailRedirectTo: vuelta, shouldCreateUser: true } });
          PASO = r.error ? { fase: "mail", email, msg: traducir(r.error), err: true }
            : a === "olvide" ? { fase: "mail", email, msg: "Te enviamos un correo: ábrelo y aquí mismo creas tu contraseña nueva." } : { fase: "code", email, msg: "" };
          pintarDlg();
        }
        else if (a === "otro") { PASO = { fase: "mail", email: PASO.email, msg: "" }; pintarDlg(); }
        else if (a === "sync") sincronizar();
        else if (a === "salir") { await cargar(); if (sb) await sb.auth.signOut(); USER = null; pintarBtn(); pintarDlg(); }
        else if (a === "google") { await cargar(); if (sb) sb.auth.signInWithOAuth({ provider: "google", options: { redirectTo: location.origin + location.pathname } }); }
      });
      DLG.addEventListener("submit", async e => {
        e.preventDefault();
        const f = e.target, btn = f.querySelector("button"); btn.disabled = true;
        await cargar();
        if (!sb) { PASO.msg = "No se pudo conectar. Revisa tu internet e intenta otra vez."; PASO.err = true; pintarDlg(); return; }
        if (f.dataset.nc === "clave") {
          const email = f.e.value.trim(), password = f.p.value, crear = e.submitter && e.submitter.value === "crear";
          const r = crear ? await sb.auth.signUp({ email, password, options: { emailRedirectTo: location.origin + location.pathname } })
            : await sb.auth.signInWithPassword({ email, password });
          if (r.error) PASO = { fase: "mail", email, msg: traducir(r.error, crear), err: true };
          else if (crear && !r.data.session) PASO = { fase: "mail", email, msg: "Cuenta creada. Te enviamos un correo para confirmarla: ábrelo y vuelves aquí ya dentro." };
          else PASO = { fase: "mail", email: "", msg: "", recien: true };
        } else if (f.dataset.nc === "nueva") {
          const r = await sb.auth.updateUser({ password: f.p.value });
          PASO = r.error ? { ...PASO, msg: traducir(r.error), err: true } : { fase: "mail", email: "", msg: "Contraseña guardada. Desde ahora puedes entrar con tu correo y esa contraseña." };
        } else if (f.dataset.nc === "mail") {
          const email = f.e.value.trim();
          const r = await sb.auth.signInWithOtp({ email, options: { emailRedirectTo: location.origin + location.pathname, shouldCreateUser: true } });
          PASO = r.error ? { fase: "mail", email, msg: traducir(r.error), err: true } : { fase: "code", email, msg: "" };
        } else {
          const r = await sb.auth.verifyOtp({ email: PASO.email, token: f.t.value.trim(), type: "email" });
          if (r.error) PASO = { ...PASO, msg: traducir(r.error), err: true }; else PASO = { fase: "mail", email: "", msg: "" };
        }
        pintarDlg();
        const i = DLG.querySelector(".nc-in"); if (i && !USER) i.focus();
      });
    }
    DLG.showModal(); pintarDlg();
    if (activo && (sesionGuardada() || USER)) cargar();
    const i = DLG.querySelector(".nc-in"); if (i) i.focus();
  }
  function traducir(e, crear) {
    const m = String(e && e.message || e);
    if (/invalid login credentials/i.test(m)) return "Correo o contraseña incorrectos. Si antes entraste con el enlace del correo, toca \"Olvidé mi contraseña\" para crear una.";
    if (/already registered|already exists/i.test(m)) return "Ese correo ya tiene cuenta: toca Entrar (o \"Olvidé mi contraseña\" si no tiene contraseña).";
    if (/email not confirmed/i.test(m)) return "Falta confirmar tu correo: abre el correo que te enviamos al crear la cuenta.";
    if (/password/i.test(m) && /(short|least|weak|characters)/i.test(m)) return "La contraseña es muy corta o muy simple: usa al menos 6 caracteres.";
    if (/same.*password|different from the old/i.test(m)) return "Esa ya es tu contraseña actual: elige otra.";
    if (/rate limit|seconds/i.test(m)) return "Se pidieron muchos correos seguidos. Espera unos minutos e intenta otra vez.";
    if (/expired|invalid/i.test(m)) return "El enlace o el código ya no sirve (vence en una hora y se usa una sola vez). Pide uno nuevo.";
    if (/email/i.test(m)) return "Revisa el correo: parece que no es válido.";
    return "No se pudo: " + m;
  }

  // franja de la liga: <div data-ncdp-tira></div> en el inicio de cada liga
  function tiraHtml() {
    const R = resumen(), x = LIGA && R.por[LIGA], L = LIGA && LIGAS[LIGA];
    if (!x) return "";
    const s = x.s;
    return `<a class="nc-tira" href="#mis-picks" style="--nc-c:${L.c}"><span class="t">${ICO.chart}Tus picks en ${esc(L.nombre)}</span>
      <span class="m">${s.dec ? `<span><b>${rec(s)}</b> gan.–perd.</span><span>acierto <b>${fp(s.pct)}</b></span><span><b class="${cls(s.u)}">${fu(s.u)}</b></span><span>ROI <b class="${cls(s.roi)}">${froi(s.roi)}</b></span>` : ""}${s.pend ? `<span><b>${s.pend}</b> pendiente${s.pend > 1 ? "s" : ""}</span>` : ""}</span>
      <span class="go">Ver Mis picks →</span></a>`;
  }
  // curva de unidades acumuladas por día (todas las ligas)
  function curva(ps) {
    const dias = {}; ps.filter(x => (x.e === "g" || x.e === "p") && /^\d{4}-\d{2}-\d{2}$/.test(x.f)).forEach(x => { dias[x.f] = (dias[x.f] || 0) + x.u; });
    const ks = Object.keys(dias).sort(); if (ks.length < 2) return "";
    let c = 0; const pts = [{ d: null, y: 0 }].concat(ks.map(d => ({ d, y: c += dias[d] })));
    const W = Math.round(Math.min(900, Math.max(340, innerWidth - 64))), H = W < 600 ? 190 : 210, pl = 44, pr = 12, pt = 12, pb = 24, ys = pts.map(p => p.y), lo = Math.min(0, ...ys), hi = Math.max(0, ...ys), sp = hi - lo || 1;
    const X = i => pl + (W - pl - pr) * i / (pts.length - 1), Y = v => pt + (H - pt - pb) * (hi - v) / sp;
    const d = pts.map((p, i) => `${i ? "L" : "M"}${X(i).toFixed(1)} ${Y(p.y).toFixed(1)}`).join(""), fin = pts[pts.length - 1].y;
    let len = 0; for (let i = 1; i < pts.length; i++) len += Math.hypot(X(i) - X(i - 1), Y(pts[i].y) - Y(pts[i - 1].y));
    const col = fin >= 0 ? "var(--good, #00a346)" : "var(--bad, #db052b)", fd = s => s ? s.slice(8) + "/" + s.slice(5, 7) : "";
    const marcas = [0].concat([hi, lo].filter(v => Math.abs(v) > sp * .12));
    return `<div class="card"><h3>Unidades acumuladas</h3><p>Suma día a día de lo que ganaste o perdiste, 1 unidad por pick o combinada, en todas las ligas.</p>
      <svg class="curva" viewBox="0 0 ${W} ${H}" role="img" aria-label="Unidades acumuladas: ${fu(fin)} tras ${ks.length} días">
        ${marcas.map(v => `<line x1="${pl}" x2="${W - pr}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line, #dfe1ea)" ${v === 0 ? "" : 'stroke-dasharray="3 4"'}/><text x="${pl - 6}" y="${Y(v) + 4}" text-anchor="end">${v > 0 ? "+" : ""}${v.toFixed(1).replace(".", ",")}</text>`).join("")}
        <path class="linea" d="${d}" stroke="${col}" style="--len:${len.toFixed(0)}"/>
        <circle cx="${X(pts.length - 1)}" cy="${Y(fin)}" r="4.5" fill="${col}"/>
        <text x="${pl}" y="${H - 6}">${fd(ks[0])}</text><text x="${W - pr}" y="${H - 6}" text-anchor="end">${fd(ks[ks.length - 1])}</text>
      </svg></div>`;
  }
  function resumenHtml() {
    const R = resumen(), T = R.total, ids = Object.keys(R.por);
    const cuenta = !activo ? "" : USER
      ? `<div class="acc"><p>${ICO.cloud.replace("<svg", '<svg style="width:18px;height:18px;vertical-align:-4px;margin-right:6px"')}Sincronizado con <b>${esc(USER.email)}</b>: tus picks te siguen a cualquier dispositivo.</p><button type="button" class="nc-b sec" data-nc-abrir>Tu cuenta</button></div>`
      : `<div class="acc"><p>Tus picks se guardan solo en este navegador. Entra con tu correo para no perderlos y verlos en el celular y en el computador.</p><button type="button" class="nc-b" data-nc-abrir>Entrar</button></div>`;
    if (!T.n) return `<div class="vacio">Aún no guardaste picks. Entra a una liga y toca <b>Lo tomo</b> en los picks que juegues (o arma una combinada): aquí verás tu rendimiento en todas las ligas juntas, y en cada liga el suyo.</div>${cuenta}`;
    const tile = (t, v, c, sub, i) => `<div class="tile" style="animation-delay:${i * 60}ms"><span>${t}</span><b class="${c}">${v}</b><small>${sub}</small></div>`;
    const mx = Math.max(...ids.map(id => R.por[id].s.dec), 1);
    return `<div class="tiles">${tile("Unidades", fu(T.u), cls(T.u), "1 unidad por pick", 0)}${tile("Ganados–perdidos", rec(T), "", T.nulo ? "el 3.º son nulos" : `${T.dec} liquidados`, 1)}
      ${tile("% acierto", fp(T.pct, 1), "", "de los liquidados", 2)}${tile("ROI", froi(T.roi), cls(T.roi), "unidades / picks", 3)}${tile("Pendientes", String(T.pend), "", "esperan resultado", 4)}</div>
      ${curva(R.todos)}
      <div class="card"><h3>Por liga</h3><p>Toca una liga para ver el detalle de tus picks allí.</p><div class="ligas">${ids.map((id, i) => { const L = LIGAS[id], s = R.por[id].s;
        return `<a class="liga" href="${L.url}#mis-picks" style="--nc-c:${L.c};animation-delay:${i * 60}ms"><span class="lg${id === "champions" ? " inv" : ""}"><img src="${L.logo}" alt="" onerror="this.remove()"></span>
          <span><b>${esc(L.nombre)}</b><small>${rec(s)} · ${fp(s.pct)} acierto${s.pend ? ` · ${s.pend} pend.` : ""}</small></span>
          <span class="u ${cls(s.u)}">${fu(s.u)}<small>ROI ${froi(s.roi)}</small></span>
          <span class="bar" aria-hidden="true"><i class="g" style="width:${100 * s.g / mx}%"></i><i class="p" style="width:${100 * s.p / mx}%"></i></span></a>`; }).join("")}</div></div>${cuenta}`;
  }
  function pintarTodo() {
    document.querySelectorAll("[data-ncdp-tira]").forEach(el => { el.innerHTML = tiraHtml(); el.dataset.ncdpTira = "1"; });
    document.querySelectorAll("[data-ncdp-resumen]").forEach(el => { el.innerHTML = `<div class="nc-res">${resumenHtml()}</div>`; });
    pintarDlg();
  }

  function montar() {
    const st = document.createElement("style"); st.textContent = CSS; document.head.appendChild(st);
    BTN = document.getElementById("cuenta-btn");
    if (BTN) {
      if (!BTN.querySelector(".nc-ico")) BTN.insertAdjacentHTML("afterbegin", `<span class="nc-ico">${ICO.user}</span><span class="nc-av" aria-hidden="true"></span>`);
      BTN.hidden = false; BTN.addEventListener("click", abrir); pintarBtn();
    }
    document.addEventListener("click", e => { if (e.target.closest("[data-nc-abrir]")) abrir(); });
    // el inicio de cada liga se repinta solo: la franja aparece cuando se inserta su contenedor vacío
    new MutationObserver(() => { document.querySelectorAll("[data-ncdp-tira='']").forEach(el => { el.innerHTML = tiraHtml(); el.dataset.ncdpTira = "1"; }); })
      .observe(document.body, { childList: true, subtree: true });
    pintarTodo();
    if (TOKERR) { PASO = { fase: "mail", email: "", msg: traducir(TOKERR), err: true }; abrir(); }
    if (activo && (sesionGuardada() || hayCode)) cargar();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", montar); else montar();

  window.NCDP = { rend, resumen, abrir, sincronizar, alCambiar: f => oyentes.add(f), get usuario() { return USER; }, LIGAS };
})();
