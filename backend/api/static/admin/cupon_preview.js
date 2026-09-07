// Preview en vivo del precio final por producto en el admin de cupones.
// Lee porcentaje y productos marcados, pregunta al endpoint interno del admin
// (que usa la misma `precio_final` que cobra el checkout) y dibuja la tabla.
(function () {
  "use strict";
  function listo(fn) {
    if (document.readyState !== "loading") fn(); else document.addEventListener("DOMContentLoaded", fn);
  }
  listo(function () {
    var caja = document.getElementById("cupon-precios");
    var porcentaje = document.getElementById("id_porcentaje");
    if (!caja || !porcentaje) return;  // en la ficha de un cupón ya creado el % es sólo lectura
    var url = caja.getAttribute("data-url");
    function productos() {
      return Array.prototype.map.call(
        document.querySelectorAll('input[name="productos"]:checked'), function (i) { return i.value; });
    }
    function dolares(c) { return "US$ " + Math.floor(c / 100) + "," + String(c % 100).padStart(2, "0"); }
    function pintar() {
      var p = parseInt(porcentaje.value, 10), prods = productos();
      if (!(p >= 1 && p <= 100) || prods.length === 0) { caja.textContent = "—"; return; }
      var q = new URLSearchParams();
      q.set("porcentaje", String(p));
      prods.forEach(function (c) { q.append("productos", c); });
      fetch(url + "?" + q.toString(), { credentials: "same-origin" })
        .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
        .then(function (d) {
          var t = document.createElement("table");
          t.innerHTML = "<tr><th>producto</th><th>lista</th><th>descuento</th><th>final</th></tr>";
          d.precios.forEach(function (f) {
            var tr = t.insertRow();
            [f.codigo, dolares(f.lista), "−" + dolares(f.descuento), dolares(f.final)].forEach(function (v) {
              tr.insertCell().textContent = v;
            });
          });
          caja.textContent = "";
          caja.appendChild(t);
        })
        .catch(function () { caja.textContent = "no se pudo calcular"; });
    }
    porcentaje.addEventListener("input", pintar);
    document.querySelectorAll('input[name="productos"]').forEach(function (i) { i.addEventListener("change", pintar); });
    pintar();
  });
})();
