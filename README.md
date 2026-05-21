# Jarkom Tugas Besar - Client Proxy Server

## Struktur File

```
├── webserver.py      # Web Server (TCP port 8000 + UDP port 9000)
├── proxy.py          # Proxy Server (TCP port 8080)
├── client.py         # Client HTTP + UDP QoS Pinger
├── proxy_cache/      # Dibuat otomatis saat proxy berjalan
└── index.html        # (disediakan, letakkan di direktori yang sama dengan webserver.py)
```

## Topologi

```
Client (client.py) ──TCP/UDP──> Proxy (proxy.py) ──TCP──> Web Server (webserver.py)
                                                    UDP ──────────────────────────>
```

## Cara Menjalankan

### 1. Urutan Start (Wajib: Server dulu, baru Proxy, lalu Client)

**Terminal 1 - Web Server:**
```bash
python webserver.py
```

**Terminal 2 - Proxy Server:**
```bash
python proxy.py
```

**Terminal 3 - Client (Mode TCP):**
```bash
python client.py -mode tcp
python client.py -mode tcp --path /index.html /page.html
```

**Terminal 3 - Client (Mode UDP/QoS):**
```bash
python client.py -mode udp
python client.py -mode udp --count 20
```

**Terminal 3 - Client (Mode Both):**
```bash
python client.py -mode both
```

## Konfigurasi Multi-Device (LAN)

Edit bagian konfigurasi di masing-masing file:

**proxy.py** - ubah IP Web Server:
```python
WEBSERVER_HOST = '192.168.1.10'   # IP laptop Web Server
```

**client.py** - ubah IP Proxy dan Server:
```python
PROXY_HOST = '192.168.1.11'       # IP laptop Proxy
WEBSERVER_HOST = '192.168.1.10'   # IP laptop Web Server (untuk UDP)
```

## Uji Multi-Client (5 Instance)

**Opsi 1 - Manual (5 terminal):**
```bash
# Jalankan hampir bersamaan di 5 terminal berbeda
python client.py -mode tcp --path /index.html
```

**Opsi 2 - Script:**
```python
import subprocess, threading

def run_client(i):
    subprocess.run(['python', 'client.py', '-mode', 'tcp', '--path', f'/page{i}.html'])

threads = [threading.Thread(target=run_client, args=(i,)) for i in range(5)]
for t in threads: t.start()
for t in threads: t.join()
```

## Port yang Digunakan

| Komponen   | Protokol | Port |
|------------|----------|------|
| Web Server | TCP/HTTP | 8000 |
| Web Server | UDP/Echo | 9000 |
| Proxy      | TCP/HTTP | 8080 |
| Client     | ephemeral| -    |

## Filter Wireshark

```
tcp.port==8000 || tcp.port==8080 || udp.port==9000
```

## Output QoS yang Dihasilkan

- RTT min/avg/max (ms)
- Packet Loss (%)
- Jitter (ms) - standar deviasi selisih RTT
- Throughput (kbps)
