import subprocess, threading

def run_client(i):
    subprocess.run(['python', 'client.py', '-mode', 'tcp', '--path', f'/page{i}.html'])

threads = [threading.Thread(target=run_client, args=(i,)) for i in range(5)]
for t in threads: t.start()
for t in threads: t.join()