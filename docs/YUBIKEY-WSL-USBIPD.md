# How to use a YubiKey for `tuf-on-ci-sign` on Windows inside WSL (Ubuntu) via `usbipd`

This guide documents one working setup for using `tuf-on-ci-sign` with a YubiKey (CCID/PIV via PKCS#11) on **Windows** from **WSL2 Ubuntu**, using **usbipd on the Windows host** to pass the device through.

It also covers the common build dependency for `tuf-on-ci-sign` (`pykcs11`), and the **polkit permissions** required for `pcscd` access in WSL.

---

## Prerequisites

- Windows 10/11 with WSL2 enabled
- An Ubuntu distribution installed in WSL
- A YubiKey plugged into the Windows machine
- Admin access on Windows (for `usbipd` bind/attach)

---

## 1) Windows host: install and use `usbipd`

### 1.1 Install `usbipd`
[Download](https://github.com/dorssel/usbipd-win/releases) and install `usbipd` on the Windows host (for sharing USB devices with WSL).

A **restart of the Windows host** may be required after installation.

### 1.2 Find the YubiKey and bind it (PowerShell as Administrator)

1. Open **PowerShell as Administrator**
2. List USB devices before and after inserting the YubiKey to identify the correct device:

```powershell
usbipd.exe list
```

3. Once you know the BUSID (format like `X-X`), bind it:

```powershell
usbipd.exe bind --busid X-X
```

> Tip: the YubiKey may show up as a composite device (HID + CCID). Binding the correct device entry is crucial.

### 1.3 Attach the device to WSL

```powershell
usbipd.exe attach --wsl --busid X-X
```

---

## 2) WSL Ubuntu: install required packages

### 2.1 Python tooling (pip + venv)

```bash
sudo apt update
sudo apt install -y python3-pip python3-venv
```

### 2.2 Build tooling + YubiKey tooling

`pip install tuf-on-ci-sign` may compile dependencies (notably `pykcs11`), so install the matching compiler versions (example: GCC 12), plus USB/YubiKey tooling.

```bash
sudo apt install -y gcc-12 g++-12 usbutils yubikey-manager yubico-piv-tool opensc pcscd libccid pcsc-tools
```

Optional: if available in your repo, you can also install Yubico’s PKCS#11 module package (naming differs by distro). On Ubuntu/Debian you often get the module via `yubico-piv-tool` and the library is available at:

- `/usr/lib/x86_64-linux-gnu/libykcs11.so`

---

## 3) WSL Ubuntu: verify the YubiKey is visible

After attaching via `usbipd`, confirm the YubiKey is present:

```bash
lsusb
lsusb -t
```

You should see a Yubico device and typically a CCID/SmartCard interface.

---

## 4) WSL Ubuntu: set up a Python venv and install `tuf-on-ci-sign`

### 4.1 Create the venv

```bash
python3 -m venv ~/python/tuf-on-ci-sign
```

### 4.2 Activate and install

```bash
source ~/python/tuf-on-ci-sign/bin/activate
pip install --upgrade pip
pip install tuf-on-ci-sign
```

---

## 5) WSL Ubuntu: automate venv activation and usbipd attach with `direnv`

### 5.1 Install `direnv`

```bash
sudo apt install -y direnv
```

Follow your shell’s integration instructions (bash/zsh) and restart your shell.

### 5.2 Create `.envrc` in your signing repository

In the git repo where you run signing commands, create `.envrc`:

```bash
source ~/python/tuf-on-ci-sign/bin/activate
usbipd.exe attach --wsl --busid X-X
```

Then allow it:

```bash
direnv allow
```

> Note: calling `usbipd.exe` from WSL works if Windows executables are on your WSL PATH (common default).

---

## 6) WSL Ubuntu: fix HID permissions (udev rule)

If you need access to HID interfaces (often needed by some `ykman` operations), add a udev rule.

Create the file:

```bash
sudo vim /etc/udev/rules.d/99-yubikey.rules
```

Example rule:

```udev
KERNEL=="hidraw*", SUBSYSTEM=="hidraw", MODE="0666", TAG+="uaccess", GROUP="plugdev", ATTRS{idVendor}=="xxxx", ATTRS{idProduct}=="xxxx"
```

- Replace `xxxx` with the vendor/product IDs.
- You can get those IDs from `usbipd.exe list` (Windows) or `lsusb` (WSL).
  - Yubico vendor ID is commonly `1050` (check your output).

Reload rules (best-effort under WSL; may require WSL restart):

```bash
sudo udevadm control --reload-rules || true
sudo udevadm trigger || true
```

---

## 7) WSL Ubuntu: allow smartcard access via polkit (pcscd)

To let user-space tools access the PC/SC daemon (`pcscd`), add a polkit rule.

Create:

```bash
sudo vim /etc/polkit-1/rules.d/99-pcscd.rules
```

Rule content:

```javascript
polkit.addRule(function(action, subject) {
  if ((action.id == "org.debian.pcsc-lite.access_pcsc" ||
       action.id == "org.debian.pcsc-lite.access_card") &&
      subject.user == "YOUR_USERNAME") {
    return polkit.Result.YES;
  }
});
```

- Replace `YOUR_USERNAME` with your actual username (for example: `john`).
- Do **not** use `$USER` literally here; polkit rules are JavaScript evaluated by polkit, not your shell.

Restart services:

```bash
sudo systemctl restart polkit
sudo systemctl restart pcscd
```

---

## 8) Validate smartcard + YubiKey access in WSL

### 8.1 PC/SC sees the card

```bash
pcsc_scan
```

You should see the YubiKey reader and an ATR when inserted.

### 8.2 Verify `ykman` access

```bash
ykman info
ykman piv info
```

### 8.3 Verify PKCS#11 sees the YubiKey

Yubico’s PKCS#11 module:

```bash
pkcs11-tool --module /usr/lib/x86_64-linux-gnu/libykcs11.so -L
pkcs11-tool --module /usr/lib/x86_64-linux-gnu/libykcs11.so -O
```

If you see a slot but it appears “empty”, you may need to initialize/populate PIV slots with keys/certificates (depends on your signing workflow).

---

## 9) Use `tuf-on-ci-sign`

With the YubiKey attached, venv enabled, and polkit permissions correct:

```bash
tuf-on-ci-sign sign/add-root-users
```

Choose `Yubikey` when prompted.

---

## Troubleshooting notes

- If you see `pcscd` logs like “Communication protocol mismatch”, ensure you use **apt-installed** tooling in WSL (avoid mixing snap/brew/conda builds of `ykman`/pcsc-lite).
- If `pcsc_scan` works but `tuf-on-ci-sign` reports no tokens, confirm that `pkcs11-tool ... -L/-O` shows a token and objects.
- If permissions regress, restart WSL, then re-run `usbipd.exe attach --wsl --busid X-X`.

---
