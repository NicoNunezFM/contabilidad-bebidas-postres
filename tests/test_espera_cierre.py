"""Cierre sin asumir que el socket y el bloqueo del archivo se liberan a la vez."""
from contextlib import contextmanager

import pytest

from scripts import abadion_preproduccion as p


def test_socket_cerrado_espera_liberacion_del_lock(monkeypatch, tmp_path):
    intentos = []
    @contextmanager
    def bloqueo(carpeta):
        intentos.append(carpeta)
        if len(intentos) < 3:
            raise ValueError('Lock aún ocupado') from OSError('Contención ficticia')
        yield
    monkeypatch.setattr(p, 'ocupado', lambda: False)
    monkeypatch.setattr(p, 'bloquear_entrenamiento', bloqueo)
    p.esperar_cierre(tmp_path, timeout=2)
    assert intentos == [tmp_path] * 3


def test_cierre_agotado_no_informa_exito_ni_fuerza_procesos(tmp_path):
    with pytest.raises(RuntimeError, match='No se forzó'):
        p.esperar_cierre(tmp_path, timeout=0)


def test_error_de_ruta_no_se_reintenta(monkeypatch, tmp_path):
    @contextmanager
    def inseguro(_):
        raise ValueError('Ruta insegura ficticia')
        yield
    monkeypatch.setattr(p, 'ocupado', lambda: False)
    monkeypatch.setattr(p, 'bloquear_entrenamiento', inseguro)
    with pytest.raises(ValueError, match='Ruta insegura'):
        p.esperar_cierre(tmp_path)
