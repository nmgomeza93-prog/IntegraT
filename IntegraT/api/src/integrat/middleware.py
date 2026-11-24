"""Middleware de la API."""

import json


class LimiteCuerpo:
    """Rechaza con 413 las peticiones con cuerpo mayor a `maximo` bytes.

    Revisa Content-Length y, si el cliente manda el cuerpo por partes (chunked) o miente en la
    cabecera, cuenta los bytes conforme llegan. Es ASGI puro para no leer el cuerpo completo.

    Al pasarse del límite responde 413 de inmediato y le avisa a la app que el cliente se fue
    (`http.disconnect`); lo que la app intente enviar después se descarta. No se puede lanzar
    una excepción desde `receive`: FastAPI la convertiría en un 400.
    """

    def __init__(self, app, maximo: int) -> None:
        self.app = app
        self.maximo = maximo

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        largo = dict(scope["headers"]).get(b"content-length", b"")
        if largo.isdigit() and int(largo) > self.maximo:
            await self._rechazar(send)
            return

        recibidos = 0
        rechazada = False

        async def receive_limitado():
            nonlocal recibidos, rechazada
            mensaje = await receive()
            if mensaje["type"] == "http.request" and not rechazada:
                recibidos += len(mensaje.get("body", b""))
                if recibidos > self.maximo:
                    rechazada = True
                    await self._rechazar(send)
                    return {"type": "http.disconnect"}
            return mensaje

        async def send_vigilado(mensaje):
            if not rechazada:
                await send(mensaje)

        await self.app(scope, receive_limitado, send_vigilado)

    @staticmethod
    async def _rechazar(send) -> None:
        cuerpo = json.dumps({"detail": "La petición es demasiado grande."}).encode()
        await send({
            "type": "http.response.start", "status": 413,
            "headers": [(b"content-type", b"application/json"),
                        (b"content-length", str(len(cuerpo)).encode()),
                        (b"connection", b"close")],
        })
        await send({"type": "http.response.body", "body": cuerpo})
