/* Tablero de analítica del admin (20-10-2026).
 *
 * Los datos los deja el servidor en <script id="tablero-datos"> (conteo.tablero):
 * por día, desde el primer dato, cada evento, las compras, lo cobrado por moneda
 * y la procedencia. Acá se elige el período y se dibuja. Todo con textContent y
 * createElement: ningún valor entra como HTML.
 */
(function () {
  "use strict";

  const raiz = document.getElementById("tablero");
  const fuente = document.getElementById("tablero-datos");
  if (!raiz || !fuente) return;
  const D = JSON.parse(fuente.textContent);
  const NOMBRES = JSON.parse((document.getElementById("tablero-nombres") || {}).textContent || "{}");
  const N = D.fechas.length;
  const SVG = "http://www.w3.org/2000/svg";

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

  function svg(tag, attrs) {
    const nodo = document.createElementNS(SVG, tag);
    for (const [k, v] of Object.entries(attrs || {})) nodo.setAttribute(k, v);
    return nodo;
  }

  const fmt = new Intl.NumberFormat("es-AR");
  const pct = (a, b) => (b > 0 ? `${Math.round((a / b) * 1000) / 10}%` : "—");
  const serie = (clave) => D.eventos[clave] || new Array(N).fill(0);
  const suma = (valores, desde, hasta) => {
    let total = 0;
    for (let i = Math.max(0, desde); i <= hasta && i < valores.length; i++) total += valores[i] || 0;
    return total;
  };
  const sumaSeries = (...claves) => {
    const out = new Array(N).fill(0);
    for (const c of claves) serie(c).forEach((v, i) => (out[i] += v));
    return out;
  };

  const DIAS_SEMANA = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
  function etiquetaDia(iso, larga) {
    const [a, m, d] = iso.split("-").map(Number);
    const fecha = new Date(Date.UTC(a, m - 1, d));
    const corta = `${d}/${m}`;
    return larga ? `${DIAS_SEMANA[fecha.getUTCDay()]} ${corta}/${a}` : corta;
  }

  const nombrePais = (() => {
    let dn = null;
    try {
      dn = new Intl.DisplayNames(["es"], { type: "region" });
    } catch (e) {
      dn = null;
    }
    return (codigo) => {
      if (!/^[A-Z]{2}$/.test(codigo)) return "Desconocido";
      try {
        return (dn && dn.of(codigo)) || codigo;
      } catch (e) {
        return codigo;
      }
    };
  })();
  const bandera = (codigo) =>
    /^[A-Z]{2}$/.test(codigo) ? String.fromCodePoint(...[...codigo].map((c) => 0x1f1a5 + c.charCodeAt(0))) : "🌐";

  const MONEDAS = { usd: ["US$", "en-US"], brl: ["R$", "pt-BR"], ars: ["$", "es-AR"] };
  function dinero(centavos, moneda) {
    const [simbolo, locale] = MONEDAS[moneda] || [moneda.toUpperCase(), "es-AR"];
    const n = new Intl.NumberFormat(locale, {
      minimumFractionDigits: centavos % 100 ? 2 : 0,
      maximumFractionDigits: 2,
    }).format(centavos / 100);
    return `${simbolo} ${n}`;
  }

  // --- estado: el período -----------------------------------------------------

  const ULTIMO = N - 1;
  const PERIODOS = [
    ["hoy", "Hoy", () => [ULTIMO, ULTIMO]],
    ["ayer", "Ayer", () => [ULTIMO - 1, ULTIMO - 1]],
    ["7", "7 días", () => [ULTIMO - 6, ULTIMO]],
    ["30", "30 días", () => [ULTIMO - 29, ULTIMO]],
    ["todo", "Todo", () => [0, ULTIMO]],
  ];
  const guardado = (() => {
    try {
      return localStorage.getItem("tablero.periodo");
    } catch (e) {
      return null;
    }
  })();
  const estado = {
    periodo: PERIODOS.some((p) => p[0] === guardado) ? guardado : "7",
    desde: null,
    metrica: "visita",
  };

  function rango() {
    if (estado.periodo === "desde" && estado.desde) {
      const i = D.fechas.indexOf(estado.desde);
      const desde = i >= 0 ? i : D.fechas.findIndex((f) => f >= estado.desde);
      return [desde < 0 ? ULTIMO : desde, ULTIMO];
    }
    const p = PERIODOS.find((x) => x[0] === estado.periodo) || PERIODOS[2];
    const [a, b] = p[2]();
    return [Math.max(0, a), Math.max(0, b)];
  }

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
            try {
              localStorage.setItem("tablero.periodo", clave);
            } catch (e) {
              /* sin almacenamiento: el período no se recuerda */
            }
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

  function tarjeta(titulo, valores, desde, hasta, extra) {
    const largo = hasta - desde + 1;
    const actual = suma(valores, desde, hasta);
    const previo = desde - largo >= 0 ? suma(valores, desde - largo, desde - 1) : null;
    let delta = null;
    if (previo !== null) {
      if (previo === 0 && actual === 0) delta = el("span", { class: "tbDelta" }, "= período anterior");
      else if (previo === 0) delta = el("span", { class: "tbDelta tbSube" }, `▲ antes 0`);
      else {
        const cambio = Math.round(((actual - previo) / previo) * 100);
        delta = el(
          "span",
          { class: "tbDelta " + (cambio >= 0 ? "tbSube" : "tbBaja"), title: `período anterior: ${fmt.format(previo)}` },
          `${cambio >= 0 ? "▲" : "▼"} ${Math.abs(cambio)}% (antes ${fmt.format(previo)})`,
        );
      }
    }
    return el(
      "div",
      { class: "tbTarjeta" },
      el("div", { class: "tbTarjetaTitulo" }, titulo),
      el("div", { class: "tbTarjetaValor" }, fmt.format(actual)),
      delta,
      extra || null,
    );
  }

  function tarjetas(desde, hasta) {
    const cobrado = Object.entries(D.ingresos || {})
      .map(([moneda, valores]) => [moneda, suma(valores, desde, hasta)])
      .filter(([, v]) => v > 0);
    const clics = sumaSeries("teaser_clic_arriba", "teaser_clic_cierre");
    return el(
      "div",
      { class: "tbTarjetas" },
      tarjeta("Visitas (páginas)", serie("visita"), desde, hasta),
      tarjeta("Cartas calculadas", serie("carta_calculada"), desde, hasta),
      tarjeta("Clic en comprar", clics, desde, hasta),
      tarjeta("Pagos abiertos", serie("checkout_abierto"), desde, hasta),
      tarjeta(
        "Compras pagas",
        serie("compra_pagada"),
        desde,
        hasta,
        el(
          "div",
          { class: "tbCobrado" },
          cobrado.length ? cobrado.map(([m, v]) => dinero(v, m)).join(" · ") : "sin cobros",
        ),
      ),
    );
  }

  function embudo(desde, hasta) {
    const s = (c) => suma(serie(c), desde, hasta);
    const pasos = [
      ["Visitas (páginas)", s("visita"), "Cada página abierta en el sitio."],
      ["Cartas calculadas", s("carta_calculada"), "Con y sin cuenta."],
      ["Llegó al final del adelanto", s("teaser_cierre_visto"), "Sin cuenta. Una vez por carta."],
      [
        "Apretó comprar",
        s("teaser_clic_arriba") + s("teaser_clic_cierre"),
        `Sin cuenta: ${fmt.format(s("teaser_clic_arriba"))} arriba + ${fmt.format(s("teaser_clic_cierre"))} al final · ` +
          `ARS ${fmt.format(s("teaser_clic_ars"))} · USD ${fmt.format(s("teaser_clic_usd"))} · BRL ${fmt.format(s("teaser_clic_brl"))}`,
      ],
      ["Dejó el mail (pesos)", s("teaser_mail_enviado"), "Sólo pide mail el pago en pesos."],
      ["Pago abierto", s("checkout_abierto"), "Con y sin cuenta, todas las monedas."],
      ["Compra paga", s("compra_pagada"), "Sin reembolsos ni canjes de cupón del 100 %."],
    ];
    const tope = Math.max(1, ...pasos.map((p) => p[1]));
    const filas = pasos.map(([nombre, valor, nota], i) => {
      const anterior = i > 0 ? pasos[i - 1][1] : null;
      const ancho = Math.max(valor > 0 ? 0.6 : 0, (valor / tope) * 100);
      return el(
        "div",
        { class: "tbPaso" },
        el("div", { class: "tbPasoNombre" }, nombre, el("small", {}, nota)),
        el(
          "div",
          { class: "tbPasoBarra" },
          el("div", { class: "tbPasoRelleno", style: `width:${ancho}%` }),
          el("span", { class: "tbPasoValor" }, fmt.format(valor)),
        ),
        el(
          "div",
          { class: "tbPasoPct", title: "contra el paso anterior" },
          anterior === null ? "" : pct(valor, anterior),
          anterior === null ? null : el("small", {}, "del paso anterior"),
        ),
      );
    });
    const extra = el(
      "p",
      { class: "tbNota" },
      `Abrió los datos de la carta: ${fmt.format(s("teaser_datos_abiertos"))} · ` +
        `Volvió a corregir fecha, hora o lugar: ${fmt.format(s("teaser_volver"))}. ` +
        "Veces, no personas. El % es contra el paso anterior.",
    );
    return el("section", { class: "tbBloque" }, el("h2", {}, "Embudo"), ...filas, extra);
  }

  const METRICAS = [
    ["visita", "Visitas", () => serie("visita")],
    ["carta_calculada", "Cartas", () => serie("carta_calculada")],
    ["clics", "Clic en comprar", () => sumaSeries("teaser_clic_arriba", "teaser_clic_cierre")],
    ["checkout_abierto", "Pagos abiertos", () => serie("checkout_abierto")],
    ["compra_pagada", "Compras", () => serie("compra_pagada")],
  ];

  function porDia(desde, hasta) {
    const elegida = METRICAS.find((m) => m[0] === estado.metrica) || METRICAS[0];
    const valores = elegida[2]().slice(desde, hasta + 1);
    const fechas = D.fechas.slice(desde, hasta + 1);
    const n = valores.length;
    const ANCHO = 960;
    const ALTO = 240;
    const IZQ = 40;
    const ABAJO = 26;
    const ARRIBA = 12;
    const util = ALTO - ABAJO - ARRIBA;
    const tope = Math.max(1, ...valores);
    const paso = (ANCHO - IZQ) / Math.max(1, n);
    const grafico = svg("svg", { viewBox: `0 0 ${ANCHO} ${ALTO}`, class: "tbSvg", role: "img" });
    grafico.append(Object.assign(svg("title"), { textContent: `${elegida[1]} por día` }));
    for (const v of [0, Math.ceil(tope / 2), tope]) {
      const y = ARRIBA + util - (v / tope) * util;
      grafico.append(svg("line", { x1: IZQ, x2: ANCHO, y1: y, y2: y, class: "tbGuia" }));
      const t = svg("text", { x: IZQ - 6, y: y + 4, class: "tbEje", "text-anchor": "end" });
      t.textContent = fmt.format(v);
      grafico.append(t);
    }
    const aviso = el("div", { class: "tbTooltip", hidden: true });
    const cadaEtiqueta = Math.max(1, Math.ceil(n / 12));
    valores.forEach((v, i) => {
      const alto = (v / tope) * util;
      const x = IZQ + i * paso + paso * 0.15;
      const ancho = Math.max(1, paso * 0.7);
      const hoy = desde + i === ULTIMO;
      const barra = svg("rect", {
        x,
        y: ARRIBA + util - alto,
        width: ancho,
        height: Math.max(v > 0 ? 1.5 : 0, alto),
        rx: Math.min(3, ancho / 3),
        class: "tbBarra" + (hoy ? " tbBarraHoy" : ""),
      });
      const zona = svg("rect", { x: IZQ + i * paso, y: 0, width: paso, height: ALTO, class: "tbZona" });
      const mostrar = (evento) => {
        const dia = desde + i;
        aviso.replaceChildren(
          el("strong", {}, etiquetaDia(D.fechas[dia], true) + (dia === ULTIMO ? " (hoy, parcial)" : "")),
          ...METRICAS.map(([, nombre, f]) => el("div", {}, `${nombre}: ${fmt.format(f()[dia] || 0)}`)),
        );
        aviso.hidden = false;
        const caja = contenedor.getBoundingClientRect();
        aviso.style.left = `${Math.min(evento.clientX - caja.left + 12, caja.width - 200)}px`;
        aviso.style.top = `${evento.clientY - caja.top + 12}px`;
      };
      zona.addEventListener("mouseenter", mostrar);
      zona.addEventListener("mousemove", mostrar);
      zona.addEventListener("mouseleave", () => (aviso.hidden = true));
      grafico.append(barra, zona);
      if (i % cadaEtiqueta === 0 || i === n - 1) {
        const t = svg("text", { x: x + ancho / 2, y: ALTO - 8, class: "tbEje", "text-anchor": "middle" });
        t.textContent = etiquetaDia(fechas[i], false);
        grafico.append(t);
      }
    });
    const chips = METRICAS.map(([clave, nombre]) =>
      el(
        "button",
        {
          type: "button",
          class: "tbChip" + (estado.metrica === clave ? " tbChipOn" : ""),
          onclick: () => {
            estado.metrica = clave;
            dibujar();
          },
        },
        nombre,
      ),
    );
    const contenedor = el("div", { class: "tbGraficoCaja" }, grafico, aviso);
    return el(
      "section",
      { class: "tbBloque" },
      el("h2", {}, "Por día"),
      el("div", { class: "tbChips" }, ...chips),
      contenedor,
      el("p", { class: "tbNota" }, "Días en UTC. La última barra es hoy, incompleto. Pasá el mouse para ver cada día."),
    );
  }

  function ranking(titulo, tipo, desde, hasta, nombre) {
    const valores = (D.procedencia || {})[tipo] || {};
    const filas = Object.entries(valores)
      .map(([valor, serieValor]) => [valor, suma(serieValor, desde, hasta)])
      .filter(([, v]) => v > 0)
      .sort((a, b) => b[1] - a[1]);
    const total = filas.reduce((t, [, v]) => t + v, 0);
    const TOPE = 10;
    const visibles = filas.slice(0, TOPE);
    const resto = filas.slice(TOPE).reduce((t, [, v]) => t + v, 0);
    if (resto) visibles.push(["__otros", resto]);
    const tope = Math.max(1, ...visibles.map((f) => f[1]));
    const cuerpo = visibles.length
      ? visibles.map(([valor, v]) =>
          el(
            "div",
            { class: "tbFila" },
            el("div", { class: "tbFilaNombre" }, valor === "__otros" ? `Otros (${filas.length - TOPE})` : nombre(valor)),
            el(
              "div",
              { class: "tbFilaBarra" },
              el("div", { class: "tbFilaRelleno", style: `width:${(v / tope) * 100}%` }),
            ),
            el("div", { class: "tbFilaValor" }, fmt.format(v), el("small", {}, pct(v, total))),
          ),
        )
      : [el("p", { class: "tbNota" }, "Sin datos en este período.")];
    return el(
      "section",
      { class: "tbBloque tbRanking" },
      el("h3", {}, titulo, el("small", {}, ` · ${fmt.format(total)}`)),
      ...cuerpo,
    );
  }

  const conBandera = (codigo) => `${bandera(codigo)} ${nombrePais(codigo)}`;
  const nombreDe = (grupo) => (valor) => (NOMBRES[grupo] || {})[valor] || valor;

  function rankings(desde, hasta) {
    return el(
      "div",
      { class: "tbRankings" },
      ranking("Visitas por país", "visita_pais", desde, hasta, conBandera),
      ranking("Visitas por sección", "visita_seccion", desde, hasta, nombreDe("seccion")),
      ranking("Visitas por canal", "visita_canal", desde, hasta, nombreDe("canal")),
      ranking("Cartas por país", "pais", desde, hasta, conBandera),
      ranking("Cartas por canal", "canal", desde, hasta, nombreDe("canal")),
      ranking("Cartas por lugar (zona horaria)", "lugar", desde, hasta, (v) => v),
    );
  }

  // --- armado -----------------------------------------------------------------

  function dibujar() {
    const [desde, hasta] = rango();
    const etiqueta =
      desde === hasta
        ? etiquetaDia(D.fechas[desde], true)
        : `${etiquetaDia(D.fechas[desde], true)} → ${etiquetaDia(D.fechas[hasta], true)}`;
    raiz.replaceChildren(
      el(
        "header",
        { class: "tbCabeza" },
        el("div", {}, el("h1", {}, "Analítica"), el("p", { class: "tbNota" }, `${etiqueta} · contado en el servidor, sin cookies`)),
        selectorPeriodo(),
      ),
      tarjetas(desde, hasta),
      embudo(desde, hasta),
      porDia(desde, hasta),
      rankings(desde, hasta),
    );
  }

  dibujar();
})();
