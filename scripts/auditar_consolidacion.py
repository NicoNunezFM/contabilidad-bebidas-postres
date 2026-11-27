"""Compara objetos Git sin importar la aplicación ni abrir bases de datos.

Usa el inventario remoto fechado, no refs locales potencialmente desactualizadas.
La ascendencia no prueba equivalencia funcional: las decisiones humanas están en docs.
"""
import argparse
import ast
import json
from pathlib import Path
import subprocess
import warnings

RAIZ = Path(__file__).resolve().parents[1]
INVENTARIO = RAIZ / "docs/consolidacion-v1/inventario-github.json"


def git(*args):
    return subprocess.check_output(
        ["git", *args], cwd=RAIZ, text=True, encoding="utf-8", errors="strict"
    ).strip()


def funciones(ref, archivo):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        arbol = ast.parse(git("show", f"{ref}:{archivo}"))
    return {n.name: ast.dump(n, include_attributes=False) for n in arbol.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}


def comparar(inventario):
    referencia = inventario["referencia"]
    existentes = set(git("ls-tree", "-r", "--name-only", referencia).splitlines())
    por_rama = {}
    ramas = []
    for rama in inventario["ramas"]:
        sha = rama["sha"]
        git("cat-file", "-e", f"{sha}^{{commit}}")
        exclusivos, posteriores = map(int, git("rev-list", "--left-right", "--count",
                                               f"{sha}...{referencia}").split())
        archivos = git("diff", "--name-only", f"{referencia}...{sha}").splitlines()
        detalle = []
        for archivo in archivos:
            if not archivo.endswith(".py"):
                continue
            if archivo not in existentes:
                detalle.append({"archivo": archivo, "estado": "ausente_en_referencia"})
                continue
            a, b = funciones(sha, archivo), funciones(referencia, archivo)
            detalle.append({"archivo": archivo,
                "simbolos_ausentes": sorted(a.keys() - b.keys()),
                "simbolos_modificados": sorted(n for n in a.keys() & b.keys() if a[n] != b[n])})
        fila = {**rama, "ancestro": exclusivos == 0, "commits_exclusivos": exclusivos,
                "commits_posteriores_en_referencia": posteriores,
                "base_comun": git("merge-base", sha, referencia),
                "commits_a_revisar": git("log", "--format=%H %s", f"{referencia}..{sha}").splitlines(),
                "archivos_desde_base_comun": archivos, "comparacion_ast": detalle}
        ramas.append(fila)
        por_rama[rama["name"]] = fila
    prs = [{**pr, "ancestro": por_rama[pr["head"]]["ancestro"],
            "commits_exclusivos": por_rama[pr["head"]]["commits_exclusivos"]}
           for pr in inventario["prs"]]
    return {"referencia": referencia, "fecha_inventario": inventario["fecha"],
            "aviso": "AST y ascendencia son evidencia estructural; no una prueba de equivalencia funcional.",
            "ramas": ramas, "prs": prs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--salida", type=Path)
    parser.add_argument("--verificar", action="store_true",
                        help="Comparar contra el informe versionado; falla si no coincide")
    args = parser.parse_args()
    informe = comparar(json.loads(INVENTARIO.read_text(encoding="utf-8")))
    destino = RAIZ / "docs/consolidacion-v1/comparacion-ramas.json"
    if args.verificar:
        if informe != json.loads(destino.read_text(encoding="utf-8")):
            raise SystemExit("El informe no coincide con los objetos Git inventariados.")
    if args.salida:
        args.salida.write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ramas": len(informe["ramas"]), "prs": len(informe["prs"]),
                      "referencia": informe["referencia"], "verificado": args.verificar}))


if __name__ == "__main__":
    main()
