require("dotenv").config();

const fs = require("fs");
const path = require("path");
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

const SEND_GROUP_WELCOME =
  String(process.env.SEND_GROUP_WELCOME || "true")
    .trim()
    .toLowerCase() === "true";

const WELCOME_STATE_PATH = path.join(
  __dirname,
  ".welcome_state.json"
);

const WELCOME_MESSAGE = [
  "*Bienvenidos a Abadion.*",
  "",
  "Desde este grupo, Abadion va a centralizar la gestión de Lo de Clau: ventas, stock, caja, movimientos y consultas.",
  "",
  "Pueden interactuar directamente con el sistema escribiendo los comandos disponibles.",
  "",
  "Para empezar, escriban *menu*."
].join("\n");

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
    return false;
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

async function enviarComandoApi(
  mensaje,
  idMensaje,
  contexto = {}
) {
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
        id_mensaje: idMensaje,
        canal: "whatsapp",
        usuario_id:
          contexto.usuario_id || null,
        usuario_numero:
          contexto.usuario_numero || null,
        grupo_id:
          contexto.grupo_id || null,
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

function cargarEstadoBienvenidas() {
  try {
    if (!fs.existsSync(WELCOME_STATE_PATH)) {
      return {};
    }

    const contenido = fs.readFileSync(
      WELCOME_STATE_PATH,
      "utf8"
    );

    const estado = JSON.parse(contenido);

    if (
      estado &&
      typeof estado === "object" &&
      !Array.isArray(estado)
    ) {
      return estado;
    }
  } catch (error) {
    console.warn(
      "No se pudo leer el estado de bienvenidas:",
      error?.message || error
    );
  }

  return {};
}

const estadoBienvenidas =
  cargarEstadoBienvenidas();

function guardarEstadoBienvenidas() {
  const temporal =
    WELCOME_STATE_PATH + ".tmp";

  fs.writeFileSync(
    temporal,
    JSON.stringify(
      estadoBienvenidas,
      null,
      2
    ),
    "utf8"
  );

  fs.renameSync(
    temporal,
    WELCOME_STATE_PATH
  );
}

async function enviarBienvenidaSiCorresponde(
  idGrupo,
  mensajeGrupo = null
) {
  if (!SEND_GROUP_WELCOME) {
    if (DEBUG_MESSAGES) {
      console.log(
        "Bienvenida omitida: SEND_GROUP_WELCOME=false."
      );
    }
    return false;
  }

  if (!ALLOW_GROUPS) {
    if (DEBUG_MESSAGES) {
      console.log(
        "Bienvenida omitida: ALLOW_GROUPS=false."
      );
    }
    return false;
  }

  if (!ALLOWED_GROUP_IDS.has(idGrupo)) {
    if (DEBUG_MESSAGES) {
      console.log(
        "Bienvenida omitida: grupo no autorizado:",
        idGrupo
      );
    }
    return false;
  }

  if (
    estadoBienvenidas[idGrupo]?.enviada
  ) {
    if (DEBUG_MESSAGES) {
      console.log(
        "Bienvenida ya enviada previamente al grupo:",
        idGrupo
      );
    }
    return false;
  }

  console.log(
    "Enviando bienvenida de Abadion al grupo:",
    idGrupo
  );

  // Evitamos getChatById porque versiones recientes de WhatsApp Web
  // pueden fallar al resolver grupos restaurados desde LocalAuth.
  // Si estamos procesando un mensaje del grupo, reply() es el camino
  // más estable; al iniciar el bot usamos client.sendMessage().
  if (
    mensajeGrupo &&
    typeof mensajeGrupo.reply === "function"
  ) {
    await mensajeGrupo.reply(
      WELCOME_MESSAGE
    );
  } else {
    await client.sendMessage(
      idGrupo,
      WELCOME_MESSAGE
    );
  }

  estadoBienvenidas[idGrupo] = {
    enviada: true,
    fecha: new Date().toISOString(),
  };

  guardarEstadoBienvenidas();

  console.log(
    "Bienvenida de Abadion enviada al grupo:",
    idGrupo
  );

  return true;
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

client.on("ready", async () => {
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

  if (ALLOW_GROUPS) {
    console.log(
      `Grupos autorizados configurados: ${ALLOWED_GROUP_IDS.size}`
    );

    if (ALLOWED_GROUP_IDS.size === 0) {
      console.warn(
        "ATENCIÓN: ALLOW_GROUPS=true pero ALLOWED_GROUP_IDS está vacío. " +
        "Los mensajes de grupos serán ignorados hasta configurar un grupo."
      );
    }
  }

  console.log(
    `Diagnóstico de mensajes: ${DEBUG_MESSAGES ? "activado" : "desactivado"}`
  );

  console.log(
    `Bienvenida automática: ${SEND_GROUP_WELCOME ? "activada" : "desactivada"}`
  );

  if (
    ALLOW_GROUPS &&
    SEND_GROUP_WELCOME
  ) {
    if (DEBUG_MESSAGES) {
      console.log(
        "IDs de grupos autorizados:",
        Array.from(ALLOWED_GROUP_IDS)
      );
      console.log(
        "Estado local de bienvenidas:",
        estadoBienvenidas
      );
    }

    for (
      const idGrupo
      of ALLOWED_GROUP_IDS
    ) {
      try {
        await enviarBienvenidaSiCorresponde(
          idGrupo
        );
      } catch (error) {
        console.error(
          "No se pudo enviar la bienvenida al grupo:",
          idGrupo,
          error?.stack || error?.message || error
        );
      }
    }
  }
});

async function procesarMensajeEntrante(message, origenEvento) {
  try {
    if (DEBUG_MESSAGES) {
      console.log(
        `[EVENTO ${origenEvento}]`
      );
    }
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

    if (esGrupo(message)) {
      try {
        await enviarBienvenidaSiCorresponde(
          message.from,
          message
        );
      } catch (error) {
        console.error(
          "No se pudo enviar la bienvenida al recibir mensaje de grupo:",
          error?.stack || error?.message || error
        );
      }
    }

    const remitente =
      await resolverNumeroRemitente(message);

    if (DEBUG_MESSAGES) {
      console.log(
        "Remitente resuelto:",
        JSON.stringify(remitente)
      );
    }

    const mensajeDeGrupo = esGrupo(message);

    if (
      !mensajeDeGrupo &&
      !numeroAutorizado(remitente.numero)
    ) {
      console.warn(
        "Remitente no autorizado.",
        "Número resuelto:",
        remitente.numero || "(sin resolver)",
        "ID:",
        remitente.identificador || "(sin ID)"
      );
      return;
    }

    if (mensajeDeGrupo && DEBUG_MESSAGES) {
      console.log(
        "Mensaje aceptado por pertenecer a un grupo autorizado:",
        message.from
      );
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
      await enviarComandoApi(
        texto,
        idMensaje,
        {
          usuario_id:
            remitente.identificador || null,
          usuario_numero:
            remitente.numero || null,
          grupo_id:
            mensajeDeGrupo
              ? message.from
              : null,
        }
      );

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
}

client.on("message", async (message) => {
  await procesarMensajeEntrante(
    message,
    "message"
  );
});

client.on("message_create", async (message) => {
  await procesarMensajeEntrante(
    message,
    "message_create"
  );
});

client.on("message_ciphertext", (message) => {
  if (!DEBUG_MESSAGES) {
    return;
  }

  console.log(
    "[EVENTO message_ciphertext]",
    JSON.stringify({
      from: message.from,
      author: message.author || null,
      fromMe: Boolean(message.fromMe),
      type: message.type,
    })
  );
});

client.on("change_state", (estado) => {
  console.log(
    "Estado de WhatsApp Web:",
    estado
  );
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
