"""Los endpoints del vínculo (parte 3 de la spec de Vínculo).

Todo 404 con `VINCULO_ENABLED=0` (RF25). Un vínculo sólo lo ve su cuenta: se
resuelve siempre con `account=request.user`, y uno ajeno es 404, igual que una
carta ajena. Las operaciones del informe son las del natal (`informe_api`); lo
único propio es mostrar los alias donde el modelo escribió «Persona A» (RF22).
"""

import re

from django.conf import settings
from django.http import Http404
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from api import informe_api
from api.auth import AccountTokenAuthentication
from api.firma_frases import firma
from api.models import Chart, Sujeto
from api.permissions import HasAccount
from api.vinculo_service import alias, cartas, crear_vinculo
from api.vinculo_tipos import VinculoInvalido

_PERSONA = re.compile(r"\b(?:Persona|Person|Pessoa) ([AB])\b")


def sustituir_alias(texto: str, alias_: tuple[str, str]) -> str:
    """RF22: el modelo escribe «Persona A»; se muestra el alias, si lo hay.
    Sensible a mayúsculas: «la persona a quien…» no es una marca. El alias
    sale tal cual: escaparlo es de quien lo dibuja (React en la web, `_esc`
    en el PDF)."""
    def _reemplazo(m: re.Match) -> str:
        nombre = alias_[0 if m.group(1) == "A" else 1]
        return nombre or m.group(0)
    return _PERSONA.sub(_reemplazo, texto)


class _Base(APIView):
    authentication_classes = [AccountTokenAuthentication]
    permission_classes = [HasAccount]

    def initial(self, request, *args, **kwargs):
        # Antes de autenticar: con el flag apagado el endpoint no existe, ni
        # siquiera para decir «falta la sesión».
        if not settings.VINCULO_ENABLED:
            raise Http404
        super().initial(request, *args, **kwargs)

    def _vinculo(self, request, uuid) -> Sujeto:
        return get_object_or_404(
            Sujeto, uuid=uuid, account=request.user, producto=Sujeto.VINCULO,
        )


def _persona_repr(carta: Chart) -> dict:
    """La forma de `_preview_repr` (lo que la web ya sabe dibujar), sin nombre
    y sin tocar sujetos: es una copia (RF15). `_chart_repr` no sirve: crearía
    un sujeto NATAL para la copia."""
    bd = carta.birth_data
    return {
        "house_system": carta.house_system, "zodiac": carta.zodiac, "data": carta.data,
        "firma": firma(carta.data),
        "birth": {
            "date": bd.date.isoformat(),
            "time": bd.time.strftime("%H:%M") if bd.time else None,
            "time_known": bd.time_known, "lat": bd.lat, "lng": bd.lng,
            "tz_name": bd.tz_name, "place_label": bd.place_label,
        },
    }


def _repr(sujeto: Sujeto) -> dict:
    a, b = cartas(sujeto)
    return {
        "id": str(sujeto.uuid), "tipo": sujeto.parametros["tipo"],
        "roles": sujeto.parametros["roles"], "alias": list(alias(sujeto)),
        "personas": [_persona_repr(a), _persona_repr(b)],
        "created_at": sujeto.created_at.isoformat(),
    }


def _con_alias(sujeto: Sujeto):
    alias_ = alias(sujeto)
    return lambda texto: sustituir_alias(texto, alias_)


class VinculosView(_Base):
    """`GET /api/vinculos/` los de la cuenta; `POST` crea uno."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "vinculo"

    def get_throttles(self):
        # El techo es para crear (calcula dos cartas); listar no lo gasta.
        return super().get_throttles() if self.request.method == "POST" else []

    def get(self, request):
        qs = Sujeto.objects.filter(
            account=request.user, producto=Sujeto.VINCULO,
        ).order_by("-created_at")
        return Response({"results": [
            {"id": str(s.uuid), "tipo": s.parametros["tipo"], "alias": list(alias(s)),
             "created_at": s.created_at.isoformat()}
            for s in qs
        ]})

    def post(self, request):
        try:
            sujeto = crear_vinculo(
                request.user, request.data.get("tipo"), request.data.get("personas"),
            )
        except VinculoInvalido as exc:
            return Response({"error": exc.motivo}, status=status.HTTP_400_BAD_REQUEST)
        except Chart.DoesNotExist:
            # Una carta que no es de esta cuenta: 404, como cualquier carta ajena.
            raise Http404 from None
        return Response(_repr(sujeto), status=status.HTTP_201_CREATED)


class VinculoDetalleView(_Base):
    def get(self, request, uuid):
        return Response(_repr(self._vinculo(request, uuid)))


class VinculoInformeView(_Base):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "interpretation"

    def get(self, request, uuid):
        if (error := informe_api.validar(request.query_params)) is not None:
            return error
        sujeto = self._vinculo(request, uuid)
        return informe_api.leer(sujeto, request.query_params, transformar=_con_alias(sujeto))

    def post(self, request, uuid):
        if (error := informe_api.chequear_pedido(request.data)) is not None:
            return error
        return informe_api.pedir(self._vinculo(request, uuid), request.data, request.user)


class VinculoInformeEstadoView(_Base):
    def get(self, request, uuid):
        if (error := informe_api.validar(request.query_params)) is not None:
            return error
        return informe_api.estado(self._vinculo(request, uuid), request.query_params)


class VinculoSeccionesView(_Base):
    def get(self, request, uuid):
        if (error := informe_api.validar(request.query_params)) is not None:
            return error
        sujeto = self._vinculo(request, uuid)
        return informe_api.secciones(sujeto, request.query_params, transformar=_con_alias(sujeto))


class VinculoIndiceView(_Base):
    def get(self, request, uuid):
        if (error := informe_api.validar_lang(request.query_params)) is not None:
            return error
        return informe_api.indice(self._vinculo(request, uuid), request.query_params)
