"""
client.py - HTTP Client (TCP via Proxy) + UDP QoS Pinger
Penggunaan:
  python client.py -mode tcp [--path /index.html] [--proxy-host 127.0.0.1] [--proxy-port 8080]
  python client.py -mode udp [--server-host 127.0.0.1] [--server-port 9000] [--count 10]
  python client.py -mode both
"""

# TODO: OUTPUT HASIL QOS KE CSV, TCP KE LOG (?)

import socket
import time
import datetime
import argparse
import sys
import math


# ─── Konfigurasi Default ────────────────────────────────────────────────────────
PROXY_HOST = '127.0.0.1'   # Ganti dengan IP Proxy jika beda perangkat
PROXY_PORT = 8080

WEBSERVER_HOST = '127.0.0.1'  # Untuk UDP QoS langsung ke server
UDP_PORT = 9000

BUFFER_SIZE = 65536
UDP_TIMEOUT = 1.0           # detik
UDP_PACKET_COUNT = 10
UDP_INTERVAL = 0.5          # jeda antar paket (detik)


# ─── Logging ────────────────────────────────────────────────────────────────────
def log(tag, message):
    ts = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
    print(f"[{ts}] [{tag}] {message}", flush=True)


# ═══════════════════════════════════════════════════════════════════════════════
# MODE HTTP (TCP) — Kirim request ke Proxy
# ═══════════════════════════════════════════════════════════════════════════════

def http_get(proxy_host, proxy_port, path):
    """Mengirim HTTP GET ke Proxy dan mengembalikan (status_line, headers, body)."""
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {proxy_host}:{proxy_port}\r\n"
        f"Connection: close\r\n"
        f"User-Agent: SimpleClient/1.0\r\n"
        f"\r\n"
    )

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(15)
        s.connect((proxy_host, proxy_port))
        s.sendall(request.encode('utf-8'))

        response = b''
        while True:
            chunk = s.recv(BUFFER_SIZE)
            if not chunk:
                break
            response += chunk

    return response


def parse_http_response(raw):
    """Memisahkan header dan body dari raw HTTP response."""
    sep = raw.find(b'\r\n\r\n')
    if sep == -1:
        return raw.decode('utf-8', errors='replace'), '', ''
    header_bytes = raw[:sep]
    body_bytes = raw[sep + 4:]

    headers_text = header_bytes.decode('utf-8', errors='replace')
    lines = headers_text.split('\r\n')
    status_line = lines[0] if lines else ''
    headers = '\r\n'.join(lines[1:])

    try:
        body = body_bytes.decode('utf-8', errors='replace')
    except Exception:
        body = repr(body_bytes)

    return status_line, headers, body


def run_http_mode(proxy_host, proxy_port, paths):
    print()
    print("=" * 60)
    print("  MODE HTTP (TCP via Proxy)")
    print("=" * 60)
    log("HTTP", f"Target Proxy: {proxy_host}:{proxy_port}")

    for path in paths:
        print()
        print(f"  ──── REQUEST: GET {path} ────")
        try:
            t_start = time.time()
            raw = http_get(proxy_host, proxy_port, path)
            elapsed = (time.time() - t_start) * 1000

            status_line, headers, body = parse_http_response(raw)
            print(f"  Status   : {status_line}")
            print(f"  Waktu    : {elapsed:.2f} ms")
            print(f"  Size     : {len(raw)} bytes")
            print()
            print("  ── Headers ──")
            for h in headers.split('\r\n'):
                if h.strip():
                    print(f"  {h}")
            print()
            print("  ── Body (500 karakter pertama) ──")
            preview = body[:500].replace('\n', '\n  ')
            print(f"  {preview}")
            if len(body) > 500:
                print(f"  ... (total {len(body)} karakter)")

        except ConnectionRefusedError:
            log("HTTP", f"GAGAL: Proxy tidak bisa dihubungi di {proxy_host}:{proxy_port}")
        except socket.timeout:
            log("HTTP", f"TIMEOUT: {path}")
        except Exception as e:
            log("HTTP", f"ERROR pada {path}: {e}")

    print()
    print("=" * 60)


# ═══════════════════════════════════════════════════════════════════════════════
# MODE UDP (QoS Pinger)
# ═══════════════════════════════════════════════════════════════════════════════

def run_udp_mode(server_host, server_port, count):
    print()
    print("=" * 60)
    print("  MODE UDP QoS PINGER")
    print("=" * 60)
    log("UDP", f"Target: {server_host}:{server_port} | Paket: {count} | Timeout: {UDP_TIMEOUT}s")
    print()

    rtt_list = []
    lost = 0
    total_payload_bytes = 0

    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.settimeout(UDP_TIMEOUT)

    t_session_start = time.time()

    for seq in range(1, count + 1):
        timestamp_send = time.time()
        payload_str = f"Ping {seq} {timestamp_send:.6f}"
        payload_bytes = payload_str.encode('utf-8')
        total_payload_bytes += len(payload_bytes)

        try:
            udp_sock.sendto(payload_bytes, (server_host, server_port))
            data, _ = udp_sock.recvfrom(BUFFER_SIZE)
            timestamp_recv = time.time()

            rtt_ms = (timestamp_recv - timestamp_send) * 1000
            rtt_list.append(rtt_ms)

            # Verifikasi echo
            echo_ok = (data == payload_bytes)
            echo_note = "" if echo_ok else " [echo berbeda!]"
            print(f"  Paket {seq:3d}: RTT = {rtt_ms:.3f} ms{echo_note}")

        except socket.timeout:
            print(f"  Paket {seq:3d}: Request timed out")
            lost += 1

        # Jeda antar paket
        time.sleep(UDP_INTERVAL)

    t_session_end = time.time()
    udp_sock.close()

    # ── Statistik ──────────────────────────────────────────────────────────────
    print()
    print("  ─── STATISTIK QoS ───────────────────────────────────────")
    total_sent = count
    total_recv = total_sent - lost
    loss_pct = (lost / total_sent) * 100 if total_sent > 0 else 0

    if rtt_list:
        rtt_min = min(rtt_list)
        rtt_avg = sum(rtt_list) / len(rtt_list)
        rtt_max = max(rtt_list)

        # Jitter = standar deviasi dari selisih RTT berturut-turut
        if len(rtt_list) >= 2:
            diffs = [abs(rtt_list[i] - rtt_list[i-1]) for i in range(1, len(rtt_list))]
            mean_diff = sum(diffs) / len(diffs)
            variance = sum((d - mean_diff) ** 2 for d in diffs) / len(diffs)
            jitter = math.sqrt(variance)
        else:
            jitter = 0.0

        # Throughput = total payload berhasil / durasi sesi
        duration = t_session_end - t_session_start
        throughput_bps = (total_payload_bytes * total_recv / total_sent * 8) / duration if duration > 0 else 0
        throughput_kbps = throughput_bps / 1000

        print(f"  Paket dikirim  : {total_sent}")
        print(f"  Paket diterima : {total_recv}")
        print(f"  Packet Loss    : {loss_pct:.1f}%")
        print()
        print(f"  RTT min        : {rtt_min:.3f} ms")
        print(f"  RTT avg        : {rtt_avg:.3f} ms")
        print(f"  RTT max        : {rtt_max:.3f} ms")
        print()
        print(f"  Jitter         : {jitter:.3f} ms")
        print(f"  Throughput     : {throughput_kbps:.3f} kbps")
        print(f"  Durasi sesi    : {duration:.2f} s")
    else:
        print(f"  Semua paket hilang! Packet Loss: {loss_pct:.1f}%")
        print(f"  Pastikan UDP server berjalan di {server_host}:{server_port}")

    print("  ─────────────────────────────────────────────────────────")
    print()


# ═══════════════════════════════════════════════════════════════════════════════
# ARGUMENT PARSER
# ═══════════════════════════════════════════════════════════════════════════════

def parse_args():
    parser = argparse.ArgumentParser(
        description='Client HTTP + UDP QoS untuk arsitektur Client-Proxy-Server',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh penggunaan:
  python client.py -mode tcp
  python client.py -mode tcp --path /index.html --proxy-host 192.168.1.11
  python client.py -mode udp --server-host 192.168.1.10 --count 20
  python client.py -mode both
        """
    )
    parser.add_argument('-mode', required=True, choices=['tcp', 'udp', 'both'],
                        help='Mode operasi: tcp | udp | both')

    # TCP options
    parser.add_argument('--proxy-host', default=PROXY_HOST,
                        help=f'IP/hostname Proxy Server (default: {PROXY_HOST})')
    parser.add_argument('--proxy-port', type=int, default=PROXY_PORT,
                        help=f'Port Proxy Server (default: {PROXY_PORT})')
    parser.add_argument('--path', nargs='+', default=['/index.html'],
                        help='Path file yang di-request (default: /index.html)')

    # UDP options
    parser.add_argument('--server-host', default=WEBSERVER_HOST,
                        help=f'IP/hostname Web Server untuk UDP (default: {WEBSERVER_HOST})')
    parser.add_argument('--server-port', type=int, default=UDP_PORT,
                        help=f'Port UDP Web Server (default: {UDP_PORT})')
    parser.add_argument('--count', type=int, default=UDP_PACKET_COUNT,
                        help=f'Jumlah paket UDP (default: {UDP_PACKET_COUNT}, minimum: 10)')

    return parser.parse_args()


# ─── Main ────────────────────────────────────────────────────────────────────────
def main():
    args = parse_args()
    count = max(10, args.count)  # minimal 10 paket

    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║         CLIENT - Jarkom Client-Proxy-Server              ║")
    print("╚══════════════════════════════════════════════════════════╝")

    try:
        if args.mode == 'tcp':
            run_http_mode(args.proxy_host, args.proxy_port, args.path)

        elif args.mode == 'udp':
            run_udp_mode(args.server_host, args.server_port, count)

        elif args.mode == 'both':
            run_http_mode(args.proxy_host, args.proxy_port, args.path)
            run_udp_mode(args.server_host, args.server_port, count)

    except KeyboardInterrupt:
        print("\nClient dihentikan oleh pengguna.")
        sys.exit(0)


if __name__ == '__main__':
    main()
