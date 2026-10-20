/* Tablero de analítica del admin (20-10-2026), dibujado con Apache ECharts
 * (static/admin/vendor, Apache-2.0, servido desde acá: sin CDN).
 *
 * Los datos los deja el servidor en <script id="tablero-datos"> (conteo.tablero):
 * por día, desde el primer dato, cada evento, las compras, lo cobrado por moneda
 * y la procedencia. Acá se elige el período y se dibuja. El HTML propio se arma
 * con textContent; los textos que ECharts muestra en tooltips pasan por
 * `esc()`, porque ECharts los interpreta como HTML.
 */
(function () {
  "use strict";

  const raiz = document.getElementById("tablero");
  const fuente = document.getElementById("tablero-datos");
  if (!raiz || !fuente || typeof echarts === "undefined") return;
  const D = JSON.parse(fuente.textContent);
  const NOMBRES = JSON.parse((document.getElementById("tablero-nombres") || {}).textContent || "{}");
  const N = D.fechas.length;
  const ULTIMO = N - 1;

  // --- utilidades -----------------------------------------------------------

  function el(tag, attrs, ...hijos) {
    const nodo = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === "class") nodo.className = v;
      else if (k.startsWith("on")) nodo.addEventListener(k.slice(2), v);
      else if (v !== false && v != null) nodo.setAttribute(k, v === true ? "" : v);
    }
    for (const h of hijos.flat()) {
      if (h == null || h === false) continue;
      nodo.append(h instanceof Node ? h : document.createTextNode(String(h)));
    }
    return nodo;
  }

  const esc = (s) =>
    String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const fmt = new Intl.NumberFormat("es-AR");
  const pct = (a, b) => (b > 0 ? `${(Math.round((a / b) * 1000) / 10).toLocaleString("es-AR")}%` : "—");
  const cero = () => new Array(N).fill(0);
  const serie = (clave) => D.eventos[clave] || cero();
  const suma = (valores, desde, hasta) => {
    let total = 0;
    for (let i = Math.max(0, desde); i <= hasta && i < valores.length; i++) total += valores[i] || 0;
    return total;
  };
  const sumaSeries = (...claves) => {
    const out = cero();
    for (const c of claves) serie(c).forEach((v, i) => (out[i] += v));
    return out;
  };

  const DIAS_SEMANA = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
  function etiquetaDia(iso, larga) {
    const [a, m, d] = iso.split("-").map(Number);
    const fecha = new Date(Date.UTC(a, m - 1, d));
    return larga ? `${DIAS_SEMANA[fecha.getUTCDay()]} ${d}/${m}/${a}` : `${d}/${m}`;
  }

  const region = (idioma) => {
    try {
      return new Intl.DisplayNames([idioma], { type: "region" });
    } catch (e) {
      return null;
    }
  };
  const regionEs = region("es");
  const regionEn = region("en");
  const esPais = (c) => /^[A-Z]{2}$/.test(c);
  const nombreEn = (dn, c) => {
    try {
      return (dn && dn.of(c)) || c;
    } catch (e) {
      return c;
    }
  };
  const nombrePais = (c) => (esPais(c) ? nombreEn(regionEs, c) : "Desconocido");
  const bandera = (c) => (esPais(c) ? String.fromCodePoint(...[...c].map((x) => 0x1f1a5 + x.charCodeAt(0))) : "🌐");
  // Los nombres del mapa (echarts 4.9 world.json) que no son los de Intl en inglés.
  const MAPA_NOMBRE = {
    EH: "W. Sahara", AX: "Aland", TF: "Fr. S. Antarctic Lands", AG: "Antigua and Barb.", BA: "Bosnia and Herz.",
    CF: "Central African Rep.", CI: "Côte d'Ivoire", CD: "Dem. Rep. Congo", CG: "Congo", KY: "Cayman Is.",
    CZ: "Czech Rep.", DO: "Dominican Rep.", FK: "Falkland Is.", FO: "Faeroe Is.", GQ: "Eq. Guinea",
    HM: "Heard I. and McDonald Is.", IO: "Br. Indian Ocean Ter.", KR: "Korea", LA: "Lao PDR", LC: "Saint Lucia",
    MK: "Macedonia", MM: "Myanmar", MP: "N. Mariana Is.", KP: "Dem. Rep. Korea", PS: "Palestine",
    PF: "Fr. Polynesia", SS: "S. Sudan", GS: "S. Geo. and S. Sandw. Is.", SH: "Saint Helena", SB: "Solomon Is.",
    PM: "St. Pierre and Miquelon", ST: "São Tomé and Principe", SZ: "Swaziland", TC: "Turks and Caicos Is.",
    TT: "Trinidad and Tobago", TR: "Turkey", VC: "St. Vin. and Gren.", VI: "U.S. Virgin Is.",
  };
  const nombreMapa = (c) => MAPA_NOMBRE[c] || nombreEn(regionEn, c);

  const MONEDAS = { usd: ["US$", "en-US"], brl: ["R$", "pt-BR"], ars: ["$", "es-AR"] };
  function dinero(centavos, moneda) {
    const [simbolo, locale] = MONEDAS[moneda] || [String(moneda).toUpperCase(), "es-AR"];
    const n = new Intl.NumberFormat(locale, {
      minimumFractionDigits: centavos % 100 ? 2 : 0,
      maximumFractionDigits: 2,
    }).format(centavos / 100);
    return `${simbolo} ${n}`;
  }

  // --- tema: el del admin (claro, oscuro o el del sistema) --------------------

  function oscuro() {
    const tema = document.documentElement.dataset.theme;
    if (tema === "dark") return true;
    if (tema === "light") return false;
    return Boolean(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
  }
  const COLORES = ["#5b8ff9", "#5ad8a6", "#f6bd16", "#e8684a", "#9270ca", "#6dc8ec", "#ff9d4d", "#269a99"];

  // --- estado -----------------------------------------------------------------

  const PERIODOS = [
    ["hoy", "Hoy", () => [ULTIMO, ULTIMO]],
    ["ayer", "Ayer", () => [ULTIMO - 1, ULTIMO - 1]],
    ["7", "7 días", () => [ULTIMO - 6, ULTIMO]],
    ["30", "30 días", () => [ULTIMO - 29, ULTIMO]],
    ["todo", "Todo", () => [0, ULTIMO]],
  ];
  const leer = (k) => {
    try {
      return localStorage.getItem(k);
    } catch (e) {
      return null;
    }
  };
  const guardar = (k, v) => {
    try {
      localStorage.setItem(k, v);
    } catch (e) {
      /* sin almacenamiento: no se recuerda */
    }
  };
  const estado = {
    periodo: PERIODOS.some((p) => p[0] === leer("tablero.periodo")) ? leer("tablero.periodo") : "7",
    desde: null,
    mapa: "visita_pais",
  };

  /** [desde, hasta, pedido]: `pedido` es el desde que se quería, para avisar
   *  si los datos no llegan tan atrás. `null` si el período no tiene días. */
  function rango() {
    if (estado.periodo === "desde" && estado.desde) {
      const i = D.fechas.findIndex((f) => f >= estado.desde);
      return i < 0 ? null : [i, ULTIMO, i];
    }
    const p = PERIODOS.find((x) => x[0] === estado.periodo) || PERIODOS[2];
    const [a, b] = p[2]();
    if (b < 0) return null;
    return [Math.max(0, a), b, a];
  }

  let graficos = [];
  function grafico(nodo, opciones) {
    const g = echarts.init(nodo, oscuro() ? "dark" : null, { renderer: "canvas" });
    g.setOption({ backgroundColor: "transparent", color: COLORES, textStyle: { fontFamily: "inherit" }, ...opciones });
    graficos.push(g);
    return g;
  }
  window.addEventListener("resize", () => graficos.forEach((g) => g.resize()));
  // Dibuja cuando el nodo ya está en la página y tiene tamaño.
  const despues = (f) => requestAnimationFrame(f);

  // --- piezas -----------------------------------------------------------------

  function selectorPeriodo() {
    const botones = PERIODOS.map(([clave, texto]) =>
      el(
        "button",
        {
          type: "button",
          class: "tbChip" + (estado.periodo === clave ? " tbChipOn" : ""),
          "aria-pressed": estado.periodo === clave ? "true" : "false",
          onclick: () => {
            estado.periodo = clave;
            guardar("tablero.periodo", clave);
            dibujar();
          },
        },
        texto,
      ),
    );
    const fecha = el("input", {
      type: "date",
      class: "tbFecha",
      min: D.fechas[0],
      max: D.fechas[ULTIMO],
      value: estado.periodo === "desde" && estado.desde ? estado.desde : "",
      "aria-label": "Desde una fecha",
      onchange: (e) => {
        if (!e.target.value) return;
        estado.periodo = "desde";
        estado.desde = e.target.value;
        dibujar();
      },
    });
    return el("div", { class: "tbPeriodo" }, ...botones, el("label", { class: "tbDesde" }, "desde ", fecha));
  }

  /** La variación contra el período anterior, sólo con días completos: hoy
   *  está a medias y compararlo con un día entero siempre da una caída. */
  function variacion(valores, desde, hasta) {
    const fin = hasta === ULTIMO ? hasta - 1 : hasta;
    if (fin < desde) return el("span", { class: "tbDelta" }, "hoy está incompleto");
    const largo = fin - desde + 1;
    if (desde - largo < 0) return el("span", { class: "tbDelta" }, "sin período anterior para comparar");
    const actual = suma(valores, desde, fin);
    const previo = suma(valores, desde - largo, desde - 1);
    const sufijo = hasta === ULTIMO ? " (sin hoy)" : "";
    if (previo === 0) return el("span", { class: "tbDelta" }, `antes 0${sufijo}`);
    const cambio = Math.round(((actual - previo) / previo) * 100);
    return el(
      "span",
      { class: "tbDelta " + (cambio >= 0 ? "tbSube" : "tbBaja") },
      `${cambio >= 0 ? "▲" : "▼"} ${Math.abs(cambio)}% vs. anterior${sufijo}`,
    );
  }

  function tarjeta(titulo, valores, desde, hasta, color, extra) {
    const chispa = el("div", { class: "tbChispa" });
    const nodo = el(
      "div",
      { class: "tbTarjeta" },
      el("div", { class: "tbTarjetaTitulo" }, titulo),
      el("div", { class: "tbTarjetaValor" }, fmt.format(suma(valores, desde, hasta))),
      variacion(valores, desde, hasta),
      extra || null,
      chispa,
    );
    despues(() =>
      grafico(chispa, {
        grid: { left: 0, right: 0, top: 4, bottom: 0 },
        xAxis: { type: "category", show: false, boundaryGap: false, data: D.fechas.slice(desde, hasta + 1) },
        yAxis: { type: "value", show: false },
        tooltip: {
          trigger: "axis",
          formatter: (p) => `${esc(etiquetaDia(p[0].name, true))}<br><b>${fmt.format(p[0].value)}</b>`,
        },
        series: [{
          type: "line", smooth: true, symbol: "none", data: valores.slice(desde, hasta + 1),
          lineStyle: { width: 2, color }, areaStyle: { color, opacity: 0.18 },
        }],
      }),
    );
    return nodo;
  }

  function tarjetas(desde, hasta) {
    const cobrado = Object.entries(D.ingresos || {})
      .map(([moneda, valores]) => [moneda, suma(valores, desde, hasta)])
      .filter(([, v]) => v > 0);
    return el(
      "div",
      { class: "tbTarjetas" },
      tarjeta("Visitas (páginas)", serie("visita"), desde, hasta, COLORES[0]),
      tarjeta("Cartas calculadas", serie("carta_calculada"), desde, hasta, COLORES[1]),
      tarjeta("Clic en comprar", sumaSeries("teaser_clic_arriba", "teaser_clic_cierre"), desde, hasta, COLORES[2]),
      tarjeta("Pagos abiertos", serie("checkout_abierto"), desde, hasta, COLORES[3]),
      tarjeta(
        "Compras pagas",
        serie("compra_pagada"),
        desde,
        hasta,
        COLORES[4],
        el("div", { class: "tbCobrado" }, cobrado.length ? cobrado.map(([m, v]) => dinero(v, m)).join(" · ") : "sin cobros"),
      ),
    );
  }

  function bloque(titulo, alto, clase) {
    const lienzo = el("div", { class: "tbLienzo", style: `height:${alto}px` });
    return [el("section", { class: "tbBloque " + (clase || "") }, el("h2", {}, titulo), lienzo), lienzo];
  }

  function embudo(desde, hasta) {
    const s = (c) => suma(serie(c), desde, hasta);
    const pasos = [
      ["Visitas (páginas)", s("visita"), "Cada página abierta en el sitio."],
      ["Cartas calculadas", s("carta_calculada"), "Con y sin cuenta."],
      ["Llegó al final", s("teaser_cierre_visto"), "Del adelanto sin cuenta, una vez por carta."],
      [
        "Apretó comprar",
        s("teaser_clic_arriba") + s("teaser_clic_cierre"),
        `${fmt.format(s("teaser_clic_arriba"))} arriba + ${fmt.format(s("teaser_clic_cierre"))} al final · ` +
          `ARS ${fmt.format(s("teaser_clic_ars"))} · USD ${fmt.format(s("teaser_clic_usd"))} · BRL ${fmt.format(s("teaser_clic_brl"))}`,
      ],
      ["Dejó el mail", s("teaser_mail_enviado"), "Sólo lo pide el pago en pesos."],
      ["Pago abierto", s("checkout_abierto"), "Con y sin cuenta, todas las monedas."],
      ["Compra paga", s("compra_pagada"), "Sin reembolsos, disputas ni canjes de cupón del 100 %."],
    ];
    const [seccion, lienzo] = bloque("Embudo", 330, "tbAncho");
    seccion.append(
      el(
        "p",
        { class: "tbNota" },
        `Abrió los datos de la carta: ${fmt.format(s("teaser_datos_abiertos"))} · ` +
          `Volvió a corregir fecha, hora o lugar: ${fmt.format(s("teaser_volver"))}. ` +
          "Veces, no personas. Pasá el mouse por cada paso.",
      ),
    );
    despues(() =>
      grafico(lienzo, {
        grid: { left: 150, right: 130, top: 8, bottom: 8 },
        xAxis: { type: "value", show: false },
        yAxis: {
          type: "category", inverse: true, data: pasos.map((p) => p[0]),
          axisTick: { show: false }, axisLine: { show: false }, axisLabel: { fontSize: 13 },
        },
        tooltip: {
          trigger: "item",
          formatter: (p) => {
            const i = p.dataIndex;
            const [nombre, valor, nota] = pasos[i];
            const previo = i > 0 ? `<br>${pct(valor, pasos[i - 1][1])} del paso anterior` : "";
            const total = i > 0 ? `<br>${pct(valor, pasos[0][1])} de las visitas` : "";
            return `<b>${esc(nombre)}: ${fmt.format(valor)}</b>${previo}${total}<br><span style="opacity:.7">${esc(nota)}</span>`;
          },
        },
        series: [{
          type: "bar", barWidth: "62%",
          data: pasos.map((p, i) => ({ value: p[1], itemStyle: { color: COLORES[i % COLORES.length], borderRadius: [0, 6, 6, 0] } })),
          label: {
            show: true, position: "right", fontSize: 13,
            formatter: (p) => (p.dataIndex === 0 ? fmt.format(p.value) : `${fmt.format(p.value)}  ·  ${pct(p.value, pasos[p.dataIndex - 1][1])}`),
          },
        }],
      }),
    );
    return seccion;
  }

  function porDia(desde, hasta) {
    const fechas = D.fechas.slice(desde, hasta + 1);
    const corte = (v) => v.slice(desde, hasta + 1);
    const lineas = [
      ["Visitas", serie("visita"), 0],
      ["Cartas", serie("carta_calculada"), 0],
      ["Clic en comprar", sumaSeries("teaser_clic_arriba", "teaser_clic_cierre"), 1],
      ["Pagos abiertos", serie("checkout_abierto"), 1],
      ["Compras", serie("compra_pagada"), 1],
    ];
    const [seccion, lienzo] = bloque("Por día", 360, "tbAncho");
    seccion.append(
      el("p", { class: "tbNota" }, "Días en UTC; el último es hoy, incompleto. Prendé y apagá series en la leyenda. Eje derecho: clics, pagos y compras."),
    );
    despues(() =>
      grafico(lienzo, {
        legend: { top: 0 },
        grid: { left: 48, right: 48, top: 40, bottom: fechas.length > 14 ? 60 : 30 },
        tooltip: {
          trigger: "axis",
          formatter: (ps) =>
            `<b>${esc(etiquetaDia(ps[0].axisValue, true))}${ps[0].axisValue === D.fechas[ULTIMO] ? " (hoy, parcial)" : ""}</b><br>` +
            ps.map((p) => `${p.marker} ${esc(p.seriesName)}: <b>${fmt.format(p.value)}</b>`).join("<br>"),
        },
        xAxis: { type: "category", data: fechas, axisLabel: { formatter: (v) => etiquetaDia(v, false) } },
        yAxis: [
          { type: "value", minInterval: 1, splitLine: { lineStyle: { opacity: 0.25 } } },
          { type: "value", minInterval: 1, splitLine: { show: false } },
        ],
        dataZoom: fechas.length > 14 ? [{ type: "inside" }, { type: "slider", height: 18, bottom: 8 }] : [],
        series: lineas.map(([nombre, valores, eje], i) => ({
          name: nombre, type: eje === 0 ? "line" : "bar", yAxisIndex: eje, data: corte(valores),
          smooth: true, symbolSize: 6, barMaxWidth: 18,
          areaStyle: eje === 0 ? { opacity: 0.12 } : undefined,
          itemStyle: { color: COLORES[i], borderRadius: eje === 1 ? [4, 4, 0, 0] : 0 },
        })),
      }),
    );
    return seccion;
  }

  function filasDe(tipo, desde, hasta) {
    const valores = (D.procedencia || {})[tipo] || {};
    return Object.entries(valores)
      .map(([valor, s]) => [valor, suma(s, desde, hasta)])
      .filter(([, v]) => v > 0)
      .sort((a, b) => b[1] - a[1]);
  }

  let mapaListo = null;
  function cargarMapa() {
    if (!mapaListo) {
      mapaListo = fetch(raiz.dataset.mapa)
        .then((r) => {
          if (!r.ok) throw new Error(String(r.status));
          return r.json();
        })
        .then((geo) => echarts.registerMap("mundo", geo));
    }
    return mapaListo;
  }

  function mapa(desde, hasta) {
    const [seccion, lienzo] = bloque("", 440, "tbAncho");
    seccion.querySelector("h2").replaceChildren(
      "Países:",
      ...[["visita_pais", "visitas"], ["pais", "cartas"]].map(([tipo, texto]) =>
        el(
          "button",
          {
            type: "button",
            class: "tbChip" + (estado.mapa === tipo ? " tbChipOn" : ""),
            onclick: () => {
              estado.mapa = tipo;
              dibujar();
            },
          },
          texto,
        ),
      ),
    );
    const filas = filasDe(estado.mapa, desde, hasta);
    const total = filas.reduce((t, [, v]) => t + v, 0);
    const conocidos = filas.filter(([c]) => esPais(c));
    const sinPais = filas.filter(([c]) => !esPais(c)).reduce((t, [, v]) => t + v, 0);
    seccion.append(
      el(
        "p",
        { class: "tbNota" },
        `${fmt.format(total)} en ${conocidos.length} países` +
          (sinPais ? ` · ${fmt.format(sinPais)} sin país conocido` : "") +
          ". Rueda para acercar, arrastrá para mover. El país sale de la IP, que no se guarda.",
      ),
    );
    cargarMapa()
      .then(() =>
        despues(() => {
          // Si mientras bajaba el mapa se eligió otro período, este lienzo ya
          // no está en la página: dibujarlo dejaría un gráfico huérfano.
          if (!lienzo.isConnected) return;
          grafico(lienzo, {
            tooltip: {
              trigger: "item",
              formatter: (p) => {
                const d = p.data;
                if (!d || !d.codigo) return `${esc(p.name)}: 0`;
                return `${bandera(d.codigo)} <b>${esc(nombrePais(d.codigo))}</b><br>${fmt.format(d.value)} · ${pct(d.value, total)}`;
              },
            },
            visualMap: {
              min: 0, max: Math.max(1, ...conocidos.map(([, v]) => v)), left: 10, bottom: 10, calculable: true,
              text: ["más", "menos"], inRange: { color: ["#cfe0ff", "#5b8ff9", "#1d3f9e"] },
            },
            series: [{
              type: "map", map: "mundo", roam: true, zoom: 1.15, emphasis: { label: { show: false } },
              itemStyle: { areaColor: oscuro() ? "#2b2b2b" : "#eeeeee", borderColor: oscuro() ? "#454545" : "#cccccc" },
              data: conocidos.map(([c, v]) => ({ name: nombreMapa(c), value: v, codigo: c })),
            }],
          });
        }),
      )
      .catch(() => lienzo.replaceChildren(el("p", { class: "tbNota" }, "No se pudo cargar el mapa.")));
    return seccion;
  }

  function ranking(titulo, tipo, desde, hasta, nombre, forma) {
    const filas = filasDe(tipo, desde, hasta);
    const total = filas.reduce((t, [, v]) => t + v, 0);
    const TOPE = 10;
    const visibles = filas.slice(0, TOPE);
    const resto = filas.slice(TOPE).reduce((t, [, v]) => t + v, 0);
    if (resto) visibles.push([`Otros (${filas.length - TOPE})`, resto, true]);
    const alto = forma === "torta" ? 280 : Math.max(120, visibles.length * 30 + 20);
    const [seccion, lienzo] = bloque(`${titulo} · ${fmt.format(total)}`, alto, "tbRanking");
    if (!visibles.length) {
      lienzo.style.height = "auto";
      lienzo.replaceChildren(el("p", { class: "tbNota" }, "Sin datos en este período."));
      return seccion;
    }
    const etiqueta = (f) => (f[2] ? f[0] : nombre(f[0]));
    const tip = (p) => `<b>${esc(p.name)}</b><br>${fmt.format(p.value)} · ${pct(p.value, total)}`;
    despues(() =>
      grafico(
        lienzo,
        forma === "torta"
          ? {
              tooltip: { trigger: "item", formatter: tip },
              legend: { type: "scroll", orient: "vertical", right: 0, top: "middle", textStyle: { fontSize: 12 } },
              series: [{
                type: "pie", radius: ["45%", "75%"], center: ["32%", "50%"],
                itemStyle: { borderRadius: 6, borderColor: oscuro() ? "#212121" : "#ffffff", borderWidth: 2 },
                label: { show: false }, emphasis: { label: { show: true, formatter: "{d}%", fontWeight: "bold", fontSize: 16 } },
                data: visibles.map((f) => ({ name: etiqueta(f), value: f[1] })),
              }],
            }
          : {
              grid: { left: 150, right: 90, top: 6, bottom: 6 },
              tooltip: { trigger: "item", formatter: tip },
              xAxis: { type: "value", show: false },
              yAxis: {
                type: "category", inverse: true, data: visibles.map(etiqueta),
                axisTick: { show: false }, axisLine: { show: false },
                axisLabel: { width: 140, overflow: "truncate" },
              },
              series: [{
                type: "bar", barWidth: "60%", data: visibles.map((f) => f[1]),
                itemStyle: { color: COLORES[0], borderRadius: [0, 5, 5, 0] },
                label: { show: true, position: "right", formatter: (p) => `${fmt.format(p.value)} · ${pct(p.value, total)}` },
              }],
            },
      ),
    );
    return seccion;
  }

  const conBandera = (c) => `${bandera(c)} ${nombrePais(c)}`;
  const nombreDe = (grupo) => (v) => (NOMBRES[grupo] || {})[v] || v;

  // --- armado -----------------------------------------------------------------

  function dibujar() {
    graficos.forEach((g) => g.dispose());
    graficos = [];
    const r = rango();
    const cabeza = (texto) =>
      el(
        "header",
        { class: "tbCabeza" },
        el("div", {}, el("h1", {}, "Analítica"), el("p", { class: "tbNota" }, texto)),
        selectorPeriodo(),
      );
    if (!r) {
      raiz.replaceChildren(cabeza("Todavía no hay datos de ese período."));
      return;
    }
    const [desde, hasta, pedido] = r;
    let texto =
      (desde === hasta
        ? etiquetaDia(D.fechas[desde], true)
        : `${etiquetaDia(D.fechas[desde], true)} → ${etiquetaDia(D.fechas[hasta], true)}`) +
      " · contado en el servidor, sin cookies";
    if (pedido < desde || (desde === 0 && D.recortado)) {
      texto += D.recortado
        ? ` · el tablero trae desde el ${etiquetaDia(D.fechas[0], true)}; lo anterior está en la tabla de abajo`
        : ` · los datos empiezan el ${etiquetaDia(D.fechas[0], true)}`;
    }
    raiz.replaceChildren(
      cabeza(texto),
      tarjetas(desde, hasta),
      el(
        "div",
        { class: "tbGrilla" },
        embudo(desde, hasta),
        porDia(desde, hasta),
        mapa(desde, hasta),
        ranking("Visitas por país", "visita_pais", desde, hasta, conBandera),
        ranking("Visitas por sección", "visita_seccion", desde, hasta, nombreDe("seccion"), "torta"),
        ranking("Visitas por canal", "visita_canal", desde, hasta, nombreDe("canal"), "torta"),
        ranking("Cartas por país", "pais", desde, hasta, conBandera),
        ranking("Cartas por canal", "canal", desde, hasta, nombreDe("canal"), "torta"),
        ranking("Cartas por lugar (zona horaria)", "lugar", desde, hasta, (v) => v),
      ),
    );
  }

  dibujar();
  // El botón de tema del admin cambia `data-theme`: los gráficos lo siguen.
  new MutationObserver(() => dibujar()).observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-theme"],
  });
})();
