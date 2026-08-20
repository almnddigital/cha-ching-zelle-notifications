# Cha-Ching Payment Notifications — GUI App

Your front desk Windows PC announces Zelle payments out loud the moment they arrive.

---

## For End Users (Front Desk PC)

1. **Download `ChaChing.exe`** — copy it anywhere on the PC (Desktop is fine)
2. **Double-click to run** — a setup window will appear
3. **Enter your Gmail address** and App Password ([get one here](https://myaccount.google.com/apppasswords))
4. Click **Test Connection** to verify it works
5. Click **Save & Start Monitoring** — the app minimizes to the system tray
6. Done — it runs silently in the background forever

The Cha-Ching Payment Notifications icon appears in the taskbar tray (bottom-right corner):
- **Green bell** = listening, ready
- **Yellow bell** = reconnecting (brief)
- **Gray bell** = stopped

Right-click the tray icon to access **Settings**, **Payment History**, **Test Announcement**, **Check for Updates**, or **Exit**.

When an update is available, click **Update now**. Cha-Ching verifies the release checksum, keeps a backup of the current EXE, installs the update, and restarts itself.

### Payment history

- History is encrypted for the current Windows user.
- Search by payer, notification email, amount, or date.
- Use Previous and Next to move through 100-record pages.
- After upgrading from an older release, open Payment History and click **Rebuild history** once to remove old false-positive bank notifications.

---

## Auto-Start on Boot (optional)

So it starts automatically when the PC logs in:

1. Press `Win + R` → type `shell:startup` → press Enter
2. Create a shortcut to `ChaChing.exe` in that folder
3. Done — it will start every time Windows boots

---

## Gmail One-Time Setup (~5 min)

### 1. Enable IMAP
- Gmail → Settings gear → See all settings → **Forwarding and POP/IMAP**
- Under "IMAP access" → **Enable IMAP** → Save Changes

### 2. Enable 2-Step Verification (required)
- [myaccount.google.com](https://myaccount.google.com) → Security → 2-Step Verification → Turn On

### 3. Create an App Password
- [myaccount.google.com](https://myaccount.google.com) → Security → **App passwords**
- App: **Mail** → Device: **Windows Computer** → **Generate**
- Copy the 16-character code — paste it into Cha-Ching Payment Notifications

---

## Building the EXE (developers only)

Requires Python 3.11+ on a Windows machine.

```
pip install -r requirements.txt
build.bat
```

Output:

- `dist\ChaChing.exe`
- `dist\ChaChing.exe.sha256`

To make one-click updates available, create a GitHub release whose tag matches `APP_VERSION` in `version.py`, then upload both output files plus `install-chaching.ps1` and `install.bat`. Do not publish the EXE without its matching checksum.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| "Test Connection" fails | Wrong email or App Password, or IMAP not enabled in Gmail |
| No sound plays | Check Windows volume / audio output is connected |
| Wrong name announced | Share a redacted Zelle email subject/body sample to tune the parser |
| Doesn't auto-start | Add a shortcut to `shell:startup` folder |
| Tray icon is yellow | Reconnecting — wait a few seconds, it auto-recovers |
| Update is not offered | Confirm the latest GitHub release has both `ChaChing.exe` and `ChaChing.exe.sha256` |
