# TUF-on-CI Signer Manual

The purpose of A TUF-on-CI repository is to secure artifact delivery to
downloaders. This is accomplished by _signers_ digitally signing TUF metadata using
the `tuf-on-ci-sign` tool.

This page documents `tuf-on-ci-sign` usage.

:exclamation: For installation and configuration, see [SIGNER-SETUP.md](SIGNER-SETUP.md)

### Terms

_Signer_: A person who has agreed to verify the integrity of artifact hashes and other
metadata of a _role_ by signing that role's metadata with their personal signing method
(e.g. a Yubikey).

_Signing event_: Collaboration of one or more signers to produce and sign a new version of
a role's metadata. A signing event happens in a GitHub pull request. Signing event names
start with "sign/".

_Role_: A role manages a set of artifacts and (optionally) a set of delegations to other
roles. A role has a set of _signers_ (defined by the delegating role): their signatures
are needed when the role is changed.
The default delegation structure includes only a `root` role and a `targets`
role (delegated by root). The targets role can further delegate to other roles.

## Usage

Metadata is signed in a _signing event_. The signing event process is:
* A signing event pull request gets created by the repository. This happens as a
  response to either a timed event (like an expiry date approaching) or as a response to
  artifact changes. Either way, the signing event contains new metadata versions that
  need to be signed before they are considered valid.
* The signing event directs _signers_ to sign the changes using `tuf-on-ci-sign`. By
  signing they confirm that the proposed changes are correct. The local signing tool
  makes a commit with the signature pushes the commit to the remote signing event branch.
  * If a signer does not have push permissions for the GitHub repository, their signature
    is added to the signing event via PR from their fork to the signing event branch.
* Finally, a Pull Request to merge the signing event into main is created.

Throughout the process, the repository updates the signing event pull request with status
reports. These reports in the signing event pull request function as a notification
mechanism but *signers should only ever fully trust their local signing tool*.

The signing tool works in the repository (git clone) directory -- note that
fetching, pushing or switching branches is not necessary: the tool will always use an
up-to-date signing event branch and when the signer decides to sign, the signature is
automatically pushed to the signing event branch.

### Accepting an invitation

When a signing event pull request invites to become a signer:
```shell
$ tuf-on-ci-sign <event>
```
* The tool prompts to select a signing method and prompts to push the public key
  and signature to the repository
* If push and pull remotes are different in signer configuration, signer creates a
  Pull Request _from their fork to the signing event branch_.

### Signing a change

When a signing event pull request instructs to sign a change:
```shell
$ tuf-on-ci-sign <event>
```
* The tool describes the changes, prompts to sign and prompts to push the signature to
  the repository
* If push and pull remotes are different in signer configuration, signer creates a
  Pull Request _from their fork to the signing event branch_.


### Modifying artifacts

Artifacts are stored in git (in the `targets/` directory) and are modified using normal
git tools: the signing tool is not used. Artifact modification commits should get pushed to a
branch on the repository (with a branch name starting with "sign/"): this creates a signing
event for the artifact change allowing signers to sign that change.

The role where the artifact belongs to is chosen with pathname:
* files in the targets directory are artifacts managed by top level role "targets"
    * NB: only files in the top level `targets` directory are owned by the "targets" role
      (so `targets/somefile` is owned by "targets", but `targets/somedir/otherfile` is not)
* files in a subdirectory are artifacts of the role with the same name (so
  `targets/A/file.txt` is an artifact managed by role "A")
    * NB: Four levels of directories are supported below each role directory
     (so `targets/A/dir1/dir2/dir3/dir4/file.txt`) is owned by "A", but
     `targets/A/dir1/dir2/dir3/dir4/dir5/file.txt` is not

<details>
  <summary>Example</summary>

  Artifact changes are committed into a signing event branch using git:
  ```shell
  # Add a new artifact managed by top level role targets
  $ git fetch && git switch -c sign/add-a-target origin/main
  $ echo "artifact" > targets/file1.txtv
  $ git add targets/file1.txt
  $ git commit -m "New artifact file1.txt, managed by targets"

  # Pushing the branch starts a signing event: Repository will create a new metadata
  # version for the role and signers can then review and sign that version.
  $ git push origin sign/add-a-target
  ```

  After the signing event is created, signers can follow instructions to sign the changes.
</details>
