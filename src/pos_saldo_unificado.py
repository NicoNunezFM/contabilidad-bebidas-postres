"""Modelo optativo para bases nuevas. No migra ni habilita instalaciones."""
import json
import hashlib
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import HTTPException
from pydantic import Field

from pos_cobros import SolicitudContable, Centavos

CAJAS = ('comidas', 'bebidas_postres')
Saldo = Annotated[int, Field(strict=True, ge=0, le=310_000_000_000_000_000)]


def existe(db):
    return bool(db.execute("SELECT 1 FROM sqlite_schema WHERE name='pos_saldos_iniciales'").fetchone())


def crear_esquema(db):
    from pos_simulacion import ID_SQLITE_SIMULACION
    from pos_compras_caja import preparar_compras_caja
    if db.execute('PRAGMA application_id').fetchone()[0] != ID_SQLITE_SIMULACION:
        raise ValueError('El modelo requiere un esquema nuevo de preparación.')
    if any(db.execute(f'SELECT COUNT(*) FROM {tabla}').fetchone()[0]
           for tabla in ('pos_ventas_simuladas', 'ventas', 'compras', 'gastos')):
        raise ValueError('No se transforma una instalación con operaciones previas.')
    preparar_compras_caja(db)
    # Sólo el preparador de una candidata NUEVA y los fixtures ficticios lo invocan.
    db.execute('''CREATE TABLE pos_saldos_iniciales (
        caja TEXT PRIMARY KEY CHECK(caja IN ('comidas','bebidas_postres')),
        saldo_centavos INTEGER CHECK(saldo_centavos >= 0),
        corte TEXT, responsable TEXT,
        CHECK((saldo_centavos IS NULL AND corte IS NULL AND responsable IS NULL)
           OR (saldo_centavos IS NOT NULL AND corte IS NOT NULL AND responsable IS NOT NULL)))''')
    db.executemany('INSERT INTO pos_saldos_iniciales(caja) VALUES (?)', [(c,) for c in CAJAS])
    db.execute('''CREATE TABLE pos_deudas_apertura (
        id_deuda INTEGER PRIMARY KEY, caja TEXT NOT NULL REFERENCES pos_saldos_iniciales,
        concepto TEXT NOT NULL, importe_centavos INTEGER NOT NULL CHECK(importe_centavos>0),
        vencimiento TEXT NOT NULL, modalidad TEXT NOT NULL CHECK(modalidad='pago_unico'))''')
    db.execute('''CREATE TABLE pos_pagos_deuda_apertura (
        id_pago INTEGER PRIMARY KEY, id_deuda INTEGER NOT NULL REFERENCES pos_deudas_apertura,
        id_solicitud TEXT NOT NULL UNIQUE, solicitud TEXT NOT NULL,
        id_usuario INTEGER NOT NULL REFERENCES usuarios_pos, fecha TEXT NOT NULL,
        importe_centavos INTEGER NOT NULL CHECK(importe_centavos>0), resultado TEXT NOT NULL)''')
    db.execute('''CREATE TABLE pos_stock_progresivo (
        id_producto INTEGER PRIMARY KEY REFERENCES productos,
        habilitado INTEGER NOT NULL CHECK(habilitado IN (0,1)))''')
    db.execute("INSERT INTO pos_stock_progresivo SELECT id_producto, 0 FROM productos WHERE lower(trim(categoria))='bebidas'")
    db.execute('''CREATE TABLE pos_validaciones_stock (
        id_solicitud TEXT PRIMARY KEY, id_producto INTEGER NOT NULL REFERENCES productos,
        id_usuario INTEGER NOT NULL REFERENCES usuarios_pos, fecha TEXT NOT NULL,
        referencia TEXT NOT NULL, cantidad INTEGER NOT NULL CHECK(cantidad>0))''')
    db.execute('''CREATE TABLE pos_reversos_deuda_apertura (
        id_pago INTEGER PRIMARY KEY REFERENCES pos_pagos_deuda_apertura,
        id_solicitud TEXT NOT NULL UNIQUE, solicitud TEXT NOT NULL,
        id_usuario INTEGER NOT NULL REFERENCES usuarios_pos, fecha TEXT NOT NULL,
        resultado TEXT NOT NULL)''')
    db.execute('''CREATE TABLE pos_cierres_unificados (
        id_cierre INTEGER PRIMARY KEY, caja TEXT NOT NULL REFERENCES pos_saldos_iniciales,
        secuencia INTEGER NOT NULL CHECK(secuencia>0),
        id_solicitud TEXT NOT NULL UNIQUE, solicitud TEXT NOT NULL,
        id_usuario INTEGER NOT NULL REFERENCES usuarios_pos, fecha TEXT NOT NULL,
        resultado TEXT NOT NULL, UNIQUE(caja,secuencia))''')
    db.execute('''CREATE TABLE pos_apertura_ensayo (
        id INTEGER PRIMARY KEY CHECK(id=1), id_solicitud TEXT NOT NULL UNIQUE,
        solicitud TEXT NOT NULL, id_usuario INTEGER NOT NULL REFERENCES usuarios_pos,
        fecha TEXT NOT NULL, resultado TEXT NOT NULL)''')
    db.execute('''CREATE TRIGGER pago_deuda_activo BEFORE INSERT ON pos_pagos_deuda_apertura
        WHEN EXISTS(SELECT 1 FROM pos_pagos_deuda_apertura p WHERE p.id_deuda=NEW.id_deuda
          AND NOT EXISTS(SELECT 1 FROM pos_reversos_deuda_apertura r WHERE r.id_pago=p.id_pago))
        BEGIN SELECT RAISE(ABORT, 'La deuda ya tiene un pago vigente'); END''')
    for tabla in ('pos_pagos_deuda_apertura', 'pos_reversos_deuda_apertura',
                  'pos_cierres_unificados', 'pos_apertura_ensayo'):
        for accion in ('UPDATE', 'DELETE'):
            db.execute(f'''CREATE TRIGGER inmutable_{tabla}_{accion} BEFORE {accion} ON {tabla}
                BEGIN SELECT RAISE(ABORT, 'Registro auditable inmutable'); END''')


def exigir(db):
    if not existe(db):
        raise HTTPException(404, 'Saldo unificado no preparado en esta instalación.')
    requeridas = {'pos_reversos_deuda_apertura','pos_cierres_unificados','pos_apertura_ensayo'}
    tablas = {t for t, in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
    if not requeridas.issubset(tablas):
        raise HTTPException(409, 'Esquema anterior. Prepará una base ficticia nueva; no se migra esta instalación.')
    if db.execute('SELECT COUNT(*) FROM pos_saldos_iniciales WHERE corte IS NOT NULL').fetchone()[0] != 2:
        raise HTTPException(409, 'Corte y saldos pendientes de aprobación. Operaciones bloqueadas.')
    cortes = db.execute('SELECT corte FROM pos_saldos_iniciales').fetchall()
    try:
        momentos = [datetime.fromisoformat(corte) for corte, in cortes]
        if len(set(momentos)) != 1 or momentos[0].utcoffset() is None or momentos[0] > datetime.now(timezone.utc):
            raise ValueError('Corte inválido')
    except (ValueError, TypeError):
        raise HTTPException(409, 'Se requiere un único instante efectivo con zona horaria, no futuro.')


def validar_pago(db, receptor, medio):
    receptor = receptor or ''
    unificado = receptor.endswith('_saldo_unificado') or medio == 'saldo_unificado'
    if unificado:
        exigir(db)
    if existe(db) and not (receptor in [c + '_saldo_unificado' for c in CAJAS]
                           and medio == 'saldo_unificado'):
        raise HTTPException(409, 'Usá el saldo unificado de la caja responsable.')


def resumen(db):
    from pos_cobros import periodo_abierto
    from pos_delivery import resumen_delivery
    exigir(db)
    reparto = resumen_delivery(db, periodo_abierto(db))
    cajas = {}
    for caja, inicial, corte, responsable in db.execute("SELECT * FROM pos_saldos_iniciales ORDER BY CASE caja WHEN 'comidas' THEN 0 ELSE 1 END"):
        # Cobros y sus reversos, transferencias y delivery se registran una sola vez en este libro.
        movimientos = db.execute('SELECT COALESCE(SUM(importe_centavos),0) FROM pos_movimientos_simulados WHERE caja=? AND receptor NOT LIKE ? AND receptor<>?',
                                 (caja, '%_en_transito', 'repartidor_directo')).fetchone()[0]
        manual = db.execute('''SELECT COALESCE(SUM(d.importe_centavos),0)
            FROM pos_diario_caja d JOIN pos_jornadas_caja j USING(id_jornada)
            WHERE j.caja=? AND d.tipo IN ('gasto','retiro','aporte','transferencia')
              AND d.id_movimiento_pos IS NULL
              AND NOT EXISTS(SELECT 1 FROM pos_compras_caja p WHERE p.id_diario=d.id_evento)''', (caja,)).fetchone()[0]
        compras = db.execute('''SELECT COALESCE(SUM(CASE WHEN evento='alta' THEN pagado_centavos ELSE -pagado_centavos END),0)
            FROM pos_compras_caja WHERE pagador LIKE ?''', (caja + '_%',)).fetchone()[0]
        pagos = db.execute('''SELECT COALESCE(SUM(p.importe_centavos),0) FROM pos_pagos_deuda_apertura p
            JOIN pos_deudas_apertura d USING(id_deuda) WHERE d.caja=?
            AND NOT EXISTS(SELECT 1 FROM pos_reversos_deuda_apertura r WHERE r.id_pago=p.id_pago)''', (caja,)).fetchone()[0]
        # Custodia de terceros no se ofrece como saldo propio ni se cuenta como venta.
        custodia = sum(r['custodia_centavos'] for r in reparto if r['receptor'].startswith(caja + '_'))
        cajas[caja] = {'saldo_centavos': inicial + movimientos + manual - compras - pagos - custodia,
                      'custodia_reparto_centavos': custodia, 'corte': corte}
    deudas = [dict(zip(('id_deuda','caja','concepto','vencimiento','pendiente_centavos'), f)) for f in db.execute('''
        SELECT d.id_deuda,d.caja,d.concepto,d.vencimiento,d.importe_centavos-COALESCE(p.importe_centavos,0)
        FROM pos_deudas_apertura d LEFT JOIN pos_pagos_deuda_apertura p ON p.id_deuda=d.id_deuda
          AND NOT EXISTS(SELECT 1 FROM pos_reversos_deuda_apertura r WHERE r.id_pago=p.id_pago)
        ORDER BY d.id_deuda''')]
    stock = [dict(zip(('id_producto','nombre','categoria','cantidad','habilitado'), f)) for f in db.execute('''
        SELECT p.id_producto,p.nombre,p.categoria,p.stock,
            CASE WHEN lower(trim(p.categoria))='postres' THEN 1 ELSE COALESCE(s.habilitado,0) END
        FROM productos p LEFT JOIN pos_stock_progresivo s USING(id_producto)
        WHERE lower(trim(p.categoria)) IN ('postres','bebidas') ORDER BY p.nombre''')]
    pagos = [dict(zip(('id_pago','id_deuda','importe_centavos','fecha','id_usuario','revertido'), f))
             for f in db.execute('''SELECT p.id_pago,p.id_deuda,p.importe_centavos,p.fecha,p.id_usuario,
                 EXISTS(SELECT 1 FROM pos_reversos_deuda_apertura r WHERE r.id_pago=p.id_pago)
                 FROM pos_pagos_deuda_apertura p ORDER BY p.id_pago''')]
    return {'cajas': cajas, 'deudas': deudas, 'pagos_deuda': pagos, 'stock': stock, 'modo': 'saldo_unificado'}


class PagoDeuda(SolicitudContable):
    importe_centavos: Centavos
    motivo: str = Field(min_length=1, max_length=300)


def pagar_deuda(db, numero, datos, usuario):
    from pos_caja_diaria import ahora_local
    exigir(db)
    if usuario['rol'] != 'admin':
        raise HTTPException(403, 'Administración debe registrar el pago de deuda.')
    solicitud = json.dumps({'id_deuda': numero, **datos.model_dump(mode='json')}, sort_keys=True)
    previo = db.execute('SELECT solicitud,id_usuario,resultado FROM pos_pagos_deuda_apertura WHERE id_solicitud=?', (str(datos.id_solicitud),)).fetchone()
    if previo:
        if previo[:2] != (solicitud, usuario['id_usuario']):
            raise HTTPException(409, 'La solicitud corresponde a otro pago.')
        return json.loads(previo[2])
    deuda = db.execute('SELECT caja,importe_centavos FROM pos_deudas_apertura WHERE id_deuda=?', (numero,)).fetchone()
    if not deuda:
        raise HTTPException(404, 'Deuda no encontrada.')
    if db.execute('''SELECT 1 FROM pos_pagos_deuda_apertura p WHERE id_deuda=?
        AND NOT EXISTS(SELECT 1 FROM pos_reversos_deuda_apertura r WHERE r.id_pago=p.id_pago)''', (numero,)).fetchone():
        raise HTTPException(409, 'La deuda ya está cancelada.')
    caja, importe = deuda
    if datos.importe_centavos != importe:
        raise HTTPException(409, 'Esta deuda requiere pago único por el saldo completo.')
    if resumen(db)['cajas'][caja]['saldo_centavos'] < importe:
        raise HTTPException(409, 'Saldo insuficiente en la caja responsable.')
    id_pago = db.execute('SELECT COALESCE(MAX(id_pago),0)+1 FROM pos_pagos_deuda_apertura').fetchone()[0]
    resultado = {'id_pago': id_pago, 'id_deuda': numero, 'caja': caja, 'pagado_centavos': importe, 'pendiente_centavos': 0}
    db.execute('''INSERT INTO pos_pagos_deuda_apertura
        (id_pago,id_deuda,id_solicitud,solicitud,id_usuario,fecha,importe_centavos,resultado) VALUES (?,?,?,?,?,?,?,?)''',
        (id_pago,numero,str(datos.id_solicitud),solicitud,usuario['id_usuario'],ahora_local(),importe,json.dumps(resultado)))
    return resultado


class ReversoDeuda(SolicitudContable):
    motivo: str = Field(min_length=1, max_length=300)


def repetir(db, tabla, solicitud, usuario, datos):
    previo = db.execute(f'SELECT solicitud,id_usuario,resultado FROM {tabla} WHERE id_solicitud=?',
                        (str(datos.id_solicitud),)).fetchone()
    if previo:
        if previo[:2] != (solicitud, usuario['id_usuario']):
            raise HTTPException(409, 'La solicitud corresponde a otra operación o responsable.')
        return json.loads(previo[2])


def administrador(usuario):
    if usuario['rol'] != 'admin':
        raise HTTPException(403, 'Se requiere Administración.')


def revertir_deuda(db, numero, datos, usuario):
    """El llamador mantiene BEGIN IMMEDIATE; nunca borra ni modifica el pago original."""
    from pos_caja_diaria import ahora_local
    exigir(db)
    administrador(usuario)
    solicitud = json.dumps({'id_pago': numero, **datos.model_dump(mode='json')}, sort_keys=True)
    previo = repetir(db, 'pos_reversos_deuda_apertura', solicitud, usuario, datos)
    if previo is not None:
        return previo
    pago = db.execute('''SELECT p.id_deuda,d.caja,p.importe_centavos FROM pos_pagos_deuda_apertura p
        JOIN pos_deudas_apertura d USING(id_deuda) WHERE p.id_pago=?''', (numero,)).fetchone()
    if not pago:
        raise HTTPException(404, 'Pago no encontrado.')
    if db.execute('SELECT 1 FROM pos_reversos_deuda_apertura WHERE id_pago=?', (numero,)).fetchone():
        raise HTTPException(409, 'El pago ya fue revertido.')
    deuda, caja, importe = pago
    resultado = {'id_pago': numero, 'id_deuda': deuda, 'caja': caja,
                 'reintegrado_centavos': importe, 'pendiente_centavos': importe}
    db.execute('INSERT INTO pos_reversos_deuda_apertura VALUES (?,?,?,?,?,?)',
               (numero,str(datos.id_solicitud),solicitud,usuario['id_usuario'],ahora_local(),json.dumps(resultado)))
    return resultado


def conciliacion(db):
    estado = resumen(db)
    # La revisión cambia aun si dos movimientos compensados dejan el mismo saldo.
    libros = {t: db.execute(f'SELECT * FROM {t} ORDER BY rowid').fetchall() for t in (
        'pos_movimientos_simulados', 'pos_diario_caja', 'pos_compras_caja',
        'pos_pagos_deuda_apertura', 'pos_reversos_deuda_apertura', 'pos_cierres_unificados')}
    revision = hashlib.sha256(json.dumps([estado, libros], sort_keys=True).encode()).hexdigest()
    cierres = [json.loads(r) for r, in db.execute('SELECT resultado FROM pos_cierres_unificados ORDER BY id_cierre')]
    return {'revision': revision, 'cajas': estado['cajas'], 'cierres': cierres}


class CierreUnificado(ReversoDeuda):
    caja: Literal['comidas', 'bebidas_postres']
    revision: str = Field(pattern=r'^[0-9a-f]{64}$')
    secuencia: int = Field(strict=True, gt=0)
    saldo_contado_centavos: Saldo
    custodia_contada_centavos: Saldo
    referencia: str = Field(min_length=1, max_length=120)


def cerrar_unificado(db, datos, usuario):
    from pos_caja_diaria import ahora_local
    exigir(db)
    administrador(usuario)
    solicitud = datos.model_dump_json()
    previo = repetir(db, 'pos_cierres_unificados', solicitud, usuario, datos)
    if previo is not None:
        return previo
    estado = conciliacion(db)
    secuencia = db.execute('SELECT COALESCE(MAX(secuencia),0)+1 FROM pos_cierres_unificados WHERE caja=?',
                          (datos.caja,)).fetchone()[0]
    if datos.revision != estado['revision'] or datos.secuencia != secuencia:
        raise HTTPException(409, 'La caja cambió. Volvé a conciliar y confirmar el conteo.')
    caja = estado['cajas'][datos.caja]
    resultado = {'caja': datos.caja, 'secuencia': secuencia, 'fecha': ahora_local(),
                 'revision': datos.revision, 'saldo_libro_centavos': caja['saldo_centavos'],
                 'saldo_contado_centavos': datos.saldo_contado_centavos,
                 'diferencia_centavos': datos.saldo_contado_centavos-caja['saldo_centavos'],
                 'custodia_libro_centavos': caja['custodia_reparto_centavos'],
                 'custodia_contada_centavos': datos.custodia_contada_centavos,
                 'diferencia_custodia_centavos': datos.custodia_contada_centavos-caja['custodia_reparto_centavos'],
                 'id_usuario': usuario['id_usuario'], 'motivo': datos.motivo, 'referencia': datos.referencia}
    db.execute('''INSERT INTO pos_cierres_unificados
        (caja,secuencia,id_solicitud,solicitud,id_usuario,fecha,resultado) VALUES (?,?,?,?,?,?,?)''',
        (datos.caja,secuencia,str(datos.id_solicitud),solicitud,usuario['id_usuario'],resultado['fecha'],json.dumps(resultado)))
    return resultado


def validar_stock(db, producto, categoria, stock, cantidad, controla=True):
    if not existe(db):
        return
    exigir(db)
    categoria = categoria.strip().lower()
    if categoria == 'bebidas':
        fila = db.execute('SELECT habilitado FROM pos_stock_progresivo WHERE id_producto=?', (producto,)).fetchone()
        if not fila or not fila[0]:
            raise HTTPException(409, 'Bebida sin reposición validada. No disponible para vender.')
    if categoria in ('postres','bebidas') and not controla:
        raise HTTPException(409, 'Este SKU requiere control de inventario por unidad.')
    if categoria in ('postres','bebidas') and cantidad > stock:
        raise HTTPException(409, 'Stock insuficiente por SKU. No se permite confirmar faltantes.')


class ValidarReposicion(SolicitudContable):
    cantidad: int = Field(strict=True, gt=0, le=1_000_000)
    referencia: str = Field(min_length=1, max_length=120)


def validar_reposicion(db, producto, datos, usuario):
    from pos_caja_diaria import ahora_local
    exigir(db)
    if usuario['rol'] != 'admin':
        raise HTTPException(403, 'Administración debe validar la reposición.')
    previo = db.execute('SELECT id_producto,id_usuario,referencia,cantidad FROM pos_validaciones_stock WHERE id_solicitud=?', (str(datos.id_solicitud),)).fetchone()
    if previo:
        if previo != (producto, usuario['id_usuario'], datos.referencia, datos.cantidad):
            raise HTTPException(409, 'La solicitud ya corresponde a otra validación.')
        return {'id_producto': producto, 'habilitado': True}
    fila = db.execute("SELECT stock,controla_stock FROM productos WHERE id_producto=? AND lower(trim(categoria))='bebidas'", (producto,)).fetchone()
    if fila != (datos.cantidad, 1):
        raise HTTPException(409, 'Registrá la reposición y verificá el conteo por SKU antes de habilitar.')
    db.execute('INSERT INTO pos_validaciones_stock VALUES (?,?,?,?,?,?)',
               (str(datos.id_solicitud),producto,usuario['id_usuario'],ahora_local(),datos.referencia,datos.cantidad))
    db.execute('INSERT INTO pos_stock_progresivo VALUES (?,1) ON CONFLICT(id_producto) DO UPDATE SET habilitado=1', (producto,))
    return {'id_producto': producto, 'habilitado': True}
