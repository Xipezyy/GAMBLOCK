"""
Blocker Server — persistent background service (Task Scheduler).
- HTTP  port 80  : shows "YOU SAID YOU'D QUIT!" with typed-only password form
- HTTPS port 443 : same, using our locally-trusted TLS cert
- DNS   port 53  : intercepts ALL subdomains of blocked sites (e.g. live.stake.com)
"""

import hashlib
import http.server
import json
import secrets
import socket
import socketserver
import ssl
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs

SCRIPT_DIR     = Path(__file__).parent.resolve()
CONFIG_FILE    = SCRIPT_DIR / "config.json"
CA_CERT_FILE   = SCRIPT_DIR / "ca_cert.pem"
CA_KEY_FILE    = SCRIPT_DIR / "ca_key.pem"
SITE_CERT_FILE = SCRIPT_DIR / "site_cert.pem"
SITE_KEY_FILE  = SCRIPT_DIR / "site_key.pem"

HOSTS_FILE   = r"C:\Windows\System32\drivers\etc\hosts"
MARKER_START = "# === SITE BLOCKER START ==="
MARKER_END   = "# === SITE BLOCKER END ==="

# ─── Shared state ─────────────────────────────────────────────────────────────

_sessions: dict[str, int] = {}
_session_lock = threading.Lock()

# Blocked domains cache — reloaded from config every 30 s so added sites take effect
_blocked_domains: set[str] = set()
_domains_lock    = threading.Lock()
_domains_loaded_at: float = 0.0

def _refresh_domains():
    global _blocked_domains, _domains_loaded_at
    if time.time() - _domains_loaded_at < 30:
        return
    config = _load_config()
    with _domains_lock:
        _blocked_domains = {s.lower().strip() for s in (config or {}).get("sites", [])}
    _domains_loaded_at = time.time()

def _get_domains() -> set[str]:
    _refresh_domains()
    with _domains_lock:
        return set(_blocked_domains)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _hash(pwd: str) -> str:
    return hashlib.sha256(pwd.encode()).hexdigest()

def _load_config() -> dict | None:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None

def _remove_hosts_entries():
    subprocess.run(["attrib", "-r", HOSTS_FILE], capture_output=True)
    try:
        with open(HOSTS_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        cleaned, inside = [], False
        for line in lines:
            if MARKER_START in line:
                inside = True
            elif MARKER_END in line:
                inside = False
            elif not inside:
                cleaned.append(line)
        with open(HOSTS_FILE, "w", encoding="utf-8") as f:
            f.writelines(cleaned)
    except Exception as e:
        print(f"[blocker] Failed to clean hosts: {e}", flush=True)
    subprocess.run(["ipconfig", "/flushdns"], capture_output=True)

def _restore_dns():
    subprocess.run([
        "powershell", "-Command",
        "Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | "
        "ForEach-Object { Set-DnsClientServerAddress -InterfaceAlias $_.Name -ResetServerAddresses }"
    ], capture_output=True)

# ─── HTML ─────────────────────────────────────────────────────────────────────

_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SITE BLOCKED</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{
  background:#080000;color:#ff2222;
  font-family:'Courier New',monospace;
  min-height:100vh;display:flex;flex-direction:column;
  align-items:center;justify-content:center;padding:40px 20px;
  user-select:none;
}}
h1{{
  font-size:clamp(2em,7vw,4.5em);font-weight:bold;
  letter-spacing:5px;text-shadow:0 0 40px #ff0000,0 0 80px #880000;
  margin-bottom:30px;text-align:center;
  animation:pulse 2.5s ease-in-out infinite;
}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.65}}}}
.counter{{
  font-size:1.4em;color:#cc7777;margin-bottom:20px;
  border:1px solid #440000;padding:12px 28px;border-radius:4px;
  background:#100000;
}}
.counter strong{{color:#ff5555;font-size:1.25em}}
.bar-wrap{{width:340px;height:10px;background:#200000;border-radius:5px;margin-bottom:32px;overflow:hidden}}
.bar-fill{{height:100%;background:linear-gradient(90deg,#cc0000,#ff6600);border-radius:5px;transition:width .4s ease}}
form{{display:flex;flex-direction:column;align-items:center;gap:14px;width:100%;max-width:380px}}
input[type=password]{{
  width:100%;padding:15px 18px;
  font-size:1.15em;font-family:'Courier New',monospace;
  background:#130000;border:2px solid #770000;border-radius:4px;
  color:#ffffff;outline:none;text-align:center;letter-spacing:3px;
  caret-color:#ff4444;
}}
input[type=password]:focus{{border-color:#ff3333;box-shadow:0 0 14px #ff000033}}
button{{
  width:100%;padding:15px;
  font-size:1.1em;font-family:'Courier New',monospace;font-weight:bold;
  background:#3d0000;color:#ff5555;border:2px solid #770000;border-radius:4px;
  cursor:pointer;letter-spacing:3px;transition:all .2s;
}}
button:hover{{background:#5c0000;border-color:#ff3333;color:#ff8888}}
.ok{{color:#33ff77;font-size:.95em;margin-top:2px}}
.err{{color:#ff5555;font-size:.95em;margin-top:2px;animation:shake .3s ease}}
@keyframes shake{{0%,100%{{transform:translateX(0)}}25%{{transform:translateX(-6px)}}75%{{transform:translateX(6px)}}}}
.done{{font-size:1.6em;color:#33ff77;margin-top:28px;text-align:center;line-height:1.6}}
.hint{{color:#440000;font-size:.8em;margin-top:28px;text-align:center;line-height:1.6}}
</style>
</head>
<body>
<h1>YOU SAID YOU'D QUIT!</h1>
<div class="counter">ENTER PASSWORDS <strong>{count}</strong>&nbsp;/&nbsp;100</div>
<div class="bar-wrap"><div class="bar-fill" style="width:{pct}%"></div></div>
{body}
<p class="hint">You blocked this site yourself.<br>You made a promise. Keep it.</p>
<script>
(function(){{
  var input = document.getElementById('pwd');
  if (!input) return;
  ['paste','copy','cut','contextmenu','drop','dragover'].forEach(function(ev){{
    input.addEventListener(ev, function(e){{ e.preventDefault(); e.stopPropagation(); }}, true);
    document.addEventListener(ev, function(e){{
      if(document.activeElement===input){{ e.preventDefault(); e.stopPropagation(); }}
    }}, true);
  }});
  document.addEventListener('keydown', function(e){{
    if(document.activeElement!==input) return;
    if((e.ctrlKey||e.metaKey) && 'vcxVCX'.indexOf(e.key)>=0){{
      e.preventDefault(); e.stopPropagation();
    }}
  }}, true);
}})();
</script>
</body>
</html>"""

_FORM = """
<form method="POST" action="/" autocomplete="off">
  <input type="hidden" name="sid" value="{sid}">
  <input type="password" id="pwd" name="pwd" autofocus
         autocomplete="new-password" autocorrect="off" autocapitalize="off"
         onpaste="return false" oncopy="return false" oncut="return false"
         placeholder="Type password #{next}...">
  <button type="submit">&#x25B6;&nbsp;SUBMIT</button>
  {msg}
</form>"""

_DONE = '<p class="done">&#x2705; All 100 passwords entered.<br>Sites unblocked. You\'re free.</p>'

def _render(sid: str, msg: str = "") -> str:
    count = _sessions.get(sid, 0)
    config = _load_config()
    if count >= 100 or not config:
        body = _DONE
    else:
        body = _FORM.format(sid=sid, next=count + 1, msg=msg)
    return _PAGE.format(count=count, pct=count, body=body)

# ─── Session helpers ──────────────────────────────────────────────────────────

def _get_sid(headers) -> str | None:
    for part in headers.get("Cookie", "").split(";"):
        p = part.strip()
        if p.startswith("sid="):
            return p[4:]
    return None

# ─── HTTP handler ─────────────────────────────────────────────────────────────

class BlockerHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def _send(self, html: str, status: int = 200, extra: dict | None = None):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        sid   = _get_sid(self.headers)
        extra = None
        if not sid:
            sid = secrets.token_hex(20)
            with _session_lock:
                _sessions[sid] = 0
            extra = {"Set-Cookie": f"sid={sid}; Path=/; HttpOnly; SameSite=Strict"}
        self._send(_render(sid), extra=extra)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        params = parse_qs(self.rfile.read(length).decode("utf-8", errors="replace"))
        sid    = params.get("sid", [""])[0]
        pwd    = params.get("pwd", [""])[0].strip()

        with _session_lock:
            if not sid or sid not in _sessions:
                sid = secrets.token_hex(20)
                _sessions[sid] = 0
            count = _sessions[sid]

        config = _load_config()
        msg = ""
        if config and 0 <= count < 100:
            if _hash(pwd) == config["hashed_passwords"][count]:
                with _session_lock:
                    _sessions[sid] = count + 1
                    count = _sessions[sid]
                if count >= 100:
                    threading.Thread(target=_do_unblock, daemon=True).start()
                    msg = '<p class="ok">&#x2705; Correct! Unblocking now&hellip;</p>'
                else:
                    msg = f'<p class="ok">&#x2705; Correct &mdash; {100 - count} remaining.</p>'
            else:
                msg = '<p class="err">&#x274C; Wrong. Type it, don\'t guess it.</p>'

        extra = {"Set-Cookie": f"sid={sid}; Path=/; HttpOnly; SameSite=Strict"}
        self._send(_render(sid, msg), extra=extra)

# ─── Unblock ──────────────────────────────────────────────────────────────────

def _do_unblock():
    time.sleep(0.8)
    _remove_hosts_entries()
    _restore_dns()
    CONFIG_FILE.unlink(missing_ok=True)
    subprocess.run(["schtasks", "/delete", "/tn", "SiteBlockerServer", "/f"], capture_output=True)
    subprocess.run(["certutil", "-delstore", "Root", "Site Blocker CA"],     capture_output=True)
    for f in [CA_CERT_FILE, CA_KEY_FILE, SITE_CERT_FILE, SITE_KEY_FILE]:
        f.unlink(missing_ok=True)

# ─── DNS Server ───────────────────────────────────────────────────────────────

def _parse_hostname(data: bytes) -> str:
    """Extract queried hostname from raw DNS query packet."""
    offset, labels = 12, []
    while offset < len(data):
        ln = data[offset]
        if ln == 0:
            break
        if ln & 0xC0 == 0xC0:  # pointer compression — stop parsing
            break
        offset += 1
        labels.append(data[offset:offset + ln].decode("ascii", errors="replace"))
        offset += ln
    return ".".join(labels).lower()

def _blocked_response(data: bytes) -> bytes:
    """DNS A-record response that resolves to 127.0.0.1."""
    # Find end of question section
    offset = 12
    while offset < len(data):
        ln = data[offset]
        if ln == 0:
            offset += 1
            break
        if ln & 0xC0 == 0xC0:
            offset += 2
            break
        offset += ln + 1
    offset += 4  # qtype + qclass
    question = data[12:offset]

    header = (
        data[:2]                  # transaction ID
        + b"\x81\x80"            # flags: standard response, no error
        + data[4:6]              # qdcount (same as query)
        + b"\x00\x01"           # ancount = 1
        + b"\x00\x00\x00\x00"  # nscount + arcount = 0
    )
    answer = (
        b"\xc0\x0c"            # name: pointer back to question (offset 12)
        + b"\x00\x01"          # type A
        + b"\x00\x01"          # class IN
        + b"\x00\x00\x00\x3c" # TTL = 60 seconds
        + b"\x00\x04"          # rdlength = 4 bytes
        + b"\x7f\x00\x00\x01" # 127.0.0.1
    )
    return header + question + answer

def _is_blocked(hostname: str, domains: set[str]) -> bool:
    h = hostname.rstrip(".")
    return any(h == d or h.endswith("." + d) for d in domains)

def _forward_query(data: bytes) -> bytes | None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(3)
        try:
            s.sendto(data, ("8.8.8.8", 53))
            return s.recv(4096)
        except Exception:
            return None

def _handle_dns_query(sock: socket.socket, data: bytes, addr, domains: set[str]):
    try:
        hostname = _parse_hostname(data)
        response = _blocked_response(data) if _is_blocked(hostname, domains) else _forward_query(data)
        if response:
            sock.sendto(response, addr)
    except Exception as e:
        print(f"[dns] Error: {e}", flush=True)

def _run_dns_server():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 53))
        print("[blocker] DNS  listening on 127.0.0.1:53 — all subdomains covered", flush=True)
        while True:
            try:
                data, addr = sock.recvfrom(4096)
                domains = _get_domains()
                threading.Thread(
                    target=_handle_dns_query,
                    args=(sock, data, addr, domains),
                    daemon=True
                ).start()
            except Exception as e:
                print(f"[dns] Loop error: {e}", flush=True)
    except OSError as e:
        print(f"[blocker] DNS bind failed ({e}) — subdomain blocking unavailable", flush=True)

# ─── HTTP / HTTPS servers ─────────────────────────────────────────────────────

class _ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads     = True
    allow_reuse_address = True

def _run_http():
    srv = _ThreadingServer(("127.0.0.1", 80), BlockerHandler)
    print("[blocker] HTTP  listening on 127.0.0.1:80", flush=True)
    srv.serve_forever()

def _run_https():
    if not (SITE_CERT_FILE.exists() and SITE_KEY_FILE.exists()):
        print("[blocker] No TLS cert — HTTPS interception disabled", flush=True)
        return
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(str(SITE_CERT_FILE), str(SITE_KEY_FILE))
    srv = _ThreadingServer(("127.0.0.1", 443), BlockerHandler)
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    print("[blocker] HTTPS listening on 127.0.0.1:443", flush=True)
    srv.serve_forever()

# ─── Entry point ──────────────────────────────────────────────────────────────

def run():
    if not CONFIG_FILE.exists():
        print("[blocker] No config found — nothing to block. Exiting.", flush=True)
        sys.exit(0)

    # Pre-load domains
    _refresh_domains()

    threads = [
        threading.Thread(target=_run_http,       daemon=True),
        threading.Thread(target=_run_https,      daemon=True),
        threading.Thread(target=_run_dns_server, daemon=True),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

if __name__ == "__main__":
    run()
