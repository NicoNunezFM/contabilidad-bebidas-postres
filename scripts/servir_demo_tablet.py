"""Servidor exclusivamente estático. No usa FastAPI, SQLite ni el bot."""
import argparse
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PAGINA = Path(__file__).resolve().parents[1] / 'pos-web' / 'demo-tablet.html'
CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'none'"


class DemoHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, pagina, permitidas, **kwargs):
        self.pagina = pagina
        self.permitidas = permitidas
        super().__init__(*args, **kwargs)

    def do_GET(self):
        if self.client_address[0] not in self.permitidas:
            self.send_error(403)
            return
        if self.path.split('?', 1)[0] not in ('/', '/pos/', '/demo-tablet.html'):
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(self.pagina)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', CSP)
        self.end_headers()
        self.wfile.write(self.pagina)

    def rechazar(self):
        self.send_error(405, 'Demo estatica: operaciones deshabilitadas')

    do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_HEAD = rechazar


def crear_servidor(bind='127.0.0.1', port=8765, permitidas=()):
    handler = partial(DemoHandler, pagina=PAGINA.read_bytes(),
                      permitidas=set(permitidas) | {'127.0.0.1', bind})
    return ThreadingHTTPServer((bind, port), handler)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bind', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--allow', action='append', default=[])
    args = parser.parse_args()
    if args.bind in ('0.0.0.0', '::'):
        parser.error('Elegí una IP concreta de la PC para la demo.')
    with crear_servidor(args.bind, args.port, args.allow) as servidor:
        print(f'DEMO ESTATICA: http://{args.bind}:{args.port} · Ctrl+C para detener', flush=True)
        try:
            servidor.serve_forever()
        except KeyboardInterrupt:
            pass
