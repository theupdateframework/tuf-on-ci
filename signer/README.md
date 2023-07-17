### Requirements

In addition to the Python requirements managed by pip, a PKCS#11 module is
required (and it's location needs to be configured, see below).

This tool has been tested with the Yubico implementation of PKCS#11, 
[YKCS11](https://developers.yubico.com/yubico-piv-tool/YKCS11/). Debian users
can install it with `apt install ykcs11`.

### Installation

Development install: `pip install -e .`

### Configuration

Tool does not currently write the config file itself so this needs to be done manually.

`.playground-sign.ini` (in the git toplevel directory):
```
[settings]
pykcs11lib = /usr/lib/x86_64-linux-gnu/libykcs11.so
user-name = @jku
```

### Usage

When a signing event (GitHub issue) requests your signature, run `playground-sign`.

### TODO

* implement role-metadata cache -- currently we load the same file quite a lot
* avoid asking for pin too many times
  1. same role is sometimes signed multiple times -- could avoid all but last one
  2. multiple roles may be signed -- this is likely not worth optimizing 
* refactor event state handling (invites): it's currently clumsy in _signer_repository.py
* git integration. Would be nice to be able to avoid
  * git fetch
  * git checkout <signing-event>
  * git push <remote> <signing-event>
  * _figure out how to create a PR to the signing-event
  We can do all this if we store pull-remote and push-remote information in the configuration