"""
GAMBLOCK Admin Panel
====================
Run this on YOUR PC only. Never distribute.
Requires: pip install requests customtkinter
"""

import hashlib
import hmac
import json
import threading
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

import customtkinter as ctk
import requests
from tkinter import messagebox

# ── Config ─────────────────────────────────────────────────────────────────────
CONFIG_FILE = Path(__file__).parent / "admin_config.json"

def _load_cfg():
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}

def _save_cfg(cfg):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))

# ── Admin unlock (same secret as site_blocker.py) ──────────────────────────────
ADMIN_SECRET = b"gb-x9K#mP2qNvTz8wRcLdYeAuF5sJh"

def generate_code(install_id: str) -> str:
    return hmac.new(ADMIN_SECRET, install_id.strip().upper().encode(), hashlib.sha256).hexdigest()[:12].upper()

# ── Supabase helpers ────────────────────────────────────────────────────────────
def sb_headers(key):
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}

def fetch_installs(url, key):
    r = requests.get(f"{url}/rest/v1/installs?select=*&order=activated_at.desc", headers=sb_headers(key), timeout=10)
    r.raise_for_status()
    return r.json()

def mark_unlocked(url, key, install_id, method):
    now = datetime.now(timezone.utc).isoformat()
    r = requests.patch(
        f"{url}/rest/v1/installs?install_id=eq.{install_id}",
        headers={**sb_headers(key), "Prefer": "return=representation"},
        json={"unlocked_at": now, "unlock_method": method},
        timeout=10)
    r.raise_for_status()

def fetch_github_downloads():
    r = requests.get("https://api.github.com/repos/Xipezyy/GAMBLOCK/releases/latest", timeout=8)
    data = r.json()
    return sum(a["download_count"] for a in data.get("assets", []))

# ── Theme ───────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
_BG     = "#0d0d0d"
_CARD   = "#161616"
_BORDER = "#252525"
_RED    = "#dc2626"
_GREEN  = "#16a34a"
_BLUE   = "#4ab3ff"
_WHITE  = "#f5f5f5"
_MUTED  = "#6b7280"
_FONT   = "Segoe UI"


# ── Setup window ────────────────────────────────────────────────────────────────
class SetupWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("GAMBLOCK Admin — Setup")
        self.geometry("520x340")
        self.resizable(False, False)
        self.configure(fg_color=_BG)
        self._result = None

        ctk.CTkLabel(self, text="GAMBLOCK Admin Setup",
                     font=ctk.CTkFont(family=_FONT, size=18, weight="bold"),
                     text_color=_WHITE).pack(pady=(28, 4))
        ctk.CTkLabel(self, text="Enter your Supabase credentials to connect.",
                     font=ctk.CTkFont(family=_FONT, size=12), text_color=_MUTED).pack(pady=(0, 20))

        frame = ctk.CTkFrame(self, fg_color=_CARD, corner_radius=10)
        frame.pack(fill="x", padx=28)

        ctk.CTkLabel(frame, text="Supabase Project URL",
                     font=ctk.CTkFont(family=_FONT, size=11), text_color=_MUTED, anchor="w").pack(padx=16, pady=(14,2), anchor="w")
        self._url = ctk.CTkEntry(frame, width=460, height=38, placeholder_text="https://xxxx.supabase.co",
                                  fg_color=_BG, border_color=_BORDER,
                                  font=ctk.CTkFont(family=_FONT, size=12))
        self._url.pack(padx=16, pady=(0, 10))

        ctk.CTkLabel(frame, text="Anon Public Key",
                     font=ctk.CTkFont(family=_FONT, size=11), text_color=_MUTED, anchor="w").pack(padx=16, anchor="w")
        self._key = ctk.CTkEntry(frame, width=460, height=38, placeholder_text="eyJhbGci...",
                                  fg_color=_BG, border_color=_BORDER,
                                  font=ctk.CTkFont(family=_FONT, size=12))
        self._key.pack(padx=16, pady=(2, 14))

        # Pre-fill if saved
        cfg = _load_cfg()
        if cfg.get("url"):  self._url.insert(0, cfg["url"])
        if cfg.get("key"):  self._key.insert(0, cfg["key"])

        ctk.CTkButton(self, text="Connect", width=460, height=42,
                       font=ctk.CTkFont(family=_FONT, size=13, weight="bold"),
                       fg_color=_RED, hover_color="#b91c1c",
                       command=self._connect).pack(padx=28, pady=16)

    def _connect(self):
        url = self._url.get().strip().rstrip("/")
        key = self._key.get().strip()
        if not url or not key:
            messagebox.showerror("Missing", "Both fields are required.", parent=self)
            return
        try:
            fetch_installs(url, key)
            _save_cfg({"url": url, "key": key})
            self._result = (url, key)
            self.destroy()
        except Exception as e:
            messagebox.showerror("Connection failed", str(e), parent=self)


# ── Main admin panel ─────────────────────────────────────────────────────────────
class AdminPanel(ctk.CTk):
    def __init__(self, url, key):
        super().__init__()
        self._url  = url
        self._key  = key
        self._data = []
        self.title("GAMBLOCK Admin")
        self.geometry("1050x680")
        self.minsize(900, 560)
        self.configure(fg_color=_BG)
        self._build()
        self._refresh()

    def _build(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=_CARD, corner_radius=0, height=52)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="GAMBLOCK",
                     font=ctk.CTkFont(family=_FONT, size=18, weight="bold"),
                     text_color=_WHITE).pack(side="left", padx=20)
        ctk.CTkLabel(hdr, text="Admin Panel",
                     font=ctk.CTkFont(family=_FONT, size=12), text_color=_MUTED).pack(side="left")
        ctk.CTkButton(hdr, text="↺  Refresh", width=100, height=32,
                       font=ctk.CTkFont(family=_FONT, size=12),
                       fg_color=_BORDER, hover_color="#333",
                       command=self._refresh).pack(side="right", padx=16)

        # Stats row
        stats = ctk.CTkFrame(self, fg_color="transparent")
        stats.pack(fill="x", padx=20, pady=(14, 0))
        self._stat_total    = self._stat_card(stats, "Total Installs",   "—")
        self._stat_active   = self._stat_card(stats, "Currently Active", "—")
        self._stat_unlocked = self._stat_card(stats, "Unlocked",         "—")
        self._stat_dl       = self._stat_card(stats, "GitHub Downloads", "—")

        # Unlock code generator
        gen = ctk.CTkFrame(self, fg_color=_CARD, corner_radius=10)
        gen.pack(fill="x", padx=20, pady=(14, 0))
        inner = ctk.CTkFrame(gen, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=12)
        ctk.CTkLabel(inner, text="Unlock Code Generator",
                     font=ctk.CTkFont(family=_FONT, size=13, weight="bold"),
                     text_color=_WHITE).pack(side="left", padx=(0,16))
        self._gen_entry = ctk.CTkEntry(inner, width=260, height=36,
                                        placeholder_text="Paste Install ID from user's DM",
                                        fg_color=_BG, border_color=_BORDER,
                                        font=ctk.CTkFont(family="Courier New", size=11))
        self._gen_entry.pack(side="left", padx=(0, 8))
        self._gen_entry.bind("<Return>", lambda _: self._gen_code())
        ctk.CTkButton(inner, text="Generate Code", width=140, height=36,
                       font=ctk.CTkFont(family=_FONT, size=12, weight="bold"),
                       fg_color=_RED, hover_color="#b91c1c",
                       command=self._gen_code).pack(side="left", padx=(0, 12))
        self._gen_result = ctk.CTkLabel(inner, text="",
                                         font=ctk.CTkFont(family="Courier New", size=14, weight="bold"),
                                         text_color=_GREEN)
        self._gen_result.pack(side="left")
        self._copy_btn = ctk.CTkButton(inner, text="Copy", width=60, height=36,
                                        font=ctk.CTkFont(family=_FONT, size=11),
                                        fg_color=_BORDER, hover_color="#333",
                                        command=self._copy_code, state="disabled")
        self._copy_btn.pack(side="left", padx=(8, 0))
        self._last_code = ""

        # Installs table header
        th = ctk.CTkFrame(self, fg_color=_CARD, corner_radius=0, height=36)
        th.pack(fill="x", padx=20, pady=(14, 0))
        th.pack_propagate(False)
        for txt, w in [("Install ID", 180), ("Activated", 180), ("Status", 100), ("Method", 110), ("Actions", 200)]:
            ctk.CTkLabel(th, text=txt,
                         font=ctk.CTkFont(family=_FONT, size=11, weight="bold"),
                         text_color=_MUTED, width=w, anchor="w").pack(side="left", padx=(12,0))

        # Scrollable installs list
        self._scroll = ctk.CTkScrollableFrame(self, fg_color=_BG, corner_radius=0)
        self._scroll.pack(fill="both", expand=True, padx=20, pady=(2, 20))

    def _stat_card(self, parent, label, value):
        card = ctk.CTkFrame(parent, fg_color=_CARD, corner_radius=10)
        card.pack(side="left", expand=True, fill="x", padx=(0, 10))
        val_lbl = ctk.CTkLabel(card, text=value,
                                font=ctk.CTkFont(family=_FONT, size=26, weight="bold"),
                                text_color=_WHITE)
        val_lbl.pack(pady=(14, 2))
        ctk.CTkLabel(card, text=label,
                     font=ctk.CTkFont(family=_FONT, size=11), text_color=_MUTED).pack(pady=(0, 14))
        return val_lbl

    def _refresh(self):
        def go():
            try:
                data = fetch_installs(self._url, self._key)
                dl   = fetch_github_downloads()
                self.after(0, self._render, data, dl)
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error", str(e), parent=self))
        threading.Thread(target=go, daemon=True).start()

    def _render(self, data, dl):
        self._data = data
        total    = len(data)
        unlocked = sum(1 for r in data if r.get("unlocked_at"))
        active   = total - unlocked
        self._stat_total.configure(text=str(total))
        self._stat_active.configure(text=str(active))
        self._stat_unlocked.configure(text=str(unlocked))
        self._stat_dl.configure(text=str(41 + dl))

        for w in self._scroll.winfo_children():
            w.destroy()

        for row in data:
            self._row(row)

    def _row(self, row):
        iid       = row["install_id"]
        activated = row.get("activated_at", "")
        if activated:
            try:
                dt = datetime.fromisoformat(activated.replace("Z", "+00:00"))
                activated = dt.strftime("%d %b %Y  %H:%M")
            except Exception:
                pass
        unlocked  = bool(row.get("unlocked_at"))
        method    = row.get("unlock_method") or "—"

        fr = ctk.CTkFrame(self._scroll, fg_color=_CARD, corner_radius=8, height=48)
        fr.pack(fill="x", pady=(0, 4))
        fr.pack_propagate(False)

        ctk.CTkLabel(fr, text=iid,
                     font=ctk.CTkFont(family="Courier New", size=11),
                     text_color=_BLUE, width=180, anchor="w").pack(side="left", padx=(12, 0))
        ctk.CTkLabel(fr, text=activated,
                     font=ctk.CTkFont(family=_FONT, size=11), text_color=_WHITE,
                     width=180, anchor="w").pack(side="left", padx=(12, 0))
        status_color = _MUTED if unlocked else _GREEN
        status_text  = "Unlocked" if unlocked else "● Active"
        ctk.CTkLabel(fr, text=status_text,
                     font=ctk.CTkFont(family=_FONT, size=11, weight="bold"),
                     text_color=status_color, width=100, anchor="w").pack(side="left", padx=(12, 0))
        ctk.CTkLabel(fr, text=method,
                     font=ctk.CTkFont(family=_FONT, size=11), text_color=_MUTED,
                     width=110, anchor="w").pack(side="left", padx=(12, 0))

        # Action buttons
        btn_row = ctk.CTkFrame(fr, fg_color="transparent")
        btn_row.pack(side="left", padx=(8, 0))

        ctk.CTkButton(btn_row, text="Get Code", width=80, height=28,
                       font=ctk.CTkFont(family=_FONT, size=10),
                       fg_color=_BORDER, hover_color="#333",
                       command=lambda i=iid: self._quick_code(i)).pack(side="left", padx=(0, 6))

        if not unlocked:
            ctk.CTkButton(btn_row, text="Mark Unlocked", width=110, height=28,
                           font=ctk.CTkFont(family=_FONT, size=10),
                           fg_color=_GREEN, hover_color="#15803d",
                           command=lambda i=iid: self._mark_unlocked(i)).pack(side="left")

    def _gen_code(self):
        iid = self._gen_entry.get().strip().upper()
        if not iid:
            return
        code = generate_code(iid)
        self._last_code = code
        self._gen_result.configure(text=code)
        self._copy_btn.configure(state="normal")

    def _copy_code(self):
        if self._last_code:
            self.clipboard_clear()
            self.clipboard_append(self._last_code)
            self._gen_result.configure(text=f"{self._last_code}  ✓ Copied!")

    def _quick_code(self, iid):
        code = generate_code(iid)
        self.clipboard_clear()
        self.clipboard_append(code)
        messagebox.showinfo("Unlock Code", f"Install ID: {iid}\n\nUnlock Code: {code}\n\n(Copied to clipboard)", parent=self)

    def _mark_unlocked(self, iid):
        method = "manual"
        try:
            mark_unlocked(self._url, self._key, iid, method)
            self._refresh()
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)


# ── Entry ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    cfg = _load_cfg()
    if cfg.get("url") and cfg.get("key"):
        try:
            fetch_installs(cfg["url"], cfg["key"])
            app = AdminPanel(cfg["url"], cfg["key"])
        except Exception:
            setup = SetupWindow()
            setup.mainloop()
            if setup._result:
                app = AdminPanel(*setup._result)
            else:
                exit()
    else:
        setup = SetupWindow()
        setup.mainloop()
        if setup._result:
            app = AdminPanel(*setup._result)
        else:
            exit()
    app.mainloop()
