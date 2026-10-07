import re
import unicodedata
from datetime import datetime


ADICIONAL_NEGOCIO = "Claudia Elizabet Rotondo"

MESES_NARANJA = {
    "ENE": 1,
    "FEB": 2,
    "MAR": 3,
    "ABR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AGO": 8,
    "SET": 9,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DIC": 12,
}


def _normalizar(texto):
    valor = unicodedata.normalize(
        "NFKD",
        str(texto or "")
    )
    valor = "".join(
        caracter
        for caracter in valor
        if not unicodedata.combining(caracter)
    )
    return " ".join(
        valor.lower().split()
    )


def _importe_argentino(valor):
    limpio = (
        str(valor)
        .replace("$", "")
        .replace(" ", "")
        .strip()
    )

    if "," in limpio:
        entero, decimal = limpio.rsplit(",", 1)
        entero = entero.replace(".", "")
        return float(
            entero + "." + decimal
        )

    return float(
        limpio.replace(".", "")
    )


def _fecha_operacion(
    cuerpo,
    fecha_email=None,
):
    texto = " ".join(
        str(cuerpo or "").split()
    )

    coincidencia = re.search(
        r"\b(\d{1,2})/(ENE|FEB|MAR|ABR|MAY|JUN|JUL|AGO|SET|SEP|OCT|NOV|DIC)"
        r"\s*-\s*(\d{1,2}):(\d{2})\s*h\b",
        texto,
        flags=re.IGNORECASE,
    )

    if not coincidencia:
        if not fecha_email:
            return None

        try:
            return datetime.fromisoformat(
                str(fecha_email).replace("Z", "+00:00")
            ).isoformat()
        except ValueError:
            return None

    anio = None

    if fecha_email:
        try:
            anio = datetime.fromisoformat(
                str(fecha_email).replace("Z", "+00:00")
            ).year
        except ValueError:
            anio = None

    if anio is None:
        anio = datetime.now().year

    mes = MESES_NARANJA[
        coincidencia.group(2).upper()
    ]

    fecha = datetime(
        anio,
        mes,
        int(coincidencia.group(1)),
        int(coincidencia.group(3)),
        int(coincidencia.group(4)),
    )

    return fecha.isoformat(
        timespec="minutes"
    )


def parsear_correo_compra_naranja(
    asunto,
    cuerpo,
    fecha_email=None,
):
    asunto_normalizado = _normalizar(
        asunto
    )

    if (
        "ingreso una compra"
        not in asunto_normalizado
    ):
        return {
            "ok": False,
            "codigo": "CORREO_NARANJA_NO_ES_COMPRA",
        }

    texto = " ".join(
        str(cuerpo or "").split()
    )

    compra = re.search(
        r"TU\s+COMPRA\s*\$\s*([\d\.]+(?:,\d{1,2})?)\s+(.+?)\s+"
        r"(Adicional|Titular)\s*-\s*(.+?)\s+Tarjeta\s+(.+?)\s+"
        r"Plan\s+(\d+)",
        texto,
        flags=re.IGNORECASE,
    )

    if not compra:
        return {
            "ok": False,
            "codigo": "FORMATO_CORREO_NARANJA_NO_RECONOCIDO",
        }

    importe = _importe_argentino(
        compra.group(1)
    )
    comercio = compra.group(2).strip()
    tipo_tarjeta = compra.group(3).strip()
    titular = compra.group(4).strip()
    tarjeta = compra.group(5).strip()
    plan = compra.group(6).strip()

    moneda_match = re.search(
        r"\b(?:cuota\s+)?en\s+(PESOS|DOLARES|DÓLARES)\b",
        texto,
        flags=re.IGNORECASE,
    )
    moneda = (
        "ARS"
        if not moneda_match
        or _normalizar(
            moneda_match.group(1)
        ) == "pesos"
        else "USD"
    )

    es_adicional = (
        _normalizar(tipo_tarjeta)
        == "adicional"
    )
    es_adicional_negocio = (
        es_adicional
        and _normalizar(titular)
        == _normalizar(
            ADICIONAL_NEGOCIO
        )
    )

    return {
        "ok": True,
        "codigo": "CORREO_NARANJA_PARSEADO",
        "importe": importe,
        "moneda": moneda,
        "comercio": comercio,
        "titular": titular,
        "tipo_tarjeta": tipo_tarjeta,
        "tarjeta": tarjeta,
        "plan": plan,
        "fecha_operacion": _fecha_operacion(
            cuerpo,
            fecha_email=fecha_email,
        ),
        "es_adicional_negocio": (
            es_adicional_negocio
        ),
        "estado_sugerido": (
            "pendiente_clasificacion"
            if es_adicional_negocio
            else "ignorado_no_negocio"
        ),
    }
