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
from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────────────────────

SCRIPT_DIR     = Path(__file__).parent.resolve()
CONFIG_FILE    = SCRIPT_DIR / "config.json"
CA_CERT_FILE   = SCRIPT_DIR / "ca_cert.pem"
CA_KEY_FILE    = SCRIPT_DIR / "ca_key.pem"
SITE_CERT_FILE = SCRIPT_DIR / "site_cert.pem"
SITE_KEY_FILE  = SCRIPT_DIR / "site_key.pem"
USER_SITES_FILE = SCRIPT_DIR / "user_sites.txt"
PASSWORDS_FILE = Path(os.path.expanduser("~")) / "OneDrive" / "Desktop" / "GAMBLOCK_PASSWORDS.txt"

HOSTS_FILE   = r"C:\Windows\System32\drivers\etc\hosts"
MARKER_START = "# === SITE BLOCKER START ==="
MARKER_END   = "# === SITE BLOCKER END ==="
TASK_NAME    = "SiteBlockerServer"

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
        print("  Right-click site_blocker.bat → 'Run as administrator'.")
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

# ─── DNS configuration ────────────────────────────────────────────────────────

def configure_dns():
    """Point all active adapters at our local DNS server (primary) + 8.8.8.8 (fallback)."""
    subprocess.run([
        "powershell", "-Command",
        "Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | "
        "ForEach-Object { Set-DnsClientServerAddress -InterfaceAlias $_.Name "
        "-ServerAddresses '127.0.0.1','8.8.8.8' }"
    ], capture_output=True)

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
    cmd = f'"{sys.executable}" "{SCRIPT_DIR / "blocker_server.py"}"'
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

# ─── Block ────────────────────────────────────────────────────────────────────

def cmd_block():
    if is_blocked():
        print("  [INFO] Blocker is already active.")
        input("\nPress Enter to exit...")
        return

    sites = _all_sites()

    print("=" * 62)
    print("  SITE BLOCKER — ACTIVATE")
    print("=" * 62)
    print(f"\n  Domains to block : {len(sites)} (+ www. variants + all subdomains)")
    print("  Subdomain cover  : live.stake.com, sports.stake.com, etc.")
    print("  Browser page     : 'YOU SAID YOU'D QUIT!' with password form")
    print("  Passwords needed : 100 (typed — no copy/paste)\n")
    if input("  Type YES to activate: ").strip() != "YES":
        print("  Aborted.")
        return

    print("\n  [1/7] Adding hosts entries...")
    try:
        _write_hosts_block(sites)
    except PermissionError:
        print("  [ERROR] Cannot write hosts file. Run as Administrator.")
        input("\nPress Enter to exit...")
        return

    print("  [2/7] Generating 100 passwords...")
    passwords = generate_passwords()
    config    = {"hashed_passwords": [hash_password(p) for p in passwords], "sites": sites}
    CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")

    print("  [3/7] Generating TLS certificates...")
    certs_ok = generate_certs(sites)

    print("  [4/7] Installing CA in Windows trust store...")
    ca_ok = install_ca() if certs_ok else False
    if certs_ok and not ca_ok:
        print("        [WARN] CA install failed — HTTPS shows cert warning.")

    print("  [5/7] Registering background server (Task Scheduler)...")
    if not install_task():
        print("        [WARN] Task Scheduler failed — server won't auto-start after reboot.")

    print("  [6/7] Configuring DNS (blocks all subdomains)...")
    configure_dns()

    print("  [7/7] Starting server now...")
    start_task()

    # Write password file
    lines = ["=" * 62, "  SITE BLOCKER — UNBLOCK PASSWORDS", "=" * 62, "",
             "  Enter ALL 100 passwords in order to unblock.",
             "  Give this to a trusted person, or print & delete this file.", "",
             "-" * 62, ""]
    for i, p in enumerate(passwords, 1):
        lines.append(f"  {i:>3}.  {p}")
    lines += ["", "-" * 62, "  site_blocker.py"]
    PASSWORDS_FILE.write_text("\n".join(lines), encoding="utf-8")

    print("\n" + "=" * 62)
    print("  BLOCKER ACTIVE")
    print("=" * 62)
    print(f"\n  Blocked {len(sites)} domains + all subdomains.")
    print(f"  HTTPS  : {'seamless — CA installed' if ca_ok else 'cert warning (click Advanced > Proceed)'}")
    print(f"\n  Passwords saved to:\n    {PASSWORDS_FILE}")
    print("\n  Give the password file to someone you trust, then delete it.")
    input("\nPress Enter to exit...")

# ─── Add site ─────────────────────────────────────────────────────────────────

def cmd_add():
    print("=" * 62)
    print("  SITE BLOCKER — ADD SITE")
    print("=" * 62)
    print("\n  Enter the domain you want to block (e.g. newcasino.com).")
    print("  Once added, it cannot be removed without the 100 passwords.\n")

    raw    = input("  Domain: ").strip().lower()
    domain = raw.replace("https://", "").replace("http://", "").split("/")[0].strip(".")

    if not domain or "." not in domain:
        print("  Invalid domain.")
        input("\nPress Enter to exit...")
        return

    if is_blocked():
        config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        if domain in config["sites"]:
            print(f"  {domain} is already blocked.")
            input("\nPress Enter to exit...")
            return

        # Update config
        config["sites"].append(domain)
        CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")

        # Re-write hosts block with new site
        _remove_hosts_block()
        _write_hosts_block(config["sites"])

        print(f"\n  Blocked: {domain}")
        print(f"  Also blocked: www.{domain} and all subdomains (*.{domain})")
        print("  Takes effect immediately.")
    else:
        # Save to user_sites.txt for next activation
        existing = []
        if USER_SITES_FILE.exists():
            existing = [s.strip().lower() for s in USER_SITES_FILE.read_text().splitlines()]
        if domain in existing:
            print(f"  {domain} is already in your list.")
        else:
            with open(USER_SITES_FILE, "a", encoding="utf-8") as f:
                f.write(f"{domain}\n")
            print(f"\n  Saved: {domain}")
            print("  It will be blocked when you activate the blocker.")

    input("\nPress Enter to exit...")

# ─── Unblock (CLI) ────────────────────────────────────────────────────────────

def cmd_unblock():
    if not is_blocked():
        print("  [INFO] Blocker is not active.")
        input("\nPress Enter to exit...")
        return

    config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    hashed = config["hashed_passwords"]

    print("=" * 62)
    print("  SITE BLOCKER — UNBLOCK")
    print("=" * 62)
    print(f"\n  Enter all {len(hashed)} passwords in order. No shortcuts.\n")
    if input("  Type YES to begin: ").strip() != "YES":
        print("  Aborted.")
        input("\nPress Enter to exit...")
        return

    print()
    for i, expected in enumerate(hashed, 1):
        while True:
            try:
                pwd = input(f"  Password {i:>3}/{len(hashed)} : ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\n\n  Aborted. Sites remain blocked.")
                input("\nPress Enter to exit...")
                return
            if hash_password(pwd) == expected:
                left = len(hashed) - i
                print(f"             Correct.{f'  {left} left.' if left else ''}\n")
                break
            else:
                print("             Wrong. Try again.\n")

    print("  Removing hosts entries...")
    _remove_hosts_block()
    print("  Restoring DNS...")
    restore_dns()
    print("  Stopping server...")
    stop_task()
    remove_task()
    print("  Uninstalling CA...")
    uninstall_ca()
    CONFIG_FILE.unlink(missing_ok=True)
    for f in [CA_CERT_FILE, CA_KEY_FILE, SITE_CERT_FILE, SITE_KEY_FILE]:
        f.unlink(missing_ok=True)

    print("\n" + "=" * 62)
    print("  UNBLOCKED")
    print("=" * 62)
    print("\n  All sites unblocked. DNS restored.")
    input("\nPress Enter to exit...")

# ─── Status ───────────────────────────────────────────────────────────────────

def cmd_status():
    print("=" * 62)
    print("  SITE BLOCKER — STATUS")
    print("=" * 62)
    if is_blocked():
        config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        print(f"\n  Status     : ACTIVE")
        print(f"  Domains    : {len(config['sites'])} sites (+ www. + all subdomains via DNS)")
        print(f"  Passwords  : {len(config['hashed_passwords'])} required to unblock")
        print(f"  TLS cert   : {'present' if SITE_CERT_FILE.exists() else 'missing'}")
    else:
        all_s = _all_sites()
        print(f"\n  Status          : INACTIVE")
        print(f"  Built-in sites  : {len(GAMBLING_SITES)}")
        print(f"  User-added sites: {len(all_s) - len(GAMBLING_SITES)}")
        print(f"  Total on activate: {len(all_s)}")
    input("\nPress Enter to exit...")

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    require_admin()

    if len(sys.argv) > 1:
        {
            "block":   cmd_block,
            "unblock": cmd_unblock,
            "add":     cmd_add,
            "status":  cmd_status,
        }.get(sys.argv[1].lower(), lambda: print(f"Unknown command: {sys.argv[1]}"))()
        return

    print("=" * 62)
    print("  SITE BLOCKER")
    print("=" * 62)
    print(f"\n  Status: {'ACTIVE — sites are BLOCKED' if is_blocked() else 'INACTIVE'}\n")
    print("  1. Activate blocker")
    print("  2. Unblock (requires 100 passwords)")
    print("  3. Add a site to block list")
    print("  4. Status")
    print("  5. Exit")
    print()
    match input("  Choose [1-5]: ").strip():
        case "1": cmd_block()
        case "2": cmd_unblock()
        case "3": cmd_add()
        case "4": cmd_status()
        case _:   print("  Goodbye.")

if __name__ == "__main__":
    main()
