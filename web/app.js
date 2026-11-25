/* Iron Coach · frontend.
 * Modo "vivo": habla con la API (/api/chat) y pinta las trazas de los agentes.
 * Modo "demo": sin servidor (p. ej. GitHub Pages), reproduce conversaciones pregrabadas.
 */

const $ = (selector) => document.querySelector(selector);

const SUGERENCIAS = [
  "Soy hombre, peso 80 kg, mido 180 cm y tengo 25 años. Entreno 4 días a la semana. ¿Cuántas calorías y macros necesito para ganar músculo?",
  "¿Cuántas series por semana necesito para el pecho y cuánto debo descansar entre series?",
  "Hago 100 kg x 5 repeticiones en press banca. ¿Cuál es mi 1RM estimado y qué discos pongo para 100 kg?",
  "¿Cuánta creatina tengo que tomar y hace falta hacer fase de carga?",
  "Llevo 3 semanas durmiendo mal y no progreso. ¿Qué hago?",
];

const NODOS = ["supervisor", "documentalista", "calculadora", "responder"];

let modo = "cargando"; // "vivo" | "demo" | "error"
let demo = [];
let historial = [];
let ocupado = false;
let nodoActivo = null;

/* ---------------------------------------------------------------- utilidades */

const dormir = (ms) => new Promise((r) => setTimeout(r, ms));

function escapar(texto) {
  return texto
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function inline(texto) {
  return escapar(texto)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`(.+?)`/g, "<code>$1</code>");
}

/** Markdown mínimo y seguro: negritas, código, listas y párrafos. */
function markdown(texto) {
  const lineas = texto.split("\n");
  let html = "";
  let enLista = false;
  let parrafo = [];
  const cerrarParrafo = () => {
    if (parrafo.length) html += "<p>" + parrafo.map(inline).join("<br>") + "</p>";
    parrafo = [];
  };
  for (const linea of lineas) {
    const item = linea.match(/^\s*(?:[-*•]|\d+\.)\s+(.*)$/);
    if (item) {
      cerrarParrafo();
      if (!enLista) { html += "<ul>"; enLista = true; }
      html += "<li>" + inline(item[1]) + "</li>";
    } else {
      if (enLista) { html += "</ul>"; enLista = false; }
      if (linea.trim() === "") cerrarParrafo(); else parrafo.push(linea);
    }
  }
  cerrarParrafo();
  if (enLista) html += "</ul>";
  return html;
}

function el(etiqueta, clase, texto) {
  const nodo = document.createElement(etiqueta);
  if (clase) nodo.className = clase;
  if (texto !== undefined) nodo.textContent = texto;
  return nodo;
}

/* ------------------------------------------------------------------- chat */

function bajarChat() {
  const caja = $("#mensajes");
  caja.scrollTop = caja.scrollHeight;
}

function añadirMensaje(quien, texto) {
  const fila = el("div", "msg " + quien);
  const burbuja = el("div", "burbuja");
  if (quien === "user") burbuja.textContent = texto;
  else burbuja.innerHTML = markdown(texto);
  fila.appendChild(burbuja);
  $("#mensajes").appendChild(fila);
  bajarChat();
  return burbuja;
}

function añadirPensando() {
  const fila = el("div", "msg bot");
  const burbuja = el("div", "burbuja");
  burbuja.innerHTML = '<span class="pensando" aria-label="Pensando"><i></i><i></i><i></i></span>';
  fila.appendChild(burbuja);
  $("#mensajes").appendChild(fila);
  bajarChat();
  return { fila, burbuja };
}

async function escribirRespuesta(burbuja, texto) {
  const palabras = texto.split(/(\s+)/);
  let acumulado = "";
  for (let i = 0; i < palabras.length; i++) {
    acumulado += palabras[i];
    if (i % 3 === 0 || i === palabras.length - 1) {
      burbuja.innerHTML = markdown(acumulado);
      bajarChat();
      await dormir(18);
    }
  }
  burbuja.innerHTML = markdown(texto);
  bajarChat();
}

/* ------------------------------------------------------- sala de máquinas */

function reiniciarPipeline() {
  nodoActivo = null;
  document.querySelectorAll("#pipeline li").forEach((li) => li.classList.remove("activo", "hecho"));
}

function activar(nodo) {
  if (nodoActivo && nodoActivo !== nodo) {
    const previo = document.querySelector(`#pipeline li[data-nodo="${nodoActivo}"]`);
    previo?.classList.remove("activo");
    previo?.classList.add("hecho");
  }
  const actual = document.querySelector(`#pipeline li[data-nodo="${nodo}"]`);
  actual?.classList.remove("hecho");
  actual?.classList.add("activo");
  nodoActivo = nodo;
}

function terminarPipeline() {
  const actual = document.querySelector(`#pipeline li[data-nodo="${nodoActivo}"]`);
  actual?.classList.remove("activo");
  actual?.classList.add("hecho");
}

function limpiarRegistro() {
  $("#registro").replaceChildren();
}

function añadirRegistro(clase, quien, contenido) {
  const entrada = el("div", "entrada-log " + clase);
  entrada.appendChild(el("div", "quien", quien));
  entrada.appendChild(contenido);
  $("#registro").appendChild(entrada);
  $("#registro").scrollTop = $("#registro").scrollHeight;
  return entrada;
}

const NOMBRES = { documentalista: "Documentalista", calculadora: "Calculadora", supervisor: "Supervisor", verificar: "Verificador" };

function formatearArgs(args) {
  const partes = Object.entries(args || {}).map(([k, v]) => `${k}=${JSON.stringify(v)}`);
  return partes.join(", ");
}

/* ----------------------------------------------------- eventos del sistema */

let burbujaPensando = null;

async function procesar(evento) {
  switch (evento.tipo) {
    case "inicio":
      activar("supervisor");
      break;

    case "supervisor": {
      if (evento.siguiente === "FIN") activar("responder");
      else activar(evento.siguiente);
      const cuerpo = el("div");
      if (evento.siguiente === "FIN") {
        cuerpo.textContent = "Ya hay información suficiente: pasa a redactar la respuesta.";
      } else {
        const destino = el("code", null, "→ " + NOMBRES[evento.siguiente]);
        cuerpo.appendChild(destino);
        cuerpo.appendChild(el("div", null, evento.tarea));
      }
      añadirRegistro("sup", "Supervisor", cuerpo);
      break;
    }

    case "herramienta": {
      const cuerpo = el("div");
      cuerpo.appendChild(el("code", null, `${evento.herramienta}(${formatearArgs(evento.args)})`));
      añadirRegistro("herr", NOMBRES[evento.agente] || evento.agente, cuerpo);
      break;
    }

    case "resultado": {
      const cuerpo = el("div");
      cuerpo.appendChild(el("code", null, `${evento.herramienta} → resultado`));
      if (evento.fuentes && evento.fuentes.length) {
        const fuentes = el("div", "fuentes");
        evento.fuentes.forEach((f) => fuentes.appendChild(el("span", null, "📄 " + f)));
        cuerpo.appendChild(fuentes);
      }
      cuerpo.appendChild(el("pre", null, evento.resultado));
      añadirRegistro("res", NOMBRES[evento.agente] || evento.agente, cuerpo);
      break;
    }

    case "redactado":
      activar("verificar");
      break;

    case "verificacion": {
      activar("verificar");
      const cuerpo = el("div");
      if (evento.fallida) {
        cuerpo.textContent = "⚠ No se pudo completar la verificación de esta respuesta.";
      } else if (evento.omitida) {
        cuerpo.textContent = "Sin información que contrastar: no hace falta verificar.";
      } else if (evento.sin_respaldo.length === 0) {
        cuerpo.textContent = "✓ Todo lo que dice la respuesta tiene respaldo en lo encontrado.";
      } else {
        cuerpo.appendChild(el("code", null, `Eliminado: ${evento.sin_respaldo.length} dato(s) sin respaldo`));
        const lista = el("ul");
        evento.sin_respaldo.forEach((t) => lista.appendChild(el("li", null, t)));
        cuerpo.appendChild(lista);
      }
      añadirRegistro("res", "Verificador", cuerpo);
      break;
    }

    case "respuesta": {
      terminarPipeline();
      burbujaPensando?.fila.remove();
      burbujaPensando = null;
      const burbuja = añadirMensaje("bot", "");
      await escribirRespuesta(burbuja, evento.texto);
      historial.push({ rol: "asistente", texto: evento.texto });
      break;
    }

    case "error":
      throw new Error(evento.mensaje);
  }
}

/* ------------------------------------------------------------- modo vivo */

async function consultarVivo(texto) {
  const respuesta = await fetch("api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mensaje: texto, historial: historial.slice(-6) }),
  });
  if (!respuesta.ok) {
    let detalle = "No se pudo contactar con el servidor.";
    try { detalle = (await respuesta.json()).error || detalle; } catch (_) {}
    throw new Error(detalle);
  }
  const lector = respuesta.body.getReader();
  const decodificador = new TextDecoder();
  let resto = "";
  while (true) {
    const { done, value } = await lector.read();
    if (done) break;
    resto += decodificador.decode(value, { stream: true });
    const lineas = resto.split("\n");
    resto = lineas.pop();
    for (const linea of lineas) {
      if (linea.trim()) await procesar(JSON.parse(linea));
    }
  }
}

/* ------------------------------------------------------------- modo demo */

async function reproducirDemo(texto) {
  const caso = demo.find((d) => d.pregunta === texto);
  if (!caso) throw new Error("En modo demo solo están disponibles las preguntas de ejemplo.");
  for (const evento of caso.eventos) {
    await dormir(evento.tipo === "respuesta" ? 500 : 650);
    await procesar(evento);
  }
}

/* ----------------------------------------------------------------- envío */

function bloquear(valor) {
  $("#enviar").disabled = valor || modo === "demo" || modo === "error";
  $("#texto").disabled = valor || modo === "demo" || modo === "error";
  document.querySelectorAll("#sugerencias button").forEach((b) => (b.disabled = valor || modo === "error"));
}

async function enviar(texto) {
  texto = texto.trim();
  if (!texto || ocupado || modo === "error") return;
  ocupado = true;
  bloquear(true);
  añadirMensaje("user", texto);
  historial.push({ rol: "usuario", texto });
  reiniciarPipeline();
  limpiarRegistro();
  burbujaPensando = añadirPensando();
  try {
    if (modo === "demo") {
      activar("supervisor");
      await reproducirDemo(texto);
    } else {
      await consultarVivo(texto);
    }
  } catch (e) {
    burbujaPensando?.fila.remove();
    burbujaPensando = null;
    historial.pop();
    const burbuja = añadirMensaje("bot", "");
    burbuja.classList.add("error");
    burbuja.textContent = "⚠️ " + e.message;
  } finally {
    ocupado = false;
    bloquear(false);
    if (modo === "vivo") $("#texto").focus();
  }
}

/* --------------------------------------------------------------- arranque */

async function detectarModo() {
  try {
    const control = new AbortController();
    const temporizador = setTimeout(() => control.abort(), 4000);
    const r = await fetch("api/health", { signal: control.signal });
    clearTimeout(temporizador);
    const tipo = r.headers.get("content-type") || "";
    if (r.ok && tipo.includes("json")) {
      const datos = await r.json();
      if (datos.ok) return { modo: "vivo" };
      return { modo: "error", mensaje: datos.error };
    }
  } catch (_) { /* sin API: modo demo */ }
  return { modo: "demo" };
}

function mostrarAviso(texto, clase, enlace) {
  const aviso = $("#aviso");
  aviso.className = "aviso" + (clase ? " " + clase : "");
  aviso.textContent = texto;
  if (enlace) {
    const a = el("a", null, enlace.texto);
    a.href = enlace.url;
    a.target = "_blank";
    a.rel = "noopener";
    aviso.append(" ", a);
  }
  aviso.hidden = false;
}

function pintarSugerencias(lista) {
  const caja = $("#sugerencias");
  caja.replaceChildren();
  lista.forEach((texto) => {
    const boton = el("button", null, texto.length > 70 ? texto.slice(0, 67) + "…" : texto);
    boton.type = "button";
    boton.title = texto;
    boton.addEventListener("click", () => enviar(texto));
    caja.appendChild(boton);
  });
}

async function iniciar() {
  const cfg = window.IRON_CONFIG || {};
  if (cfg.REPO_URL) $("#enlace-repo").href = cfg.REPO_URL; else $("#enlace-repo").hidden = true;
  if (cfg.LIVE_URL) {
    $("#enlace-vivo").href = cfg.LIVE_URL;
    $("#enlace-vivo").hidden = false;
    $("#enlace-vivo-sep").hidden = !cfg.REPO_URL;
  }

  $("#formulario").addEventListener("submit", (e) => {
    e.preventDefault();
    const texto = $("#texto").value;
    $("#texto").value = "";
    enviar(texto);
  });

  const deteccion = await detectarModo();
  modo = deteccion.modo;

  if (modo === "vivo") {
    pintarSugerencias(SUGERENCIAS);
  } else if (modo === "demo") {
    try {
      demo = await (await fetch("demo.json")).json();
    } catch (_) { demo = []; }
    pintarSugerencias(demo.map((d) => d.pregunta));
    $("#texto").placeholder = "Modo demo: elige una pregunta de ejemplo";
    mostrarAviso(
      "Modo demo: estas conversaciones están pregrabadas. Para preguntar lo que quieras, usa la versión en vivo o ejecútalo en local.",
      "",
      cfg.LIVE_URL ? { texto: "Abrir versión en vivo", url: cfg.LIVE_URL } : null
    );
  } else {
    pintarSugerencias(SUGERENCIAS);
    mostrarAviso("El servidor está en marcha, pero el modelo no está configurado: " + (deteccion.mensaje || ""), "error");
  }
  bloquear(false);

  // ?auto reproduce la primera conversación de la demo (para capturas del README)
  if (modo === "demo" && demo.length && new URLSearchParams(location.search).has("auto")) {
    enviar(demo[0].pregunta);
  }
}

iniciar();
