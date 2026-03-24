# GAMBLOCK

A self-imposed crypto casino blocker for Windows. When you visit a blocked site, instead of loading it, your browser shows:

> **YOU SAID YOU'D QUIT!**
> ENTER PASSWORDS 0 / 100

To unblock, you must type 100 randomly generated passwords — one by one, no copy/paste. Give the password list to someone you trust, or print it and destroy the digital copy.

---

## How It Works

- **Hosts file** — redirects blocked domains to your local machine before any DNS or VPN can reach them
- **Local DNS server** — catches every subdomain automatically (`live.stake.com`, `sports.stake.com`, etc.)
- **Local HTTPS server** — serves the custom blocking page with a password form directly in your browser
- **TLS certificate** — installed into Windows trust store so there are no certificate warnings
- **Task Scheduler** — the server restarts automatically every time your PC boots

Works with most VPNs. Survives browser changes. Requires 100 typed passwords to undo.

---

## Requirements

- Windows 10 or 11
- Python 3.8 or later — [python.org/downloads](https://www.python.org/downloads/)

---

## Installation

**1. Download GAMBLOCK**

Click the green **Code** button → **Download ZIP** → extract it anywhere (Desktop is fine).

**2. Run the installer**

Right-click `install.bat` → **Run as administrator**

This installs the required Python dependency and confirms your setup is ready.

**3. Activate GAMBLOCK**

Right-click `site_blocker.bat` → **Run as administrator** → choose **1. Activate blocker**

GAMBLOCK will:
- Block all sites in the list (+ every subdomain)
- Generate 100 random passwords and save them to your Desktop as `GAMBLOCK_PASSWORDS.txt`
- Install a background server that persists across reboots

**4. Secure the passwords**

Do one of these — don't skip this step:
- Email `GAMBLOCK_PASSWORDS.txt` to a trusted friend or family member, then delete it
- Print it and physically destroy the digital copy
- Put it somewhere you genuinely cannot easily access

---

## Usage

Right-click `site_blocker.bat` → Run as administrator

```
  1. Activate blocker
  2. Unblock (requires 100 passwords)
  3. Add a site to block list
  4. Status
  5. Exit
```

### Adding a site

Choose option **3** and enter the domain (e.g. `newcasino.com`).

- If GAMBLOCK is **active**: the site is blocked immediately
- If GAMBLOCK is **inactive**: the site is saved and will be blocked on next activation
- Sites can be added but **never removed** without the 100 passwords

---

## Default blocked sites

| Site | Site | Site |
|------|------|------|
| stake.com | rollbit.com | roobet.com |
| shuffle.com | bc.game | duelbits.com |
| duel.com | chips.gg | gamdom.com |
| thunderpick.io | bitstarz.com | betfury.io |
| mystake.com | bets.io | wild.io |
| jackbit.com | vave.com | flush.com |
| fortunejack.com | mbitcasino.com | cloudbet.com |
| sportsbet.io | winz.io | haz.casino |
| katsubet.com | metaspins.com | primedice.com |
| wolfbet.com | crashino.com | donbet.com |
| csgoempire.com | | |

All `www.` variants and every subdomain are blocked automatically.

---

## Unblocking

Open `site_blocker.bat` as administrator → choose **2. Unblock**

You will be asked to type all 100 passwords in order. There is no way around this without the password list. This is intentional.

---

## Frequently Asked Questions

**Does it work with a VPN?**
Yes. The hosts file is resolved before DNS, and our local DNS server handles subdomains — both layers operate below the VPN.

**What if I visit `stake.com/slots`?**
Blocked. The path after the domain is irrelevant — the block happens at the DNS/hosts level before the browser even connects.

**What about `live.stake.com` or other subdomains?**
Blocked. The local DNS server catches all `*.stake.com` variants automatically.

**Can I remove a site from the list?**
Not while GAMBLOCK is active. You must unblock (100 passwords) to change the site list, then reactivate.

**What if I reinstall Windows?**
GAMBLOCK would be removed. If you're serious about this, give your password list to someone else — that way unblocking requires their cooperation too.

**Is my data sent anywhere?**
No. Everything runs locally on your machine. No analytics, no network calls, no accounts.

---

## Getting Help

If you're struggling with gambling, you don't have to do this alone:

- **National Problem Gambling Helpline**: 1-800-522-4700 (US, 24/7)
- **GamCare**: gamcare.org.uk (UK)
- **Gambling Therapy**: gamblingtherapy.org (international, free)
- **Gamblers Anonymous**: gamblersanonymous.org

---

## License

MIT — free to use, share, and modify.
