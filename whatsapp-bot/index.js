require("dotenv").config();

const qrcode = require("qrcode-terminal");
const { Client, LocalAuth } = require("whatsapp-web.js");

const API_URL =
  process.env.API_URL ||
  "http://127.0.0.1:8000/comandos";

const API_TIMEOUT_MS = Number(
  process.env.API_TIMEOUT_MS || 10000
);

const ALLOW_GROUPS =
  String(process.env.ALLOW_GROUPS || "false")
    .trim()
    .toLowerCase() === "true";

const DEBUG_MESSAGES =
  String(process.env.DEBUG_MESSAGES || "true")
    .trim()
    .toLowerCase() === "true";

function soloDigitos(valor) {
  return String(valor || "").replace(/\D/g, "");
}

function leerLista(valor) {
  return String(valor || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

const ALLOWED_NUMBERS = new Set(
  leerLista(process.env.ALLOWED_NUMBERS)
    .map(soloDigitos)
    .filter(Boolean)
);

const ALLOWED_GROUP_IDS = new Set(
  leerLista(process.env.ALLOWED_GROUP_IDS)
);

const procesados = new Set();
const ordenProcesados = [];
const MAX_PROCESADOS = 1000;

function recordarMensaje(idMensaje) {
  if (!idMensaje || procesados.has(idMensaje)) {
    return false;
  }

  procesados.add(idMensaje);
  ordenProcesados.push(idMensaje);

  if (ordenProcesados.length > MAX_PROCESADOS) {
    const masAntiguo = ordenProcesados.shift();
    procesados.delete(masAntiguo);
  }

  return true;
}

function esGrupo(message) {
  return String(message.from || "").endsWith("@g.us");
}

function identificadorRemitente(message) {
  return String(
    message.author ||
    message.from ||
    ""
  );
}

function variantesNumero(numero) {
  const limpio = soloDigitos(numero);
  const variantes = new Set();

  if (!limpio) {
    return variantes;
  }

  variantes.add(limpio);

  // En Argentina WhatsApp puede exponer el móvil con o sin el 9.
  if (limpio.startsWith("549")) {
    variantes.add("54" + limpio.slice(3));
  } else if (
    limpio.startsWith("54") &&
    !limpio.startsWith("549")
  ) {
    variantes.add("549" + limpio.slice(2));
  }

  return variantes;
}

async function resolverNumeroRemitente(message) {
  const identificador = identificadorRemitente(message);

  if (!identificador) {
    return {
      numero: "",
      identificador: "",
      metodo: "sin_identificador",
    };
  }

  if (!identificador.endsWith("@lid")) {
    return {
      numero: soloDigitos(
        identificador.split("@")[0]
      ),
      identificador,
      metodo: "jid_directo",
    };
  }

  // WhatsApp está migrando algunos chats a IDs @lid.
  // Intentamos resolverlos al número telefónico real.
  try {
    if (
      typeof client.getContactLidAndPhone ===
      "function"
    ) {
      const resultados =
        await client.getContactLidAndPhone([
          identificador,
        ]);

      const phoneId =
        resultados?.[0]?.pn || "";

      const numero = soloDigitos(
        String(phoneId).split("@")[0]
      );

      if (numero) {
        return {
          numero,
          identificador,
          metodo: "lid_a_phone",
        };
      }
    }
  } catch (error) {
    if (DEBUG_MESSAGES) {
      console.warn(
        "No se pudo resolver @lid con getContactLidAndPhone:",
        error?.message || error
      );
    }
  }

  // Fallback para versiones/cuentas donde la resolución LID falla.
  try {
    const contacto = await message.getContact();

    const numero = soloDigitos(
      contacto?.number ||
      contacto?.id?.user ||
      ""
    );

    if (numero) {
      return {
        numero,
        identificador,
        metodo: "contacto",
      };
    }
  } catch (error) {
    if (DEBUG_MESSAGES) {
      console.warn(
        "No se pudo resolver el contacto del mensaje:",
        error?.message || error
      );
    }
  }

  return {
    numero: "",
    identificador,
    metodo: "lid_sin_resolver",
  };
}

function grupoAutorizado(message) {
  if (!esGrupo(message)) {
    return true;
  }

  if (!ALLOW_GROUPS) {
    return false;
  }

  if (ALLOWED_GROUP_IDS.size === 0) {
    return true;
  }

  return ALLOWED_GROUP_IDS.has(message.from);
}

function numeroAutorizado(numero) {
  if (ALLOWED_NUMBERS.size === 0) {
    return false;
  }

  const variantes = variantesNumero(numero);

  for (const variante of variantes) {
    if (ALLOWED_NUMBERS.has(variante)) {
      return true;
    }
  }

  return false;
}

async function enviarComandoApi(mensaje) {
  const controlador = new AbortController();

  const timeout = setTimeout(
    () => controlador.abort(),
    API_TIMEOUT_MS
  );

  try {
    const respuesta = await fetch(API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        mensaje,
      }),
      signal: controlador.signal,
    });

    let datos;

    try {
      datos = await respuesta.json();
    } catch {
      throw new Error(
        `La API devolvió una respuesta no JSON (HTTP ${respuesta.status}).`
      );
    }

    return {
      status: respuesta.status,
      datos,
    };
  } finally {
    clearTimeout(timeout);
  }
}

function textoRespuestaApi(datos) {
  if (!datos || typeof datos !== "object") {
    return "La API devolvió una respuesta inválida.";
  }

  return (
    datos.respuesta ||
    datos.mensaje ||
    "La operación no devolvió un mensaje."
  );
}

const client = new Client({
  authStrategy: new LocalAuth({
    clientId: "lo-de-clau-bot",
  }),
  puppeteer: {
    headless: true,
  },
});

client.on("qr", (qr) => {
  console.log(
    "\nEscaneá este QR desde WhatsApp > Dispositivos vinculados:\n"
  );

  qrcode.generate(qr, {
    small: true,
  });
});

client.on("authenticated", () => {
  console.log("WhatsApp autenticado.");
});

client.on("auth_failure", (mensaje) => {
  console.error(
    "Falló la autenticación de WhatsApp:",
    mensaje
  );
});

client.on("ready", () => {
  console.log("Bot de WhatsApp listo.");

  if (ALLOWED_NUMBERS.size === 0) {
    console.warn(
      "ATENCIÓN: ALLOWED_NUMBERS está vacío. " +
      "El bot no procesará mensajes hasta configurarlo."
    );
  } else {
    console.log(
      `Números autorizados configurados: ${ALLOWED_NUMBERS.size}`
    );
  }

  console.log(
    `API configurada: ${API_URL}`
  );

  console.log(
    `Grupos: ${ALLOW_GROUPS ? "habilitados" : "deshabilitados"}`
  );

  console.log(
    `Diagnóstico de mensajes: ${DEBUG_MESSAGES ? "activado" : "desactivado"}`
  );
});

client.on("message", async (message) => {
  try {
    if (DEBUG_MESSAGES) {
      console.log(
        "[RX]",
        JSON.stringify({
          from: message.from,
          author: message.author || null,
          fromMe: Boolean(message.fromMe),
          type: message.type,
          body: String(message.body || ""),
        })
      );
    }

    if (message.fromMe) {
      if (DEBUG_MESSAGES) {
        console.log(
          "Mensaje ignorado porque fromMe=true."
        );
      }
      return;
    }

    if (
      message.from === "status@broadcast" ||
      String(message.from || "").endsWith("@newsletter")
    ) {
      if (DEBUG_MESSAGES) {
        console.log(
          "Estado/newsletter ignorado."
        );
      }
      return;
    }

    if (!grupoAutorizado(message)) {
      if (DEBUG_MESSAGES) {
        console.log(
          "Mensaje de grupo ignorado por configuración."
        );
      }
      return;
    }

    const remitente =
      await resolverNumeroRemitente(message);

    if (DEBUG_MESSAGES) {
      console.log(
        "Remitente resuelto:",
        JSON.stringify(remitente)
      );
    }

    if (!numeroAutorizado(remitente.numero)) {
      console.warn(
        "Remitente no autorizado.",
        "Número resuelto:",
        remitente.numero || "(sin resolver)",
        "ID:",
        remitente.identificador || "(sin ID)"
      );
      return;
    }

    const texto = String(message.body || "").trim();

    if (!texto) {
      if (DEBUG_MESSAGES) {
        console.log(
          "Mensaje vacío ignorado."
        );
      }
      return;
    }

    const idMensaje =
      message.id?._serialized ||
      message.id?.id;

    if (!recordarMensaje(idMensaje)) {
      console.log(
        "Mensaje duplicado ignorado:",
        idMensaje
      );
      return;
    }

    console.log(
      `Mensaje autorizado de ${remitente.numero}: ${texto}`
    );

    const { status, datos } =
      await enviarComandoApi(texto);

    const respuesta =
      textoRespuestaApi(datos);

    console.log(
      `API HTTP ${status}: ${datos.codigo || "SIN_CODIGO"}`
    );

    await message.reply(respuesta);

    console.log(
      "Respuesta enviada a WhatsApp."
    );
  } catch (error) {
    const esTimeout =
      error?.name === "AbortError";

    console.error(
      "Error procesando mensaje:",
      error
    );

    try {
      await message.reply(
        esTimeout
          ? "La API tardó demasiado en responder. Intentá nuevamente."
          : "No pude comunicarme con el sistema del negocio. Revisá que la API esté encendida."
      );
    } catch (replyError) {
      console.error(
        "No se pudo enviar el mensaje de error:",
        replyError
      );
    }
  }
});

client.on("disconnected", (motivo) => {
  console.error(
    "WhatsApp se desconectó:",
    motivo
  );
});

process.on("SIGINT", async () => {
  console.log("\nCerrando bot...");

  try {
    await client.destroy();
  } finally {
    process.exit(0);
  }
});

console.log("Iniciando cliente de WhatsApp...");
client.initialize();
