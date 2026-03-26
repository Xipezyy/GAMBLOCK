#!/usr/bin/env python3
"""
Site Blocker — Self-control tool.
Blocks crypto casino sites via hosts file + local DNS server.
Shows "YOU SAID YOU'D QUIT!" in the browser. Requires 100 typed passwords to unblock.
Must be run as Administrator.
"""

import ctypes
import datetime
import hashlib
import json
import os
import random
import string
import subprocess
import sys
import threading
import winreg
from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────────────────────

# When frozen by PyInstaller, exe lives in Program Files (read-only).
# Store all runtime data in AppData\GAMBLOCK instead.
if getattr(sys, "frozen", False):
    INSTALL_DIR = Path(sys.executable).parent
else:
    INSTALL_DIR = Path(__file__).parent.resolve()

# ProgramData is accessible to all users, admin, and SYSTEM — consistent regardless of who runs it
DATA_DIR = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "GAMBLOCK"
DATA_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_FILE     = DATA_DIR / "config.json"
CA_CERT_FILE    = DATA_DIR / "ca_cert.pem"
CA_KEY_FILE     = DATA_DIR / "ca_key.pem"
SITE_CERT_FILE  = DATA_DIR / "site_cert.pem"
SITE_KEY_FILE   = DATA_DIR / "site_key.pem"
USER_SITES_FILE = DATA_DIR / "user_sites.txt"
def _get_desktop() -> Path:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders") as key:
            return Path(winreg.QueryValueEx(key, "Desktop")[0])
    except Exception:
        return Path(os.path.expanduser("~")) / "Desktop"

PASSWORDS_FILE  = _get_desktop() / "GAMBLOCK_PASSWORDS.txt"

HOSTS_FILE   = r"C:\Windows\System32\drivers\etc\hosts"
MARKER_START = "# === SITE BLOCKER START ==="
MARKER_END   = "# === SITE BLOCKER END ==="
TASK_NAME         = "SiteBlockerServer"
DNS_GUARD_TASK    = "GAMBLOCKDNSGuard"

PASSWORD_COUNT  = 100
PASSWORD_LENGTH = 16

# ─── Default site list ────────────────────────────────────────────────────────
# www. variants are blocked automatically.
# Subdomains (live.stake.com, sports.stake.com, etc.) are caught by the DNS server.
# To permanently add a site, run the script and choose option 3.

GAMBLING_SITES: list[str] = [
    "stake.com",
    "rollbit.com",
    "roobet.com",
    "shuffle.com",
    "bc.game",
    "duelbits.com",
    "duel.com",
    "chips.gg",
    "gamdom.com",
    "thunderpick.io",
    "bitstarz.com",
    "betfury.io",
    "mystake.com",
    "bets.io",
    "wild.io",
    "jackbit.com",
    "vave.com",
    "flush.com",
    "fortunejack.com",
    "mbitcasino.com",
    "cloudbet.com",
    "sportsbet.io",
    "winz.io",
    "haz.casino",
    "katsubet.com",
    "metaspins.com",
    "primedice.com",
    "wolfbet.com",
    "crashino.com",
    "donbet.com",
    "csgoempire.com",
]

# ─── Utilities ────────────────────────────────────────────────────────────────

def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False

def require_admin():
    if not is_admin():
        print("[ERROR] Must be run as Administrator.")
        print("  Right-click GAMBLOCK.exe → 'Run as administrator'.")
        input("\nPress Enter to exit...")
        sys.exit(1)

def hash_password(pwd: str) -> str:
    return hashlib.sha256(pwd.encode("utf-8")).hexdigest()

def generate_passwords() -> list[str]:
    rng   = random.SystemRandom()
    chars = string.ascii_letters + string.digits
    return ["".join(rng.choice(chars) for _ in range(PASSWORD_LENGTH))
            for _ in range(PASSWORD_COUNT)]

def is_blocked() -> bool:
    return CONFIG_FILE.exists()

def _all_sites() -> list[str]:
    """Merge built-in list with any user-added sites."""
    user: list[str] = []
    if USER_SITES_FILE.exists():
        user = [s.strip().lower() for s in USER_SITES_FILE.read_text().splitlines()
                if s.strip() and not s.startswith("#")]
    seen, merged = set(), []
    for s in GAMBLING_SITES + user:
        if s not in seen:
            seen.add(s)
            merged.append(s)
    return merged

# ─── TLS certificate generation ───────────────────────────────────────────────

def generate_certs(sites: list[str]) -> bool:
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError:
        print("  [WARN] 'cryptography' not found — HTTPS interception disabled.")
        print("         Run: python -m pip install cryptography")
        return False

    now = datetime.datetime.now(datetime.timezone.utc)

    # Root CA
    ca_key  = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Site Blocker CA")])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name).issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, key_cert_sign=True, crl_sign=True,
            content_commitment=False, key_encipherment=False,
            data_encipherment=False, key_agreement=False,
            encipher_only=False, decipher_only=False), critical=True)
        .sign(ca_key, hashes.SHA256())
    )

    # Site cert with SAN for every blocked domain + wildcards
    site_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    sans: list[x509.GeneralName] = [x509.DNSName("localhost")]
    for site in sites:
        s = site.lower().strip()
        sans.append(x509.DNSName(s))
        sans.append(x509.DNSName(f"*.{s}"))          # catches all subdomains
        if not s.startswith("www."):
            sans.append(x509.DNSName(f"www.{s}"))

    site_cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Blocked Site")]))
        .issuer_name(ca_name)
        .public_key(site_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=825))
        .add_extension(x509.SubjectAlternativeName(sans), critical=False)
        .sign(ca_key, hashes.SHA256())
    )

    CA_KEY_FILE.write_bytes(ca_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption()))
    CA_CERT_FILE.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    SITE_KEY_FILE.write_bytes(site_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption()))
    SITE_CERT_FILE.write_bytes(site_cert.public_bytes(serialization.Encoding.PEM))
    return True

def install_ca() -> bool:
    r = subprocess.run(["certutil", "-addstore", "-f", "Root", str(CA_CERT_FILE)],
                       capture_output=True, text=True)
    return r.returncode == 0

def uninstall_ca():
    subprocess.run(["certutil", "-delstore", "Root", "Site Blocker CA"], capture_output=True)

# ─── Browser proxy lockdown ───────────────────────────────────────────────────
# Browser VPN extensions (NordVPN, ExpressVPN, etc.) route traffic through a remote
# proxy, bypassing the local DNS and hosts file entirely. We counter this by pushing
# Group Policy that forces Chrome/Edge/Brave into direct-connection mode and writing
# a Firefox enterprise policy that does the same.

_BROWSER_POLICY_KEYS = [
    r"SOFTWARE\Policies\Google\Chrome",
    r"SOFTWARE\Policies\Microsoft\Edge",
    r"SOFTWARE\Policies\BraveSoftware\Brave",
]
_FIREFOX_DIRS = [
    Path(r"C:\Program Files\Mozilla Firefox\distribution"),
    Path(r"C:\Program Files (x86)\Mozilla Firefox\distribution"),
]

def block_browser_proxy():
    for key_path in _BROWSER_POLICY_KEYS:
        try:
            key = winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_ALL_ACCESS)
            winreg.SetValueEx(key, "ProxyMode", 0, winreg.REG_SZ, "direct")
            winreg.SetValueEx(key, "DnsOverHttpsMode", 0, winreg.REG_SZ, "off")  # force system resolver (honours hosts file)
            winreg.CloseKey(key)
        except Exception:
            pass
    ff_policy = {"policies": {"Proxy": {"Mode": "none", "Locked": True},
                               "DNSOverHTTPS": {"Enabled": False, "Locked": True}}}
    for ff_dir in _FIREFOX_DIRS:
        if ff_dir.parent.exists():
            ff_dir.mkdir(exist_ok=True)
            (ff_dir / "policies.json").write_text(json.dumps(ff_policy, indent=2), encoding="utf-8")

def unblock_browser_proxy():
    for key_path in _BROWSER_POLICY_KEYS:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_WRITE) as key:
                for val in ("ProxyMode", "DnsOverHttpsMode"):
                    try:
                        winreg.DeleteValue(key, val)
                    except FileNotFoundError:
                        pass
        except FileNotFoundError:
            pass
    for ff_dir in _FIREFOX_DIRS:
        policy_file = ff_dir / "policies.json"
        if policy_file.exists():
            try:
                policy_file.unlink()
            except Exception:
                pass

# ─── DNS configuration ────────────────────────────────────────────────────────

def configure_dns():
    """Point all active adapters at our local DNS server (primary) + 8.8.8.8 (fallback)."""
    subprocess.run([
        "powershell", "-Command",
        "Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | "
        "ForEach-Object { Set-DnsClientServerAddress -InterfaceAlias $_.Name "
        "-ServerAddresses '127.0.0.1','8.8.8.8' }"
    ], capture_output=True)

def install_dns_guard():
    """Task triggered on every network adapter connect — re-applies our DNS to catch VPN adapters."""
    ps = (
        "Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | "
        "ForEach-Object { Set-DnsClientServerAddress -InterfaceAlias $_.Name "
        "-ServerAddresses '127.0.0.1','8.8.8.8' }"
    )
    subprocess.run([
        "schtasks", "/create", "/tn", DNS_GUARD_TASK,
        "/sc", "onevent",
        "/ec", "Microsoft-Windows-NetworkProfile/Operational",
        "/mo", "*[System[(EventID=10000)]]",
        "/tr", f'powershell -WindowStyle Hidden -Command "{ps}"',
        "/ru", "SYSTEM", "/rl", "HIGHEST", "/f",
    ], capture_output=True)

def remove_dns_guard():
    subprocess.run(["schtasks", "/delete", "/tn", DNS_GUARD_TASK, "/f"], capture_output=True)

def restore_dns():
    """Reset all adapters back to automatic (DHCP) DNS."""
    subprocess.run([
        "powershell", "-Command",
        "Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | "
        "ForEach-Object { Set-DnsClientServerAddress -InterfaceAlias $_.Name "
        "-ResetServerAddresses }"
    ], capture_output=True)

# ─── Task Scheduler ───────────────────────────────────────────────────────────

def install_task() -> bool:
    if getattr(sys, "frozen", False):
        # Running as compiled exe — launch the server exe directly
        cmd = f'"{INSTALL_DIR / "GAMBLOCK_Server.exe"}"'
    else:
        cmd = f'"{sys.executable}" "{INSTALL_DIR / "blocker_server.py"}"'
    r   = subprocess.run([
        "schtasks", "/create", "/tn", TASK_NAME,
        "/sc", "onstart", "/ru", "SYSTEM", "/rl", "HIGHEST",
        "/tr", cmd, "/f",
    ], capture_output=True, text=True)
    return r.returncode == 0

def start_task():
    subprocess.run(["schtasks", "/run",    "/tn", TASK_NAME], capture_output=True)

def stop_task():
    subprocess.run(["schtasks", "/end",    "/tn", TASK_NAME], capture_output=True)

def remove_task():
    subprocess.run(["schtasks", "/delete", "/tn", TASK_NAME, "/f"], capture_output=True)

# ─── Hosts file ───────────────────────────────────────────────────────────────

def _set_hosts_readonly(readonly: bool):
    subprocess.run(["attrib", "+r" if readonly else "-r", HOSTS_FILE], capture_output=True)

def _write_hosts_block(sites: list[str]):
    _set_hosts_readonly(False)
    with open(HOSTS_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n{MARKER_START}\n")
        for site in sites:
            s = site.lower().strip()
            f.write(f"127.0.0.1 {s}\n")
            if not s.startswith("www."):
                f.write(f"127.0.0.1 www.{s}\n")
        f.write(f"{MARKER_END}\n")
    _set_hosts_readonly(True)
    subprocess.run(["ipconfig", "/flushdns"], capture_output=True)

def _remove_hosts_block():
    _set_hosts_readonly(False)
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
        print(f"  [ERROR] Could not update hosts file: {e}")
    subprocess.run(["ipconfig", "/flushdns"], capture_output=True)

# ─── GUI ──────────────────────────────────────────────────────────────────────

import customtkinter as ctk
from tkinter import messagebox

ctk.set_appearance_mode("dark")

_BG     = "#0d0d0d"
_CARD   = "#161616"
_BORDER = "#252525"
_RED    = "#dc2626"
_RED_H  = "#b91c1c"
_GREEN  = "#16a34a"
_WHITE  = "#f5f5f5"
_MUTED  = "#6b7280"
_FONT   = "Segoe UI"


def _no_paste(entry):
    for seq in ("<Control-v>", "<Control-V>", "<<Paste>>",
                "<Button-3>", "<Control-Insert>", "<Shift-Insert>"):
        entry.bind(seq, lambda e: "break")


class _Modal(ctk.CTkToplevel):
    def __init__(self, parent, title, w, h):
        super().__init__(parent)
        self.title(title)
        self.geometry(f"{w}x{h}")
        self.resizable(False, False)
        self.configure(fg_color=_BG)
        self.grab_set()
        try:
            ico = INSTALL_DIR / "gamblock.ico"
            if ico.exists():
                self.after(200, lambda: self.iconbitmap(str(ico)))
        except Exception:
            pass


class AddSiteDialog(_Modal):
    def __init__(self, parent):
        super().__init__(parent, "Add Site — GAMBLOCK", 420, 220)
        ctk.CTkLabel(self, text="Block a new site",
                     font=ctk.CTkFont(family=_FONT, size=16, weight="bold"),
                     text_color=_WHITE).pack(pady=(24, 4))
        ctk.CTkLabel(self, text="Once added it cannot be removed without 100 passwords.",
                     font=ctk.CTkFont(family=_FONT, size=11), text_color=_MUTED).pack()
        self._e = ctk.CTkEntry(self, width=340, height=40,
                                placeholder_text="e.g. newcasino.com",
                                font=ctk.CTkFont(family=_FONT, size=13),
                                fg_color=_CARD, border_color=_BORDER)
        self._e.pack(pady=16)
        self._e.focus()
        self._e.bind("<Return>", lambda _: self._submit())
        ctk.CTkButton(self, text="Block Site", width=340, height=40,
                       font=ctk.CTkFont(family=_FONT, size=13, weight="bold"),
                       fg_color=_RED, hover_color=_RED_H,
                       command=self._submit).pack()

    def _submit(self):
        raw    = self._e.get().strip().lower()
        domain = raw.replace("https://", "").replace("http://", "").split("/")[0].strip(".")
        if not domain or "." not in domain:
            messagebox.showerror("Invalid", "Enter a valid domain (e.g. casino.com)", parent=self)
            return
        if is_blocked():
            config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if domain in config["sites"]:
                messagebox.showinfo("Already blocked", f"{domain} is already blocked.", parent=self)
                self.destroy(); return
            config["sites"].append(domain)
            CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")
            _remove_hosts_block()
            _write_hosts_block(config["sites"])
            messagebox.showinfo("Blocked", f"{domain} is now blocked.\nAll subdomains are covered.", parent=self)
        else:
            existing = []
            if USER_SITES_FILE.exists():
                existing = [s.strip().lower() for s in USER_SITES_FILE.read_text().splitlines()]
            if domain in existing:
                messagebox.showinfo("Already saved", f"{domain} is already in your list.", parent=self)
            else:
                with open(USER_SITES_FILE, "a", encoding="utf-8") as f:
                    f.write(f"{domain}\n")
                messagebox.showinfo("Saved", f"{domain} saved.\nIt will be blocked on next activation.", parent=self)
        self.destroy()


class StatusWindow(_Modal):
    def __init__(self, parent):
        super().__init__(parent, "Status — GAMBLOCK", 400, 280)
        active = is_blocked()
        ctk.CTkLabel(self, text=("●  ACTIVE" if active else "●  INACTIVE"),
                     font=ctk.CTkFont(family=_FONT, size=20, weight="bold"),
                     text_color=_GREEN if active else _RED).pack(pady=(28, 16))
        frame = ctk.CTkFrame(self, fg_color=_CARD, corner_radius=10)
        frame.pack(fill="x", padx=24)
        if active:
            config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            rows = [("Sites blocked", str(len(config["sites"]))),
                    ("Passwords to unlock", "100"),
                    ("TLS cert", "present" if SITE_CERT_FILE.exists() else "missing"),
                    ("Server", "running — auto-starts on boot")]
        else:
            all_s = _all_sites()
            rows = [("Built-in sites", str(len(GAMBLING_SITES))),
                    ("User-added sites", str(len(all_s) - len(GAMBLING_SITES))),
                    ("Total on activate", str(len(all_s)))]
        for k, v in rows:
            row = ctk.CTkFrame(frame, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=5)
            ctk.CTkLabel(row, text=k, font=ctk.CTkFont(family=_FONT, size=12),
                         text_color=_MUTED, width=160, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=v, font=ctk.CTkFont(family=_FONT, size=12, weight="bold"),
                         text_color=_WHITE, anchor="w").pack(side="left")
        ctk.CTkButton(self, text="Close", width=160, height=36,
                       fg_color=_CARD, hover_color=_BORDER,
                       border_width=1, border_color=_BORDER,
                       font=ctk.CTkFont(family=_FONT, size=12),
                       command=self.destroy).pack(pady=20)


class UnblockWindow(_Modal):
    def __init__(self, parent):
        super().__init__(parent, "Unblock — GAMBLOCK", 480, 320)
        self._par    = parent
        self._config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        self._hashed = self._config["hashed_passwords"]
        self._idx    = 0
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="🔓  Unblock GAMBLOCK",
                     font=ctk.CTkFont(family=_FONT, size=16, weight="bold"),
                     text_color=_WHITE).pack(pady=(24, 4))
        self._prog_lbl = ctk.CTkLabel(self, text=f"Password 1 of {len(self._hashed)}",
                                       font=ctk.CTkFont(family=_FONT, size=12), text_color=_MUTED)
        self._prog_lbl.pack()
        self._bar = ctk.CTkProgressBar(self, width=400, height=6,
                                        fg_color=_CARD, progress_color=_RED)
        self._bar.pack(pady=12)
        self._bar.set(0)
        self._entry = ctk.CTkEntry(self, width=400, height=44,
                                    placeholder_text="Type password here — no copy/paste",
                                    font=ctk.CTkFont(family=_FONT, size=13),
                                    fg_color=_CARD, border_color=_BORDER)
        self._entry.pack()
        self._entry.focus()
        _no_paste(self._entry)
        self._entry.bind("<Return>", lambda _: self._check())
        self._fb = ctk.CTkLabel(self, text="", font=ctk.CTkFont(family=_FONT, size=12),
                                 text_color=_MUTED)
        self._fb.pack(pady=8)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack()
        ctk.CTkButton(row, text="Submit", width=190, height=40,
                       font=ctk.CTkFont(family=_FONT, size=13, weight="bold"),
                       fg_color=_RED, hover_color=_RED_H,
                       command=self._check).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="Cancel", width=190, height=40,
                       font=ctk.CTkFont(family=_FONT, size=13),
                       fg_color=_CARD, hover_color=_BORDER,
                       border_width=1, border_color=_BORDER,
                       command=self.destroy).pack(side="left")

    def _check(self):
        pwd = self._entry.get().strip()
        if hash_password(pwd) == self._hashed[self._idx]:
            self._idx += 1
            self._entry.delete(0, "end")
            self._bar.set(self._idx / len(self._hashed))
            if self._idx == len(self._hashed):
                self._fb.configure(text="All correct — unblocking...", text_color=_GREEN)
                self.after(400, self._do_unblock)
            else:
                left = len(self._hashed) - self._idx
                self._prog_lbl.configure(text=f"Password {self._idx + 1} of {len(self._hashed)}")
                self._fb.configure(text=f"✓ Correct — {left} remaining", text_color=_GREEN)
        else:
            self._fb.configure(text="✗ Wrong — try again", text_color=_RED)

    def _do_unblock(self):
        def run():
            _remove_hosts_block()
            restore_dns()
            remove_dns_guard()
            unblock_browser_proxy()
            stop_task()
            remove_task()
            uninstall_ca()
            CONFIG_FILE.unlink(missing_ok=True)
            for f in [CA_CERT_FILE, CA_KEY_FILE, SITE_CERT_FILE, SITE_KEY_FILE]:
                f.unlink(missing_ok=True)
            self.after(0, self._done)
        threading.Thread(target=run, daemon=True).start()

    def _done(self):
        messagebox.showinfo("Unblocked", "All sites unblocked. DNS restored.", parent=self)
        self.destroy()
        if hasattr(self._par, "_refresh"):
            self._par._refresh()


class ActivateWindow(_Modal):
    _STEPS = [
        "Adding hosts entries…",
        "Generating 100 passwords…",
        "Generating TLS certificates…",
        "Installing CA certificate…",
        "Registering startup task…",
        "Configuring DNS…",
        "Installing DNS guard…",
        "Blocking browser extensions…",
        "Starting server…",
    ]

    def __init__(self, parent):
        super().__init__(parent, "Activating — GAMBLOCK", 480, 260)
        self._par = parent
        ctk.CTkLabel(self, text="Activating GAMBLOCK…",
                     font=ctk.CTkFont(family=_FONT, size=16, weight="bold"),
                     text_color=_WHITE).pack(pady=(30, 16))
        self._lbl = ctk.CTkLabel(self, text="Starting…",
                                  font=ctk.CTkFont(family=_FONT, size=12), text_color=_MUTED)
        self._lbl.pack()
        self._bar = ctk.CTkProgressBar(self, width=400, height=8,
                                        fg_color=_CARD, progress_color=_RED)
        self._bar.pack(pady=14)
        self._bar.set(0)
        self._sub = ctk.CTkLabel(self, text="",
                                  font=ctk.CTkFont(family=_FONT, size=11), text_color=_MUTED)
        self._sub.pack()
        self.after(300, self._run)

    def _step(self, i, sub=""):
        self._bar.set(i / len(self._STEPS))
        if i < len(self._STEPS):
            self._lbl.configure(text=self._STEPS[i])
        self._sub.configure(text=sub)
        self.update()

    def _run(self):
        def go():
            sites = _all_sites()
            self.after(0, self._step, 0)
            try:
                _write_hosts_block(sites)
            except PermissionError:
                self.after(0, lambda: messagebox.showerror(
                    "Error", "Cannot write hosts file.\nRun GAMBLOCK as Administrator.", parent=self))
                self.after(0, self.destroy); return

            self.after(0, self._step, 1)
            passwords = generate_passwords()
            config = {"hashed_passwords": [hash_password(p) for p in passwords], "sites": sites}
            CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")

            self.after(0, self._step, 2)
            certs_ok = generate_certs(sites)

            self.after(0, self._step, 3)
            ca_ok = install_ca() if certs_ok else False

            self.after(0, self._step, 4)
            install_task()

            self.after(0, self._step, 5)
            configure_dns()

            self.after(0, self._step, 6)
            install_dns_guard()

            self.after(0, self._step, 7)
            block_browser_proxy()

            self.after(0, self._step, 8)
            start_task()

            lines = ["=" * 62, "  GAMBLOCK — UNBLOCK PASSWORDS", "=" * 62, "",
                     "  Enter ALL 100 passwords in order to unblock.",
                     "  Give this to a trusted person, or print & delete this file.", "",
                     "-" * 62, ""]
            for i, p in enumerate(passwords, 1):
                lines.append(f"  {i:>3}.  {p}")
            lines += ["", "-" * 62, "  GAMBLOCK — gamblock.xyz"]
            PASSWORDS_FILE.write_text("\n".join(lines), encoding="utf-8")

            self.after(0, self._finish, len(sites))
        threading.Thread(target=go, daemon=True).start()

    def _finish(self, n):
        self._bar.set(1.0)
        self._lbl.configure(text="Active!", text_color=_GREEN)
        self._sub.configure(text=f"Blocked {n} sites. Passwords saved to Desktop.", text_color=_GREEN)
        self.update()
        self.after(1000, lambda: self._done())

    def _done(self):
        messagebox.showinfo(
            "GAMBLOCK Active",
            f"Protection is now ON.\n\n"
            f"100 passwords saved to:\n{PASSWORDS_FILE}\n\n"
            f"Give this file to a trusted person, then delete it from your PC.",
            parent=self)
        self.destroy()
        if hasattr(self._par, "_refresh"):
            self._par._refresh()


class GAMBLOCKApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("GAMBLOCK")
        self.geometry("480x390")
        self.resizable(False, False)
        self.configure(fg_color=_BG)
        try:
            ico = INSTALL_DIR / "gamblock.ico"
            if ico.exists():
                self.after(200, lambda: self.iconbitmap(str(ico)))
        except Exception:
            pass
        self._build()
        self._refresh()

    def _build(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=_CARD, corner_radius=0, height=54)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="GAMBLOCK",
                     font=ctk.CTkFont(family=_FONT, size=19, weight="bold"),
                     text_color=_WHITE).pack(side="left", padx=20)
        ctk.CTkLabel(hdr, text="gamblock.xyz",
                     font=ctk.CTkFont(family=_FONT, size=11),
                     text_color=_MUTED).pack(side="right", padx=20)

        # Status card
        sc = ctk.CTkFrame(self, fg_color=_CARD, corner_radius=12)
        sc.pack(fill="x", padx=20, pady=(18, 0))
        inner = ctk.CTkFrame(sc, fg_color="transparent")
        inner.pack(pady=14, padx=20, anchor="w")
        self._dot = ctk.CTkLabel(inner, text="●", font=ctk.CTkFont(size=18), text_color=_MUTED)
        self._dot.pack(side="left", padx=(0, 12))
        col = ctk.CTkFrame(inner, fg_color="transparent")
        col.pack(side="left")
        self._stitle = ctk.CTkLabel(col, text="CHECKING",
                                     font=ctk.CTkFont(family=_FONT, size=15, weight="bold"),
                                     text_color=_MUTED)
        self._stitle.pack(anchor="w")
        self._ssub = ctk.CTkLabel(col, text="",
                                   font=ctk.CTkFont(family=_FONT, size=11), text_color=_MUTED)
        self._ssub.pack(anchor="w")

        # Button grid
        g = ctk.CTkFrame(self, fg_color="transparent")
        g.pack(padx=20, pady=18, fill="x")
        g.columnconfigure((0, 1), weight=1)

        self._btn_act = self._mkbtn(g, "🛡  Activate",  self._activate, 0, 0, True)
        self._mkbtn(g, "＋  Add Site",  self._add_site, 0, 1)
        self._mkbtn(g, "🔓  Unblock",   self._unblock,  1, 0)
        self._mkbtn(g, "ℹ   Status",    self._status,   1, 1)

    def _mkbtn(self, parent, text, cmd, row, col, primary=False):
        b = ctk.CTkButton(
            parent, text=text,
            font=ctk.CTkFont(family=_FONT, size=13, weight="bold"),
            height=58, fg_color=_RED if primary else _CARD,
            hover_color=_RED_H if primary else _BORDER,
            text_color=_WHITE,
            border_width=0 if primary else 1, border_color=_BORDER,
            corner_radius=10, command=cmd)
        b.grid(row=row, column=col,
               padx=(0, 6) if col == 0 else (6, 0),
               pady=(0, 8), sticky="ew")
        return b

    def _refresh(self):
        active = is_blocked()
        if active:
            self._dot.configure(text_color=_GREEN)
            self._stitle.configure(text="ACTIVE", text_color=_GREEN)
            self._ssub.configure(text="Casino protection is on")
            self._btn_act.configure(state="disabled", fg_color=_CARD,
                                     text_color=_MUTED, border_width=1, border_color=_BORDER)
        else:
            self._dot.configure(text_color=_RED)
            self._stitle.configure(text="INACTIVE", text_color=_RED)
            self._ssub.configure(text="Click Activate to enable protection")
            self._btn_act.configure(state="normal", fg_color=_RED,
                                     text_color=_WHITE, border_width=0)

    def _activate(self):
        if is_blocked():
            messagebox.showinfo("Already active", "GAMBLOCK is already active.", parent=self)
            return
        if not messagebox.askyesno(
                "Activate GAMBLOCK",
                f"This will block {len(_all_sites())} casino sites and all subdomains.\n\n"
                "100 passwords will be saved to your Desktop.\n"
                "Give them to a trusted person, then delete the file.\n\nContinue?",
                parent=self):
            return
        ActivateWindow(self)

    def _add_site(self):
        AddSiteDialog(self)

    def _unblock(self):
        if not is_blocked():
            messagebox.showinfo("Not active", "GAMBLOCK is not currently active.", parent=self)
            return
        UnblockWindow(self)

    def _status(self):
        StatusWindow(self)


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    if not is_admin():
        # Re-launch elevated
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable,
            " ".join(f'"{a}"' for a in sys.argv), None, 1)
        sys.exit(0)
    app = GAMBLOCKApp()
    app.mainloop()

if __name__ == "__main__":
    main()
