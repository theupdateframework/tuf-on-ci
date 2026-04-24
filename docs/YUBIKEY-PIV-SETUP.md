# YubiKey PIV Setup

This guide walks through using the YubiKey Manager CLI to configure PIV for TUF signing operations.

> [!IMPORTANT]
> This is a general setup guide for using YubiKey with TUF-on-CI. When provisioning YubiKeys for production TUF use, you may want to consider additional procedures around the procurement, distribution, and configuration of the devices. (e.g. serial number tracking, offline device configuration, YubiKey Manager CLI, hardware random number generators, etc.)

### Requirements

Download YubiKey Manager CLI (ykman)

```shell
pip install yubikey-manager
```

> [!TIP]
> Use https://www.yubico.com/genuine/ to confirm that your YubiKey device is genuine

### Update PIV PIN Defaults

A new YubiKey is configured with a default PIN, PUK (PIN unlock code), and Management Key.

The default PIN codes must be updated with new values that you remember or store securely.

PIN codes are used for signing operations and to unlock a device.

#### Reset PIV to Defaults

> [!CAUTION]
> Performing this operation will destroy all existing PIV data

```shell
ykman piv reset
```

All PIV data will be cleared from the YubiKey and PIN, PUK, and Management Key set to default.

#### Set PIN

```shell
ykman piv access change-pin --pin 123456
```

#### Set PUK (PIN unlock code)

The PUK PIN is used to unlock a device after a number of failed PIN entry attempts.

```shell
ykman piv access change-puk --puk 12345678
```

#### Set Management Key

The management key is used to perform many YubiKey management operations, such as generating a key pair.

```shell
ykman piv access change-management-key --algorithm aes256
```

To store the management key on the device protected by the PIN, add the `--protect` parameter.

```shell
ykman piv access change-management-key --algorithm aes256 --protect
```

### Generate Digital Signature Certificate

Generate a key in the signature slot (PIV slot 9c). The following generates a self-signed certificate.

```shell
ykman piv keys generate -a eccp256 9c pub.pem
ykman piv certificates generate 9c --subject subject-field-value pub.pem
```

It is recommended to use your GitHub handle as the `--subject` parameter value.

> [!NOTE]
> The tuf-on-ci-delegate sign/init command currently requires the key type to be eccp256.

After generating the digital signature certificate, continue the TUF-on-CI [signer setup process](SIGNER-SETUP.md).
