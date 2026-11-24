"""Protocolo atómico de apertura ensayable. NO activa candidatas ni producción.

La aprobación humana y la activación real requieren una implementación posterior revisada.
No se publica este ensayo como endpoint ni como comando del instalador.
"""
import hashlib
import json
from datetime import datetime, date, timezone, timedelta
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from pos_cobros import SolicitudContable, Centavos
from pos_saldo_unificado import CAJAS, Saldo, administrador, repetir


class DeudaEnsayo(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    concepto: str = Field(min_length=1, max_length=120)
    importe_centavos: Centavos
    vencimiento: date
    caja: Literal['comidas']


class AperturaEnsayo(SolicitudContable):
    consentimiento: Literal['ENSAYO FICTICIO SIN ACTIVACION PRODUCTIVA']
    instancia: str = Field(min_length=1, max_length=120)
    version_codigo: str = Field(pattern=r'^[0-9a-f]{40}$')
    catalogo_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    evidencia_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    responsable: str = Field(min_length=1, max_length=120)
    corte: datetime
    saldos: dict[str, Saldo]
    postres: dict[int, Saldo]
    deuda_tarjeta: DeudaEnsayo | None
    fiados_previos_centavos: Literal[0]
    bebidas_sin_existencias: Literal[True]
    conciliacion_sin_duplicados: Literal[True]
    sin_operaciones_en_transito: Literal[True]
    modelo_rotiseria_aceptado: Literal[True]

    @model_validator(mode='after')
    def validar(self):
        if set(self.saldos) != set(CAJAS):
            raise ValueError('Se requieren exactamente los dos saldos unificados.')
        if (self.corte.utcoffset() != timedelta(hours=-3)
                or self.corte > datetime.now(timezone.utc)):
            raise ValueError('Corte efectivo no futuro con zona de Buenos Aires (-03:00).')
        if any(cantidad > 1_000_000 for cantidad in self.postres.values()):
            raise ValueError('Conteo fuera de rango.')
        if self.deuda_tarjeta and self.deuda_tarjeta.vencimiento < self.corte.date():
            raise ValueError('Vencimiento anterior al corte: requiere revisión separada.')
        return self


def huella_catalogo(db):
    # Vincula el ensayo al catálogo exacto consultado, sin incluir existencias.
    filas = db.execute('''SELECT id_producto,nombre,categoria,precio_venta,controla_stock
        FROM productos ORDER BY id_producto''').fetchall()
    return hashlib.sha256(json.dumps(filas, ensure_ascii=False).encode()).hexdigest()


def ensayar_apertura(db, datos, usuario):
    """Dueño de su transacción IMMEDIATE: todo o nada, incluso ante fallos SQL.

    Rechaza explícitamente la identidad de candidata aunque alguien cambie application_id.
    Sólo admite la identidad de Preproducción ficticia y una base sin operaciones.
    """
    from pos_preproduccion import MODO
    from pos_simulacion import ID_SQLITE_SIMULACION
    from pos_caja_diaria import ahora_local
    administrador(usuario)
    if db.in_transaction:
        raise ValueError('El ensayo necesita una conexión sin transacción previa.')
    with db:
        db.execute('BEGIN IMMEDIATE')
        if (db.execute('PRAGMA application_id').fetchone()[0] != ID_SQLITE_SIMULACION
                or db.execute("SELECT 1 FROM sqlite_schema WHERE name='candidata_corte'").fetchone()):
            raise HTTPException(409, 'Sólo se admite una base ficticia; candidata bloqueada.')
        if db.execute('SELECT modo,instalacion FROM pos_preproduccion').fetchall() != [(MODO, datos.instancia)]:
            raise HTTPException(409, 'Instancia ficticia incorrecta.')
        if not db.execute('SELECT 1 FROM usuarios_pos WHERE id_usuario=? AND rol=? AND activo=1',
                          (usuario['id_usuario'], 'admin')).fetchone():
            raise HTTPException(403, 'Responsable inactivo o ajeno.')
        solicitud = datos.model_dump_json()
        previo = repetir(db, 'pos_apertura_ensayo', solicitud, usuario, datos)
        if previo is not None:
            return previo
        if db.execute('SELECT 1 FROM pos_apertura_ensayo').fetchone():
            raise HTTPException(409, 'La apertura ya fue registrada.')
        configuracion = {'productos', 'adicionales_catalogo', 'usuarios_pos', 'sesiones_pos',
                         'pos_catalogo_entrenamiento', 'pos_adicionales_producto',
                         'pos_inicio_caja_diaria', 'pos_inicio_contable', 'pos_preproduccion',
                         'pos_puente_ficticio', 'pos_saldos_iniciales', 'pos_stock_progresivo'}
        # Lista permitida cerrada: cualquier libro legado, pendiente o tabla nueva con
        # datos impide el ensayo. Las tablas optativas ausentes no se crean al consultar.
        tablas = [t for t, in db.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'")
                  if t not in configuracion]
        if any(db.execute('SELECT COUNT(*) FROM "' + t.replace('"', '""') + '"').fetchone()[0] for t in tablas):
            raise HTTPException(409, 'El ensayo requiere una base nueva sin operaciones ni pendientes.')
        if db.execute('SELECT 1 FROM pos_saldos_iniciales WHERE saldo_centavos IS NOT NULL').fetchone():
            raise HTTPException(409, 'Los saldos ya fueron establecidos.')
        if huella_catalogo(db) != datos.catalogo_sha256:
            raise HTTPException(409, 'Catálogo cambiado desde su revisión.')
        postres = {p for p, in db.execute("SELECT id_producto FROM productos WHERE lower(trim(categoria))='postres'")}
        if set(datos.postres) != postres:
            raise HTTPException(409, 'Se requiere el conteo de cada SKU de postres, incluidos ceros.')
        if db.execute("SELECT 1 FROM productos WHERE lower(trim(categoria)) IN ('postres','bebidas') AND controla_stock<>1").fetchone():
            raise HTTPException(409, 'Postres y bebidas requieren control por SKU.')
        if db.execute('SELECT 1 FROM productos WHERE stock<>0').fetchone():
            raise HTTPException(409, 'La base de ensayo debe comenzar sin existencias.')
        corte = datos.corte.isoformat()
        db.executemany('UPDATE pos_saldos_iniciales SET saldo_centavos=?,corte=?,responsable=? WHERE caja=?',
                       [(datos.saldos[c],corte,datos.responsable,c) for c in CAJAS])
        db.executemany('UPDATE productos SET stock=? WHERE id_producto=?',
                       [(cantidad,p) for p,cantidad in datos.postres.items()])
        db.execute('UPDATE pos_stock_progresivo SET habilitado=0')
        if datos.deuda_tarjeta:
            d = datos.deuda_tarjeta
            db.execute('''INSERT INTO pos_deudas_apertura(caja,concepto,importe_centavos,vencimiento,modalidad)
                VALUES (?,?,?,?,'pago_unico')''', (d.caja,d.concepto,d.importe_centavos,d.vencimiento.isoformat()))
        db.execute('UPDATE pos_inicio_contable SET fecha=? WHERE id=1', (datos.corte.date().isoformat(),))
        resultado = {'ensayo': True, 'habilitacion_productiva': False, 'instancia': datos.instancia,
                     'corte': corte, 'id_solicitud': str(datos.id_solicitud)}
        db.execute('INSERT INTO pos_apertura_ensayo VALUES (1,?,?,?,?,?)',
                   (str(datos.id_solicitud),solicitud,usuario['id_usuario'],ahora_local(),json.dumps(resultado)))
        return resultado
