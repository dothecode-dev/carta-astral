"""Reglas del checkout que no son de ninguna pasarela: idiomas y vencimiento."""

import datetime as dt

# Los idiomas que el sitio sirve, y que Stripe también soporta en su checkout.
# Lista blanca y no concatenación: el locale llega del navegador y termina en la
# URL a la que Stripe devuelve a la persona después de pagar.
LOCALES = ("es", "en", "pt")
LOCALE_POR_DEFECTO = "es"

# Cuánto vive una sesión de pago. Sin decirlo, Stripe la deja abierta 24 h, y
# durante todo ese tiempo la cuenta tendría que decir algo de un pago que
# nadie hizo. Una hora alcanza de sobra para pagar, y es lo que dura el link
# «retomar el pago» de la cuenta. Stripe admite entre 30 minutos y 24 horas.
# Al vencer manda `checkout.session.expired`; el endpoint del dashboard tiene
# que estar suscripto a ese evento (nada en el repo lo verifica).
VENCIMIENTO_SESION = dt.timedelta(hours=1)
