# TUF-on-CI Signer Installation and Configuration

### Requirements

`tuf-on-ci-sign` can be used to sign with either a hardware key with PIV support (e.g.
a Yubikey) or a Sigstore identity.

#### Hardware signing requirements

A hardware signing key must contain a _PIV Digital Signature private key_ to be used with TUF-on-CI.
TUF-on-CI also needs access to a PKCS#11 module.

1. Generate a PIV signing key on your hardware key if you don't have one yet. For
   Yubikey owners the easiest tool is Yubikey manager:
   ![Yubikey manager UI](yubikey-manager.png)

1. Install a PKCS#11 module. TUF-on-CI has been tested with the Yubicos ykcs11. Debian users can install it with
   ```shell
   $ apt install ykcs11
   ```
   macOS users can install with
   ```shell
   $ brew install yubico-piv-tool
   ```

#### Sigstore signing requirements

:warning: Sigstore signing is an experimental feature and may not be compatible with all TUF client implementations.

To use Sigstore as a signing method, you will need an account in one of the compatible
identity providers (GitHub, Google or Microsoft).

### Signing tool installation

As of 0.0.1 releases are not yet available on PyPI.

Installation from git:
```shell
pip install git+https://git@github.com/theupdateframework/tuf-on-ci#subdirectory=signer
```

### Local configuration

1. `git clone` the repository you are a signer for
1. If you are not a GitHub maintainer of the repository, fork the repository on GitHub
   and add your fork as a remote in your local git clone
1. Create a local configuration file `.tuf-on-ci-sign.ini` in the repository directory:

  ```
  [settings]
  # Path to PKCS#11 module
  pykcs11lib = /usr/lib/x86_64-linux-gnu/libykcs11.so

  # GitHub username
  user-name = @my-github-username

  # pull-remote: the git remote name of the TUF repository
  pull-remote = origin

  # push-remote: If you are allowed to push to the TUF repository, you can use the same value
  # as pull-remote. Otherwise use the rmeote name of your fork 
  push-remote = origin
  ```