"""
proxy.py - Proxy Server dengan mekanisme Forwarding, Caching, dan Konkurensi
Arsitektur: Client -> Proxy -> Web Server
Port: 8080 (mendengarkan dari Client)
"""

import socket
import threading
import os
import datetime
import sys
import hashlib


# ─── Konfigurasi ────────────────────────────────────────────────────────────────
PROXY_HOST = '0.0.0.0'
PROXY_PORT = 8080

WEBSERVER_HOST = '127.0.0.1'   # Ganti dengan IP Web Server jika beda perangkat
WEBSERVER_PORT = 8000

BUFFER_SIZE = 65536
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'proxy_cache')

# Lock untuk thread-safety pada cache
cache_lock = threading.Lock()


# ─── Logging ────────────────────────────────────────────────────────────────────
def log(tag, message):
    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    print(f"[{ts}] [{tag}] {message}", flush=True)


# ─── Utilitas Cache ──────────────────────────────────────────────────────────────
def get_cache_key(url_path):
    """Membuat nama file cache yang aman dari URL path."""
    safe = url_path.strip('/').replace('/', '_').replace('\\', '_')
    if not safe:
        safe = 'root_index'
    # Tambahkan hash pendek untuk hindari tabrakan
    h = hashlib.md5(url_path.encode()).hexdigest()[:8]
    return f"{safe}_{h}.cache"


def cache_exists(cache_key):
    cache_path = os.path.join(CACHE_DIR, cache_key)
    return os.path.isfile(cache_path)


def read_cache(cache_key):
    cache_path = os.path.join(CACHE_DIR, cache_key)
    with open(cache_path, 'rb') as f:
        return f.read()


def write_cache(cache_key, data):
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, cache_key)
    # Penulisan atomik: tulis ke temp dulu lalu rename
    tmp_path = cache_path + '.tmp'
    with open(tmp_path, 'wb') as f:
        f.write(data)
    os.replace(tmp_path, cache_path)


# ─── Utilitas HTTP ──────────────────────────────────────────────────────────────
def parse_request_line(raw_request):
    """
    Mengurai request line HTTP.
    Mengembalikan (method, path, version, raw_header_bytes) atau None jika gagal.
    """
    try:
        header_end = raw_request.find(b'\r\n\r\n')
        if header_end == -1:
            return None
        header_section = raw_request[:header_end].decode('utf-8', errors='replace')
        first_line = header_section.split('\r\n')[0]
        parts = first_line.strip().split(' ')
        if len(parts) < 2:
            return None
        method = parts[0]
        path = parts[1]
        version = parts[2] if len(parts) > 2 else 'HTTP/1.1'
        return method, path, version
    except Exception:
        return None


def build_error_response(status_code, status_text):
    body = f"<html><body><h1>{status_code} {status_text}</h1><p>Proxy Server</p></body></html>"
    body_bytes = body.encode('utf-8')
    header = (
        f"HTTP/1.1 {status_code} {status_text}\r\n"
        f"Content-Type: text/html; charset=utf-8\r\n"
        f"Content-Length: {len(body_bytes)}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    )
    return header.encode('utf-8') + body_bytes


def build_forward_request(path, host, port):
    """Membangun HTTP GET request untuk dikirim ke Web Server."""
    req = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    )
    return req.encode('utf-8')


# ─── Forward ke Web Server ───────────────────────────────────────────────────────
def forward_to_server(path):
    """
    Menghubungi Web Server dan mengembalikan raw response bytes.
    Raises exception jika gagal.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(10)
        s.connect((WEBSERVER_HOST, WEBSERVER_PORT))
        request = build_forward_request(path, WEBSERVER_HOST, WEBSERVER_PORT)
        s.sendall(request)

        response = b''
        while True:
            chunk = s.recv(BUFFER_SIZE)
            if not chunk:
                break
            response += chunk
    return response


def extract_status_code(response_bytes):
    """Mengekstrak status code dari HTTP response."""
    try:
        first_line = response_bytes.split(b'\r\n')[0].decode('utf-8')
        parts = first_line.split(' ')
        if len(parts) >= 2:
            return int(parts[1])
    except Exception:
        pass
    return 0


# ─── Handler Koneksi dari Client ─────────────────────────────────────────────────
def handle_client(conn, addr):
    thread_name = threading.current_thread().name
    start_time = datetime.datetime.now()
    log("PROXY", f"Koneksi dari {addr[0]}:{addr[1]} [{thread_name}]")

    try:
        # Terima request dari client
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

        # Parse request
        parsed = parse_request_line(raw_request)
        if parsed is None:
            conn.sendall(build_error_response(400, 'Bad Request'))
            log("PROXY", f"{addr[0]} -> 400 Bad Request (malformed)")
            conn.close()
            return

        method, path, _ = parsed

        if path == '/':
            path = '/index.html'

        log("PROXY", f"{addr[0]} -> {method} {path}")

        # ── Cek Cache ───────────────────────────────────────────────────────────
        cache_key = get_cache_key(path)

        with cache_lock:
            hit = cache_exists(cache_key)
            if hit:
                cached_data = read_cache(cache_key)

        if hit:
            # Cache HIT
            elapsed = (datetime.datetime.now() - start_time).total_seconds() * 1000
            log("PROXY", f"Cache HIT  | {path} | {elapsed:.2f}ms | {addr[0]}")
            conn.sendall(cached_data)
            conn.close()
            return

        # ── Cache MISS: Forward ke Web Server ───────────────────────────────────
        log("PROXY", f"Cache MISS | {path} | Forwarding ke {WEBSERVER_HOST}:{WEBSERVER_PORT}")
        try:
            response = forward_to_server(path)
        except socket.timeout:
            log("PROXY", f"Timeout saat forward ke server untuk {path}")
            conn.sendall(build_error_response(504, 'Gateway Timeout'))
            conn.close()
            return
        except ConnectionRefusedError:
            log("PROXY", f"Server tidak terjangkau: {WEBSERVER_HOST}:{WEBSERVER_PORT}")
            conn.sendall(build_error_response(502, 'Bad Gateway'))
            conn.close()
            return
        except Exception as e:
            log("PROXY", f"Error saat forward: {e}")
            conn.sendall(build_error_response(502, 'Bad Gateway'))
            conn.close()
            return

        # Periksa status dari server
        status = extract_status_code(response)
        if status >= 500:
            log("PROXY", f"Server mengembalikan error {status} untuk {path} -> 502")
            conn.sendall(build_error_response(502, 'Bad Gateway'))
            conn.close()
            return

        # Simpan ke cache hanya jika response sukses (2xx)
        if 200 <= status < 300:
            with cache_lock:
                try:
                    write_cache(cache_key, response)
                    log("PROXY", f"Cache WRITE | {path} | key={cache_key}")
                except Exception as e:
                    log("PROXY", f"Gagal menulis cache: {e}")

        # Kirim response ke client
        conn.sendall(response)
        elapsed = (datetime.datetime.now() - start_time).total_seconds() * 1000
        log("PROXY", f"Cache MISS | {path} | {elapsed:.2f}ms | status={status} | {addr[0]}")

    except socket.timeout:
        log("PROXY", f"Timeout dari {addr[0]}")
    except Exception as e:
        log("PROXY", f"Error pada {addr[0]}: {e}")
        try:
            conn.sendall(build_error_response(500, 'Internal Server Error'))
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ─── Main ────────────────────────────────────────────────────────────────────────
def main():
    # Buat direktori cache jika belum ada
    os.makedirs(CACHE_DIR, exist_ok=True)
    log("PROXY", f"Direktori cache: {CACHE_DIR}")
    log("PROXY", f"Forwarding ke Web Server: {WEBSERVER_HOST}:{WEBSERVER_PORT}")

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((PROXY_HOST, PROXY_PORT))
    server_sock.listen(128)
    log("PROXY", f"Proxy listening on port {PROXY_PORT} | multithreading aktif")

    try:
        while True:
            conn, addr = server_sock.accept()
            t = threading.Thread(
                target=handle_client,
                args=(conn, addr),
                daemon=True,
                name=f"PROXY-{addr[0]}:{addr[1]}"
            )
            t.start()
            log("PROXY", f"Thread baru: {t.name} (aktif: {threading.active_count()-1})")
    except KeyboardInterrupt:
        log("PROXY", "Proxy dihentikan.")
        sys.exit(0)
    finally:
        server_sock.close()


if __name__ == '__main__':
    main()
