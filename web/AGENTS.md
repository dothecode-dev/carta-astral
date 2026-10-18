<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

# El esqueleto de una página

Toda página de `app/[locale]/` se arma igual, y **no es prosa: lo chequea
`tests/esqueleto.test.ts`**, que corre en `make test-web` y en el CI.

```tsx
<>
  <Nav locale={locale} dict={dict} path="/loquesea" signedIn={signedIn} />
  <main className="docFrame …">…</main>
  <Footer locale={locale} dict={dict} />
</>
```

- `Nav` y `Footer` van **sueltos**, nunca dentro del `<main>`. Cada uno trae su
  propio marco interno (`navInner`, `footInner`) con la misma medida, así que
  ocupan el ancho de la ventana y su contenido queda alineado entre sí en todas
  las páginas. El contenido usa la medida que quiera: es otra cosa.
- El contenido va en `<main>`, siempre. Es el landmark por el que un lector de
  pantalla salta la navegación.
- La única excepción es una página que sólo redirige (`carta/[id]/lectura`): no
  renderiza nada y el test la reconoce por eso, no por faltarle el `Nav`.

Por qué existe la regla: el 03-09-2026 `/precios` tenía el `Footer` fuera del
`<main>` mientras las otras diez lo tenían adentro. Como el pie no traía marco
propio, su ancho lo decidía quien lo envolviera: se estiraba hasta el borde de
la ventana contra un header contenido. Dos páginas, además, usaban `<div
className="docFrame">` en vez de `<main>` y no tenían landmark principal.

# Los anchos de página

Toda página se centra en la pantalla con **uno** de tres anchos, y **no es prosa:
lo chequea `tests/anchos.test.ts`**.

- `--ancho-columna` (42rem): formularios, textos, notas, cuenta. Es el default de
  `.docFrame`.
- `--ancho-sitio` (1180px, el de la navegación): lo que necesita espacio —la
  carta, precios, y `/nueva` cuando ya muestra la carta calculada—.
- `--ancho-angosto` (35rem): una tarjeta sola (entrar).

Un marco (`.algoFrame`) no declara otro `max-width`, y si cambia el ancho va
**después** de `.docFrame` en `globals.css` (misma especificidad: gana la
última). Los párrafos toman la medida de `:where(.docFrame) p`, sin
especificidad, así la clase propia de un párrafo sigue ganando.

Por qué existe la regla: hasta el 18-10-2026 cada página tenía su propio ancho
(1180, 1080, 960, 860, 720 y 560 px) y el título de cada una arrancaba en otro
lugar. Alinear todo al borde del logo se probó y se descartó: dejaba los
formularios contra la izquierda y tres cuartos de pantalla vacíos.
