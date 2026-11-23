# Auditoría de integración de Abadion

## Historial verificado

GitHub listó 18 PR abiertos, todos en borrador. `main` estaba en `3bead61c` y es ancestro de `1c0f218`, con 352 commits de diferencia. Los números #10, #14 y #15 corresponden a issues.

| PR | Alcance | Commit | Base declarada | Estado en #21 |
| --- | --- | --- | --- | --- |
| [#1](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/pull/1) | Abadion POS V1 · Validación de pedidos y ventas simuladas | `e8bb64d1` | `feature/pos-edicion-carrito` | Ancestro directo o transitivo |
| [#2](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/pull/2) | Abadion POS V1 · Completar el flujo simulado en la interfaz web | `a5efe435` | #1 | Ancestro directo o transitivo |
| [#3](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/pull/3) | Abadion POS · Auditoría del backend y plan de integración contable | `98f7c09e` | #2 | Ancestro directo o transitivo |
| [#4](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/pull/4) | Abadion POS · Cobros combinados, fiados y conciliación ficticia | `39e7d2f7` | #3 | Ancestro directo o transitivo |
| [#5](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/pull/5) | Abadion POS · Etapa 5 de integración contable ficticia | `9e50636f` | #4 | Ancestro directo o transitivo |
| [#6](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/pull/6) | Abadion POS · Etapa 6 de caja diaria ficticia | `03343c52` | #5 | Ancestro directo o transitivo |
| [#7](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/pull/7) | Abadion POS · Etapa 7 de contabilidad unificada ficticia | `dea47e66` | #6 | Ancestro directo o transitivo |
| [#8](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/pull/8) | Abadion Entrenamiento para Lo de Clau | `74ea4b75` | #6 | Contenido incorporado en #9. Diez commits paralelos |
| [#9](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/pull/9) | Abadion POS · Integrar contabilidad de etapa 7 con modo entrenamiento | `ba1e3267` | #7 | Ancestro directo o transitivo |
| [#11](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/pull/11) | QA de Abadion POS Integrado · Issue #10 | `7cbedc17` | #9 | QA incorporada en #13. Dos commits paralelos |
| [#12](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/pull/12) | Abadion POS · Menú táctil por familias y personalizaciones para cocina | `b89aa971` | #9 | Menú incorporado en #13. Dos commits paralelos |
| [#13](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/pull/13) | Abadion Entrenamiento · Integración de QA contable y menú táctil | `6d7e8fd7` | #9 | Ancestro directo o transitivo |
| [#16](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/pull/16) | Abadion Entrenamiento · Clientes y cuentas corrientes FIFO | `0eabad9d` | #13 | Ancestro directo o transitivo |
| [#17](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/pull/17) | Issue #15: seguimiento de pedidos y conciliación de envíos | `8a4906f0` | #16 | Ancestro directo o transitivo |
| [#18](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/pull/18) | Abadion Entrenamiento: adaptación táctil de 7 pulgadas y Chrome 101 | `59b4810d` | #17 | Ancestro directo o transitivo |
| [#19](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/pull/19) | Abadion: demo táctil estática ficticia y verificación de descarga PCBOX | `9bcab7f9` | #18 | Ancestro directo o transitivo |
| [#20](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/pull/20) | Abadion: laboratorio HTTPS autenticado con base ficticia temporal | `c95b0c8c` | #19 | Ancestro directo o transitivo |
| [#21](https://github.com/NicoNunezFM/contabilidad-bebidas-postres/pull/21) | Abadion PCBOX: laboratorio remoto protegido con Cloudflare Access | `1c0f218b` | #20 | Base de la candidata. Laboratorio remoto opcional |

Los archivos modificados por #8 coinciden en su totalidad con el alcance de #9. Los archivos de #11 y #12 están todos en el alcance de #13. Los cruces incluyen el launcher de Entrenamiento y pruebas Edge, además del HTML del POS y componentes de simulación en #8/#9. Reaplicar las ramas paralelas agregaría cambios sobre archivos que ya evolucionaron. La cobertura funcional se comprueba en la candidata.

Se eligió partir de `1c0f218` y abrir el borrador contra `feature/abadion-tablet-acceso-remoto-seguro`. El diff del borrador muestra sólo cambios de estabilización y evidencia. El commit conserva la historia acumulada de la línea integrada y ambos laboratorios. Cloudflare Access sigue siendo una opción del laboratorio remoto.


## Estabilidad contable y seguridad

- La caja legada consultaba la categoría del catálogo para ventas y compras históricas. La migración registra la categoría por operación y los disparadores capturan la de cada alta. Los importes siguen saliendo de la línea de la operación. Para datos previos, se congela la categoría disponible en el momento de migrar. Una reclasificación previa requiere evidencia independiente para reconstruirse.
- El POS mantiene las categorías de caja y los importes de las ventas en los datos registrados al confirmar. El libro de costos ficticio mantiene importes y sección por evento y revierte desde el alta original. Los cambios contables de la candidata se limitan a la clasificación legada.
- El respaldo diario usa la API de copia de SQLite y ejecuta `integrity_check` antes de publicar. La publicación del archivo definitivo es atómica dentro del mismo directorio y rechaza un destino concurrente. Un cierre abrupto puede dejar un archivo `.tmp` que queda fuera de la retención y del reconocimiento de respaldos. Los respaldos diarios generados por versiones anteriores requieren verificación antes de restaurarse.
- La revisión de rutas encontró credencial de integración en el router contable y credenciales diferenciadas en `/comandos`. En el POS, las operaciones dependen de sesión y los cambios administrativos dependen del rol. Se conservan las lecturas de catálogo permitidas por el diseño, incluidos adicionales y personalizaciones. La sesión se guarda con token hasheado y vencimiento. Los laboratorios autenticados mantienen sus controles de origen, sesiones y roles.
- La demo estática trabaja con datos ficticios propios. Los laboratorios HTTPS y Access crean SQLite ficticio temporal. Entrenamiento tiene identidad SQLite y directorio propios. El modo simulación del servidor general verifica identidad de esquema y ruta. La aplicación general puede resolver `negocio.db` por defecto. En todos los comandos de prueba se requiere una ruta ficticia explícita antes de importar o iniciar la aplicación.
- El proceso de recuperación ensaya una interrupción después de escribir venta, cobro y stock y antes del commit, seguida de validación de integridad y reintentos con el mismo identificador. Esto cubre la pérdida de un proceso en ese punto. Falta caracterizar un corte de energía y almacenamiento en el entorno destino.

## Funcionalidades y matriz de pruebas

Los módulos indicados forman parte del commit base y siguen en la candidata.

| Área conservada | Evidencia reproducible |
| --- | --- |
| Ventas, stock, compras, gastos, mermas y ajustes de inventario | `test_ventas*`, `test_compras*`, `test_gastos`, `test_inventario`, `test_movimientos_stock`, `test_stock_insumos` |
| Pedidos anónimos, preparación, confirmación y conciliación de envíos | `test_issue15_base`, `test_pos_pedidos`, `test_pos_entrenamiento` |
| Cobros en efectivo, transferencia, Mercado Pago, mixtos y fiados, con clientes y FIFO | `test_pos_cobros`, `test_pos_clientes`, `test_issue15_base` |
| Dos cajas, arqueos, cierres, reportes y diezmo | `test_cajas_secciones`, `test_pos_caja_diaria`, `test_cierres`, `test_pos_contabilidad`, `test_diezmo`, `test_api` |
| Anulaciones, devoluciones, errores, idempotencia y concurrencia | `test_idempotencia_y_anulaciones`, `test_concurrencia_contable`, `test_pos_simulacion`, `test_pos_qa_integrado` |
| Personalizaciones, menú táctil, historial y edición de precios | `test_pos_personalizaciones`, `test_pos_precios`, `test_pos_tablet_compat`, `test_pos_web` |
| Autenticación, roles, sesiones, JWT y separación de laboratorios | `test_seguridad_api`, `test_pos_usuarios`, `test_pos_entrenamiento`, `test_tablet_https`, `test_tablet_access`, `test_demo_tablet` |
| Respaldo, concurrencia de respaldo y restauración WAL sobre otro archivo | `test_backups` |

En la estación local, el arranque de Uvicorn quedó bloqueado antes de abrir Edge y `TestClient` quedó esperando en `socket.accept` al armar el bucle de Windows. Los trabajos `sqlite-ficticio` y `pos-edge` de GitHub Actions corren en máquinas distintas. Usá los resultados del commit de la candidata. La CI anterior del #21 es evidencia de la base, con 316 pruebas Python/API aprobadas, 14 omitidas en ese job y 31 aprobadas en Edge. El adaptador de WhatsApp pasó `node --check whatsapp-bot/index.js` con Node 20.20.2, compatible con el requisito declarado de Node >=18. La conexión externa de WhatsApp queda fuera de la prueba.

## Ensayo de actualización reversible con SQLite ficticio

1. Prepará dos carpetas descartables con el código del #21 y de la candidata. Usá una base de ejercicio creada desde el commit anterior y un entorno virtual por copia si cambian los requisitos. Registrá el SHA, la versión de Python y la ruta explícita de SQLite. Para validar POS y tablet, usá los launchers de práctica en sus directorios temporales.
2. Detené los escritores de la base ficticia. Localizá la base, conservá el original y generá un respaldo fuera de su directorio con `Connection.backup`. Abrí el origen con URI `mode=ro` y el destino como archivo nuevo. Validá `PRAGMA integrity_check` y `PRAGMA foreign_key_check`. Registrá conteos de ventas, compras, stock y los saldos por caja antes de actualizar.
3. Restaurá el respaldo con `Connection.backup` en un tercer archivo SQLite nuevo. Validá las mismas comprobaciones y conciliá los totales. En PowerShell, fijá `NEGOCIO_DB_PATH` en esa restauración ficticia y `PYTHON_DOTENV_DISABLED=1`. En el checkout candidato ejecutá `python -c "import sys; sys.path.insert(0, 'src'); from database import inicializar_base_de_datos; inicializar_base_de_datos()"`. Repetí la inicialización para comprobar que el registro histórico permanece fijo. En una copia de Entrenamiento usá el launcher y los comandos de activación de la guía de Entrenamiento en un perfil descartable, fuera de la carpeta de la familia.
4. Contrastá conteos y cajas, hacé una venta ficticia y verificá que la edición del catálogo afecta las altas posteriores. Al ensayar la vuelta atrás, detené los escritores, conservá la copia migrada aparte y restaurá el respaldo en un archivo nuevo. Volvé al código del SHA anterior y dirigilo a esa restauración. Conservá la copia migrada para examinar cualquier movimiento posterior al respaldo.
5. Repetí `python -m pytest -q -rs` con una ruta ficticia. Para Edge, configurá `POS_TEST_BROWSER` con la ruta a `msedge.exe` y ejecutá `python -m pytest -q tests/test_pos_web.py tests/test_demo_tablet.py tests/test_tablet_https.py`. El ensayo de hardware requiere acceso físico a la PCBOX.

## Bloqueos antes de producción

1. Completar CI de la candidata y reconciliar una jornada completa con ambas cajas partiendo de datos ficticios. Acordar el corte entre el libro legado y un futuro POS productivo. El flujo POS consolidado pertenece a práctica en este candidato.
2. Ensayar el respaldo, la restauración y el retorno de versión en el entorno destino. Acordar retención, permisos y responsable. Reconciliar categorías previas si el catálogo cambió antes de la migración.
3. Definir el alcance de credenciales, sesiones y perfiles del despliegue. Revisar las lecturas de catálogo, la configuración de TLS, el alta y revocación de cuentas y el acceso al archivo SQLite.
4. Hacer una venta y una devolución en la PCBOX física con su navegador. Si se elige acceso remoto, verificar adicionalmente el inicio de sesión de Access, conectividad desde otra red y expiración en el navegador instalado.
5. Validar con la familia el flujo habitual de pedidos y cobro, el arqueo, los importes de diezmo y la recuperación ante un cierre accidental. La prueba real de WhatsApp se reserva para un entorno autorizado aparte.

## Evidencia local

La ejecución focalizada de SQLite aprobó 30 pruebas, incluidos respaldo WAL restaurable, publicación concurrente, reintento de respaldo, concurrencia contable, ventas, compras, gastos, inventario, cierres y diezmo.
