"""
webserver.py - Web Server dengan TCP HTTP Server dan UDP Echo Server
Arsitektur: Client -> Proxy -> Web Server
Port: 8000 (TCP/HTTP), 9000 (UDP/Echo)
"""

import socket
import threading
import os
import mimetypes
import datetime
import sys


# ─── Konfigurasi ────────────────────────────────────────────────────────────────
TCP_HOST = '0.0.0.0'
TCP_PORT = 8000
UDP_HOST = '0.0.0.0'
UDP_PORT = 9000
BUFFER_SIZE = 65536
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ─── Logging ────────────────────────────────────────────────────────────────────
def log(tag, message):
    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    print(f"[{ts}] [{tag}] {message}", flush=True)


# ─── Utilitas HTTP ──────────────────────────────────────────────────────────────
def get_mime_type(path):
    mime, _ = mimetypes.guess_type(path)
    if mime is None:
        mime = 'application/octet-stream'
    return mime


def build_response(status_code, status_text, content_type, body_bytes):
    header = (
        f"HTTP/1.1 {status_code} {status_text}\r\n"
        f"Content-Type: {content_type}; charset=utf-8\r\n"
        f"Content-Length: {len(body_bytes)}\r\n"
        f"Connection: close\r\n"
        f"Server: SimpleWebServer/1.0\r\n"
        f"Date: {datetime.datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')}\r\n"
        f"\r\n"
    )
    return header.encode('utf-8') + body_bytes


def build_error_response(status_code, status_text):
    body = f"<html><body><h1>{status_code} {status_text}</h1></body></html>"
    return build_response(status_code, status_text, 'text/html', body.encode('utf-8'))


# ─── Handler Koneksi TCP ────────────────────────────────────────────────────────
def handle_tcp_client(conn, addr):
    thread_name = threading.current_thread().name
    log("HTTP", f"Koneksi dari {addr[0]}:{addr[1]} [{thread_name}]")
    try:
        # Terima request
        raw_request = b''
        conn.settimeout(10)
        while True:
            chunk = conn.recv(BUFFER_SIZE)
            if not chunk:
                break
            raw_request += chunk
            if b'\r\n\r\n' in raw_request:
                break

        if not raw_request:
            conn.close()
            return

        # Parse HTTP request
        try:
            header_section = raw_request.split(b'\r\n\r\n')[0]
            request_line = header_section.decode('utf-8', errors='replace').split('\r\n')[0]
            parts = request_line.strip().split(' ')
            if len(parts) < 2:
                raise ValueError("Malformed request line")
            method = parts[0]
            path = parts[1]
        except Exception as e:
            log("HTTP", f"Parsing error dari {addr[0]}: {e}")
            conn.sendall(build_error_response(400, 'Bad Request'))
            conn.close()
            return

        # Hanya handle GET
        if method not in ('GET', 'HEAD'):
            conn.sendall(build_error_response(405, 'Method Not Allowed'))
            log("HTTP", f"{addr[0]} {method} {path} -> 405")
            conn.close()
            return

        # Normalisasi path
        if path == '/':
            path = '/index.html'

        # Sanitasi path (cegah directory traversal)
        safe_path = os.path.normpath(path.lstrip('/'))
        file_path = os.path.join(BASE_DIR, safe_path)

        # Cek file ada
        if not os.path.isfile(file_path):
            response = build_error_response(404, 'Not Found')
            conn.sendall(response)
            log("HTTP", f"{addr[0]} GET {path} -> 404 Not Found")
            conn.close()
            return

        # Baca dan kirim file
        try:
            with open(file_path, 'rb') as f:
                body = f.read()
            mime = get_mime_type(file_path)
            response = build_response(200, 'OK', mime, body)
            conn.sendall(response)
            log("HTTP", f"{addr[0]} GET {path} -> 200 OK ({len(body)} bytes, {mime})")
        except Exception as e:
            response = build_error_response(500, 'Internal Server Error')
            conn.sendall(response)
            log("HTTP", f"{addr[0]} GET {path} -> 500 Internal Server Error: {e}")

    except socket.timeout:
        log("HTTP", f"Timeout dari {addr[0]}")
    except Exception as e:
        log("HTTP", f"Error pada koneksi {addr[0]}: {e}")
        try:
            conn.sendall(build_error_response(500, 'Internal Server Error'))
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ─── TCP Server Thread ───────────────────────────────────────────────────────────
def run_tcp_server():
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((TCP_HOST, TCP_PORT))
    server_sock.listen(128)
    log("HTTP", f"TCP HTTP Server berjalan di port {TCP_PORT}")

    while True:
        try:
            conn, addr = server_sock.accept()
            t = threading.Thread(
                target=handle_tcp_client,
                args=(conn, addr),
                daemon=True,
                name=f"TCP-{addr[0]}:{addr[1]}"
            )
            t.start()
            log("HTTP", f"Thread baru dibuat: {t.name} (aktif: {threading.active_count()-1})")
        except Exception as e:
            log("HTTP", f"Accept error: {e}")


# ─── UDP Echo Server Thread ──────────────────────────────────────────────────────
def run_udp_server():
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp_sock.bind((UDP_HOST, UDP_PORT))
    log("UDP", f"UDP Echo Server berjalan di port {UDP_PORT}")

    while True:
        try:
            data, addr = udp_sock.recvfrom(BUFFER_SIZE)
            # Echo balik payload tanpa modifikasi
            udp_sock.sendto(data, addr)
            log("UDP", f"Echo ke {addr[0]}:{addr[1]} | payload: {data.decode('utf-8', errors='replace')!r}")
        except Exception as e:
            log("UDP", f"Error: {e}")


# ─── Main ────────────────────────────────────────────────────────────────────────
def main():
    log("SERVER", f"Web Server dimulai | BASE_DIR: {BASE_DIR}")
    log("SERVER", f"Server running on port {TCP_PORT}/TCP, {UDP_PORT}/UDP")

    # Jalankan UDP server di thread terpisah
    udp_thread = threading.Thread(target=run_udp_server, daemon=True, name="UDP-Server")
    udp_thread.start()

    # Jalankan TCP server di main thread
    try:
        run_tcp_server()
    except KeyboardInterrupt:
        log("SERVER", "Server dihentikan.")
        sys.exit(0)


if __name__ == '__main__':
    main()
