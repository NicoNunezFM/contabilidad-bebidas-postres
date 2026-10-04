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

function remitenteDe(message) {
  const identificador =
    message.author || message.from || "";

  return soloDigitos(
    String(identificador).split("@")[0]
  );
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

function remitenteAutorizado(message) {
  if (ALLOWED_NUMBERS.size === 0) {
    return false;
  }

  return ALLOWED_NUMBERS.has(
    remitenteDe(message)
  );
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
  }

  console.log(
    `API configurada: ${API_URL}`
  );

  console.log(
    `Grupos: ${ALLOW_GROUPS ? "habilitados" : "deshabilitados"}`
  );
});

client.on("message", async (message) => {
  try {
    if (message.fromMe) {
      return;
    }

    if (
      message.from === "status@broadcast" ||
      String(message.from || "").endsWith("@newsletter")
    ) {
      return;
    }

    if (!grupoAutorizado(message)) {
      return;
    }

    if (!remitenteAutorizado(message)) {
      return;
    }

    const texto = String(message.body || "").trim();

    if (!texto) {
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
      `Mensaje de ${remitenteDe(message)}: ${texto}`
    );

    const { status, datos } =
      await enviarComandoApi(texto);

    const respuesta =
      textoRespuestaApi(datos);

    console.log(
      `API HTTP ${status}: ${datos.codigo || "SIN_CODIGO"}`
    );

    await message.reply(respuesta);
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
