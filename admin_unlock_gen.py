"""
GAMBLOCK Admin Unlock Code Generator
=====================================
Run this when a user DMs you their Install ID + payment proof.
Copy the code and DM it back to them.

Usage:
    python admin_unlock_gen.py
"""

import hashlib
import hmac

ADMIN_SECRET = b"gb-x9K#mP2qNvTz8wRcLdYeAuF5sJh"

def generate_code(install_id: str) -> str:
    return hmac.new(ADMIN_SECRET, install_id.strip().upper().encode(), hashlib.sha256).hexdigest()[:12].upper()

if __name__ == "__main__":
    print("=" * 50)
    print("  GAMBLOCK — Admin Unlock Code Generator")
    print("=" * 50)
    install_id = input("\nPaste Install ID from user's DM: ").strip().upper()
    if not install_id:
        print("No ID entered.")
    else:
        code = generate_code(install_id)
        print(f"\n  Unlock code: {code}")
        print(f"\n  DM this to the user: {code}")
        print("\n  (They paste it in GAMBLOCK → Unblock → Donate to Unlock)")
    input("\nPress Enter to exit...")
