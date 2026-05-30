"""Single-port TLS proxy: detects plain HTTP vs TLS on the same port.

If the first byte is 0x16 (TLS ClientHello), forward the connection to Gunicorn.
Otherwise, send an HTTP 301 redirect to HTTPS.
"""

import os
import socket
import ssl
import selectors
import threading

LISTEN_PORT = int(os.environ.get('PORT', '9443'))
BACKEND_PORT = int(os.environ.get('GUNICORN_PORT', '8000'))
CERT_FILE = os.environ.get('CERT_FILE', '/data/certs/cert.pem')
KEY_FILE = os.environ.get('KEY_FILE', '/data/certs/key.pem')


def handle_client(client_sock, addr):
    try:
        first_byte = client_sock.recv(1, socket.MSG_PEEK)
        if not first_byte:
            client_sock.close()
            return

        if first_byte[0] == 0x16:
            # TLS handshake - wrap in SSL and proxy to backend
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(CERT_FILE, KEY_FILE)
            try:
                tls_sock = ctx.wrap_socket(client_sock, server_side=True)
            except ssl.SSLError:
                client_sock.close()
                return

            backend = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            backend.connect(('127.0.0.1', BACKEND_PORT))
            _proxy_bidirectional(tls_sock, backend)
        else:
            # Plain HTTP - read request line and redirect
            data = b''
            while b'\r\n' not in data and len(data) < 4096:
                chunk = client_sock.recv(4096)
                if not chunk:
                    break
                data += chunk

            request_line = data.split(b'\r\n')[0].decode('utf-8', errors='replace')
            path = '/'
            parts = request_line.split(' ')
            if len(parts) >= 2:
                path = parts[1]

            host_header = ''
            for line in data.split(b'\r\n')[1:]:
                if line.lower().startswith(b'host:'):
                    host_header = line.split(b':', 1)[1].strip().decode('utf-8', errors='replace')
                    break

            hostname = host_header.split(':')[0] if host_header else 'localhost'
            if LISTEN_PORT == 443:
                location = f'https://{hostname}{path}'
            else:
                location = f'https://{hostname}:{LISTEN_PORT}{path}'

            response = (
                f'HTTP/1.1 301 Moved Permanently\r\n'
                f'Location: {location}\r\n'
                f'Content-Length: 0\r\n'
                f'Connection: close\r\n'
                f'\r\n'
            ).encode()
            client_sock.sendall(response)
            client_sock.close()
    except Exception:
        try:
            client_sock.close()
        except Exception:
            pass


def _proxy_bidirectional(client, backend):
    """Shuttle data between client and backend until one side closes."""
    sel = selectors.DefaultSelector()
    sel.register(client, selectors.EVENT_READ, backend)
    sel.register(backend, selectors.EVENT_READ, client)
    try:
        while True:
            events = sel.select(timeout=120)
            if not events:
                break
            for key, _ in events:
                src = key.fileobj
                dst = key.data
                try:
                    data = src.recv(65536)
                except (ssl.SSLError, OSError):
                    data = b''
                if not data:
                    sel.close()
                    client.close()
                    backend.close()
                    return
                try:
                    dst.sendall(data)
                except (ssl.SSLError, OSError):
                    sel.close()
                    client.close()
                    backend.close()
                    return
    except Exception:
        pass
    finally:
        sel.close()
        try:
            client.close()
        except Exception:
            pass
        try:
            backend.close()
        except Exception:
            pass


def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', LISTEN_PORT))
    server.listen(128)
    print(f"TLS proxy listening on port {LISTEN_PORT} (HTTP+HTTPS -> backend :{BACKEND_PORT})")

    while True:
        client_sock, addr = server.accept()
        t = threading.Thread(target=handle_client, args=(client_sock, addr), daemon=True)
        t.start()


if __name__ == '__main__':
    main()
