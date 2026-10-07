import base64
import html
import os
import re
from datetime import datetime
from pathlib import Path

from importaciones_deuda import registrar_importacion_deuda
from naranja_email import parsear_correo_compra_naranja


SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly"
]

FUENTE_IMPORTACION = "gmail_naranja"


def _ruta_env(
    nombre_variable,
    valor_predeterminado,
):
    return Path(
        os.getenv(
            nombre_variable,
            valor_predeterminado,
        )
    )


def crear_servicio_gmail(
    credentials_path=None,
    token_path=None,
):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    credentials_path = Path(
        credentials_path
        or _ruta_env(
            "GMAIL_CREDENTIALS_PATH",
            "gmail_credentials.json",
        )
    )
    token_path = Path(
        token_path
        or _ruta_env(
            "GMAIL_TOKEN_PATH",
            "gmail_token.json",
        )
    )

    credenciales = None

    if token_path.exists():
        credenciales = Credentials.from_authorized_user_file(
            str(token_path),
            SCOPES,
        )

    if (
        credenciales is not None
        and credenciales.expired
        and credenciales.refresh_token
    ):
        credenciales.refresh(
            Request()
        )

    if (
        credenciales is None
        or not credenciales.valid
    ):
        if not credentials_path.exists():
            raise FileNotFoundError(
                "No se encontró el archivo OAuth de Gmail: "
                f"{credentials_path}"
            )

        flujo = InstalledAppFlow.from_client_secrets_file(
            str(credentials_path),
            SCOPES,
        )
        credenciales = flujo.run_local_server(
            port=0
        )

    token_path.write_text(
        credenciales.to_json(),
        encoding="utf-8",
    )

    return build(
        "gmail",
        "v1",
        credentials=credenciales,
        cache_discovery=False,
    )


def _decodificar_base64url(valor):
    if not valor:
        return ""

    faltantes = (
        4
        - len(valor) % 4
    ) % 4

    valor += "=" * faltantes

    return base64.urlsafe_b64decode(
        valor.encode("ascii")
    ).decode(
        "utf-8",
        errors="replace",
    )


def _texto_html_a_plano(texto):
    texto = re.sub(
        r"(?is)<(script|style).*?>.*?</\1>",
        " ",
        texto,
    )
    texto = re.sub(
        r"(?i)<br\s*/?>",
        "\n",
        texto,
    )
    texto = re.sub(
        r"(?i)</p\s*>",
        "\n",
        texto,
    )
    texto = re.sub(
        r"(?s)<[^>]+>",
        " ",
        texto,
    )

    return html.unescape(
        texto
    )


def _extraer_cuerpo(payload):
    textos_planos = []
    textos_html = []

    def recorrer(parte):
        mime_type = parte.get(
            "mimeType",
            ""
        )
        body = parte.get(
            "body",
            {}
        )
        data = body.get(
            "data"
        )

        if data:
            contenido = _decodificar_base64url(
                data
            )

            if mime_type == "text/plain":
                textos_planos.append(
                    contenido
                )
            elif mime_type == "text/html":
                textos_html.append(
                    contenido
                )

        for hija in parte.get(
            "parts",
            []
        ):
            recorrer(
                hija
            )

    recorrer(
        payload
    )

    if textos_planos:
        return "\n".join(
            textos_planos
        )

    if textos_html:
        return _texto_html_a_plano(
            "\n".join(
                textos_html
            )
        )

    return ""


def _cabeceras(payload):
    return {
        item.get("name", "").lower(): item.get(
            "value",
            ""
        )
        for item in payload.get(
            "headers",
            []
        )
    }


def leer_mensaje_gmail(
    servicio,
    message_id,
):
    mensaje = (
        servicio
        .users()
        .messages()
        .get(
            userId="me",
            id=message_id,
            format="full",
        )
        .execute()
    )

    payload = mensaje.get(
        "payload",
        {}
    )
    headers = _cabeceras(
        payload
    )

    internal_date = mensaje.get(
        "internalDate"
    )
    fecha_email = None

    if internal_date:
        fecha_email = datetime.fromtimestamp(
            int(internal_date) / 1000
        ).isoformat(
            timespec="seconds"
        )

    return {
        "id": mensaje["id"],
        "thread_id": mensaje.get(
            "threadId"
        ),
        "asunto": headers.get(
            "subject",
            "",
        ),
        "fecha_email": fecha_email,
        "cuerpo": _extraer_cuerpo(
            payload
        ),
    }


def buscar_ids_compras_naranja(
    servicio,
    fecha_corte,
    max_results=50,
):
    fecha = datetime.fromisoformat(
        str(fecha_corte).replace(
            "Z",
            "+00:00",
        )
    )

    # Se busca desde el día anterior y la fecha de corte se vuelve
    # a validar antes de tocar la deuda. Evita depender de la
    # semántica horaria del operador after: de Gmail.
    dia_busqueda = fecha.date()

    query = (
        'subject:"Ingresó una compra en tu tarjeta crédito" '
        f"after:{dia_busqueda.isoformat().replace('-', '/')}"
    )

    respuesta = (
        servicio
        .users()
        .messages()
        .list(
            userId="me",
            q=query,
            maxResults=max_results,
        )
        .execute()
    )

    return [
        item["id"]
        for item in respuesta.get(
            "messages",
            []
        )
    ]


def procesar_mensaje_naranja(
    *,
    gmail_message_id,
    asunto,
    cuerpo,
    fecha_email,
    fecha_corte,
):
    parseado = parsear_correo_compra_naranja(
        asunto=asunto,
        cuerpo=cuerpo,
        fecha_email=fecha_email,
    )

    if not parseado["ok"]:
        return parseado

    return registrar_importacion_deuda(
        fuente=FUENTE_IMPORTACION,
        id_externo=gmail_message_id,
        importe=parseado["importe"],
        fecha_operacion=(
            parseado["fecha_operacion"]
            or fecha_email
        ),
        moneda=parseado["moneda"],
        comercio=parseado["comercio"],
        titular=parseado["titular"],
        tipo_tarjeta=parseado[
            "tipo_tarjeta"
        ],
        plan=parseado["plan"],
        asunto=asunto,
        cuenta_deuda="naranja",
        aplica_deuda=parseado[
            "es_adicional_negocio"
        ],
        fecha_corte=fecha_corte,
    )


def sincronizar_compras_naranja(
    servicio=None,
    fecha_corte=None,
    max_results=50,
):
    fecha_corte = (
        fecha_corte
        or os.getenv(
            "NARANJA_IMPORTAR_DESDE"
        )
    )

    if not fecha_corte:
        return {
            "ok": False,
            "codigo": "FECHA_CORTE_NARANJA_REQUERIDA",
            "mensaje": (
                "Definí NARANJA_IMPORTAR_DESDE antes de "
                "activar la importación automática."
            ),
        }

    if servicio is None:
        servicio = crear_servicio_gmail()

    ids = buscar_ids_compras_naranja(
        servicio,
        fecha_corte=fecha_corte,
        max_results=max_results,
    )

    resultados = []

    for message_id in ids:
        correo = leer_mensaje_gmail(
            servicio,
            message_id,
        )

        resultados.append(
            procesar_mensaje_naranja(
                gmail_message_id=correo["id"],
                asunto=correo["asunto"],
                cuerpo=correo["cuerpo"],
                fecha_email=correo["fecha_email"],
                fecha_corte=fecha_corte,
            )
        )

    return {
        "ok": True,
        "codigo": "SINCRONIZACION_NARANJA_COMPLETA",
        "encontrados": len(ids),
        "resultados": resultados,
    }


if __name__ == "__main__":
    resultado = sincronizar_compras_naranja()

    print(
        resultado
    )
