"""
GAMBLOCK Admin Panel
====================
Run this on YOUR PC only. Never distribute.
Requires: pip install requests customtkinter
"""

import hashlib
import hmac
import threading
import webbrowser

import customtkinter as ctk
import requests
from tkinter import messagebox

# ── Admin unlock (same secret as site_blocker.py) ─────────────────────────────
ADMIN_SECRET = b"gb-x9K#mP2qNvTz8wRcLdYeAuF5sJh"

def generate_code(install_id: str) -> str:
    return hmac.new(ADMIN_SECRET, install_id.strip().upper().encode(), hashlib.sha256).hexdigest()[:12].upper()

def fetch_github_stats():
    r = requests.get("https://api.github.com/repos/Xipezyy/GAMBLOCK/releases/latest", timeout=8)
    data = r.json()
    downloads = sum(a["download_count"] for a in data.get("assets", []))
    return 41 + downloads, data.get("name", "—"), data.get("published_at", "")[:10]

# ── Theme ──────────────────────────────────────────────────────────────────────
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


class AdminPanel(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("GAMBLOCK Admin")
        self.geometry("620x540")
        self.resizable(False, False)
        self.configure(fg_color=_BG)
        self._last_code = ""
        self._build()
        self._refresh_stats()

    def _build(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=_CARD, corner_radius=0, height=52)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="GAMBLOCK",
                     font=ctk.CTkFont(family=_FONT, size=18, weight="bold"),
                     text_color=_WHITE).pack(side="left", padx=20)
        ctk.CTkLabel(hdr, text="Admin Panel",
                     font=ctk.CTkFont(family=_FONT, size=12),
                     text_color=_MUTED).pack(side="left")
        ctk.CTkButton(hdr, text="↺  Refresh", width=100, height=32,
                       font=ctk.CTkFont(family=_FONT, size=12),
                       fg_color=_BORDER, hover_color="#333",
                       command=self._refresh_stats).pack(side="right", padx=16)

        # Stats row
        stats = ctk.CTkFrame(self, fg_color="transparent")
        stats.pack(fill="x", padx=20, pady=16)
        self._dl_lbl      = self._stat_card(stats, "Total Downloads", "—")
        self._version_lbl = self._stat_card(stats, "Latest Version",  "—")
        self._date_lbl    = self._stat_card(stats, "Released",        "—")

        # Discord info
        discord = ctk.CTkFrame(self, fg_color=_CARD, corner_radius=10)
        discord.pack(fill="x", padx=20, pady=(0, 14))
        row = ctk.CTkFrame(discord, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=14)
        ctk.CTkLabel(row, text="📡",
                     font=ctk.CTkFont(size=20)).pack(side="left", padx=(0, 12))
        col = ctk.CTkFrame(row, fg_color="transparent")
        col.pack(side="left")
        ctk.CTkLabel(col, text="Live installs appear in your Discord channel",
                     font=ctk.CTkFont(family=_FONT, size=13, weight="bold"),
                     text_color=_WHITE).pack(anchor="w")
        ctk.CTkLabel(col, text="Each activation pings your #installs channel with the Install ID.",
                     font=ctk.CTkFont(family=_FONT, size=11),
                     text_color=_MUTED).pack(anchor="w")

        # Divider
        ctk.CTkFrame(self, fg_color=_BORDER, height=1).pack(fill="x", padx=20, pady=(0, 14))

        # Unlock code generator
        ctk.CTkLabel(self, text="Unlock Code Generator",
                     font=ctk.CTkFont(family=_FONT, size=15, weight="bold"),
                     text_color=_WHITE).pack(anchor="w", padx=20)
        ctk.CTkLabel(self,
                     text="Copy the Install ID from Discord, paste it below to get their unlock code.",
                     font=ctk.CTkFont(family=_FONT, size=11),
                     text_color=_MUTED).pack(anchor="w", padx=20, pady=(2, 14))

        gen = ctk.CTkFrame(self, fg_color=_CARD, corner_radius=10)
        gen.pack(fill="x", padx=20)

        ctk.CTkLabel(gen, text="Install ID",
                     font=ctk.CTkFont(family=_FONT, size=11), text_color=_MUTED,
                     anchor="w").pack(padx=16, pady=(14, 4), anchor="w")
        self._id_entry = ctk.CTkEntry(gen, width=560, height=42,
                                       placeholder_text="e.g. A1B2C3D4E5F6G7H8",
                                       font=ctk.CTkFont(family="Courier New", size=13),
                                       fg_color=_BG, border_color=_BORDER)
        self._id_entry.pack(padx=16)
        self._id_entry.bind("<Return>", lambda _: self._gen_code())

        ctk.CTkButton(gen, text="Generate Unlock Code", width=560, height=42,
                       font=ctk.CTkFont(family=_FONT, size=13, weight="bold"),
                       fg_color=_RED, hover_color="#b91c1c",
                       command=self._gen_code).pack(padx=16, pady=10)

        # Result
        result_frame = ctk.CTkFrame(self, fg_color=_CARD, corner_radius=10)
        result_frame.pack(fill="x", padx=20, pady=14)
        result_inner = ctk.CTkFrame(result_frame, fg_color="transparent")
        result_inner.pack(fill="x", padx=16, pady=16)
        ctk.CTkLabel(result_inner, text="Unlock Code:",
                     font=ctk.CTkFont(family=_FONT, size=12), text_color=_MUTED).pack(side="left", padx=(0, 12))
        self._code_lbl = ctk.CTkLabel(result_inner, text="—",
                                       font=ctk.CTkFont(family="Courier New", size=20, weight="bold"),
                                       text_color=_GREEN)
        self._code_lbl.pack(side="left")
        self._copy_btn = ctk.CTkButton(result_inner, text="Copy", width=80, height=36,
                                        font=ctk.CTkFont(family=_FONT, size=12, weight="bold"),
                                        fg_color=_BORDER, hover_color="#333",
                                        command=self._copy_code, state="disabled")
        self._copy_btn.pack(side="right")

        # Instructions
        ctk.CTkLabel(self,
                     text="DM the code back to the user on Twitter/X  •  Then donate their $200 to GamCare",
                     font=ctk.CTkFont(family=_FONT, size=11),
                     text_color=_MUTED).pack(pady=(0, 10))

    def _stat_card(self, parent, label, value):
        card = ctk.CTkFrame(parent, fg_color=_CARD, corner_radius=10)
        card.pack(side="left", expand=True, fill="x", padx=(0, 10))
        val = ctk.CTkLabel(card, text=value,
                            font=ctk.CTkFont(family=_FONT, size=24, weight="bold"),
                            text_color=_WHITE)
        val.pack(pady=(14, 2))
        ctk.CTkLabel(card, text=label,
                     font=ctk.CTkFont(family=_FONT, size=11), text_color=_MUTED).pack(pady=(0, 14))
        return val

    def _refresh_stats(self):
        def go():
            try:
                dl, version, date = fetch_github_stats()
                self.after(0, lambda: self._dl_lbl.configure(text=str(dl)))
                self.after(0, lambda: self._version_lbl.configure(text=version))
                self.after(0, lambda: self._date_lbl.configure(text=date))
            except Exception:
                pass
        threading.Thread(target=go, daemon=True).start()

    def _gen_code(self):
        iid = self._id_entry.get().strip().upper()
        if not iid:
            messagebox.showwarning("Missing", "Paste an Install ID first.", parent=self)
            return
        code = generate_code(iid)
        self._last_code = code
        self._code_lbl.configure(text=code)
        self._copy_btn.configure(state="normal")

    def _copy_code(self):
        if self._last_code:
            self.clipboard_clear()
            self.clipboard_append(self._last_code)
            self._code_lbl.configure(text=f"{self._last_code}  ✓")
            self.after(2000, lambda: self._code_lbl.configure(text=self._last_code))


if __name__ == "__main__":
    app = AdminPanel()
    app.mainloop()
