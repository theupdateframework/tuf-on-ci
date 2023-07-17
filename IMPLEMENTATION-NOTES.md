# Notes for implementation

This document describes a goal: current functionality is not quite the same yet:
as an example, git pushes/pulls are not yet handled by the tool. Currently the 
functionality is also split into playground-signer and playground-delegate.

## Signer tool Commands

Most actions should require no arguments or even commands, apart from the
signing event name. The tool should offer the right thing based on context.
So the common invocation looks like:

`signer <signing-event-name>`

Planned actions:
  * accept invitation -- offered when user is in "role.invites" custom metadata
  * update targets -- offered when the targets/ dir does not match targets in metadata
  * sign changes -- offered when user is a signer and the sig is missing
  * initialize a repository -- offered when root.json does not exist yet (but see below)
  * Change delegation -- likely NOT offered automatically as there's no logical
    trigger for this

The "change delegation" action is the only one that needs to be manually triggerable and
potentially does require input from user: _role, signers/keys, threshold, expiry-period,
signing-period_.
  * Note that "initialize repository" is a special case of 4 X "change
    delegation" with some defaults
  * Plan is to accept input in challenge-response manner (although arguments
    could also be added):
    ```bash
    $ signer <signing-event-name> <role-name>
    Modifying <role-name>. Options:
      1. Change signers. Current signers are [@userA, @userB]. Threshold is 1.
      2. Change expiry. Current expiry in 365 days, with re-signing 30 days before
    Choose option: ...
    Please input list of new signers: ...
    Please input new threshold: ...
    New <role-name> signers are [@userA, @userB, @userC]. Threshold is 2.
    $ 
    ```

To achieve the "no arguments" goal, the tool will require context, such as:
* custom metadata (see below)
* tool configuration: These could be prompted for any time they're not found
  * CI username
  * HW signing implementation details like pkcs11lib
  * git repository details (e.g. remote names, see below)


## Describing metadata changes

Being able to describe metadata changes is quite core to the usability of both
the Github actions and the signer tool. Plan is something like this

```bash
$ signer <signing-event-name>
Your signature is requested for the following changes to <rolename>:
 * New target file file1.txt
 * New expiry period: 180 days, with re-signing 30 days before
This change has already been signed by: [@userA]

Sign? [y/N]: y
Please open a PR to <signing-event-name> with your changes: <url>
```

or

```bash
$ signer <signing-event-name>
You have been invited as a signer for <rolename>. To become a signer,
your public key and username have to be added to the repository.

Add public key? [y/N]: y
Please open a PR to <signing-event-name> with your changes: <url>
```


There are still some open questions here -- like how to allow reviewing the proposed
changes at your own pace, then coming back to sign (this is mostly an issue WRT
git-integration like doing a pull automatically). 

## Custom metadata 

Custom metadata and how it is used. All custom field names should be prefixed with "x-playground-" to
A) make it clear it's custom and B) make collisions unlikely.

* key.x-playground-keyowner
  * used by tool to know when to sign
  * used by repo to notify @username
* key.x-playground-online-uri
  * used by repo to sign with online key
* role.x-playground-expiry-period & role.x-playground-signing-period (for all online roles)
  * used by repo to decide when new timestamp/snapshot is needed and to decide the new expiry date
  * signing-period may not be needed -- maybe we can predict what is safe?
* signed.x-playground-expiry-period & signed.x-playground-signing-period (for all offline roles)
  * used by repo to decide when to start a signing event
  * used by tool to bump version

In addition to signed metadata, the following data is committed to git during the signing event (but is
not part of the actual signed repository):
* invitations 
  * set by signer tool
  * used by repo to notify invited usernames
  * used by signer tool to accept invitations

## GitHub Actions that should be provided

1. snapshot
  * if snapshot is needed, create one. If timestamp is needed, create one
  * Smoke test? -- make sure the repository is considered valid by clients
  * merge to main (or create PR, this could be configurable)
  * Failure to sign or merge should lead to a GitHub issue, with root signers
    getting notified
1. expiry-check
  * check each offline role
    * if signing-period for a role is reached, start a signing event (branch)
    * construct the version bump commit in the branch
      (alternatively, let signing tool create the version bump)
    * request signatures
  * check each online role
    * if signing-period for a role is reached, create new version and sign
      (if snapshot changed, also bump timestamp)
1. signing-event
   Uses repo software to define the state of the signing event.
   Possible signing event states include:
   * No actual changes (branch has been created, but no commits)
   * Changes to online roles (error)
   * Changes to offline roles, not accepted by repository (error)
     * metadata changes don't match target file changes
     * unexpected expiry date
     * unexpected delegation structure
     * etc, etc
   * Signer invitations waiting
   * Changes to offline roles, at least one roles threshold not reached
   * Thresholds reached
   Two possible results
   * Document current state with a comment in issue in TUF repository
   * If thresholds have been reached, also create a PR in TUF repository
1. publish
   * use repo software to create a repository version
   * can we audit log this somehow -- this is the relevant event for the public repository 
   * make the repository files a result of this action, and leave the upload
     to the calling workflow

## CI events that trigger actions / workflows defined in the repository template 

### signing-branch-changed

* This event means a signing-event branch in the repository has changed
* workflow calls external action "signing-event"

### main-changed

* this event triggers after every signing event
* workflow calls external action "snapshot":
* If "snapshot" changed anything, workflow calls external action "publish"
* take the results of "publish", push them to github pages

### cron

* this should run often enough so every expiry/signing period is followed
* workflow calls external action "expiry-check"
* this may result in:
  * new signing events for offline signed branches
  * new snapshot/timestamp if they are expiring: create new versions, and "publish"

### label-assigned

* This is a convenience to create a branch for external contributors
* if "sign/..." label is assigned to an issue, create a signing event branch of same name

## Undecided issues

### Automating git in signer tool

The big question is hiding git UX:
* hiding git details is not ideal: it should always be possible to not do that
  if the user so wishes
* on the other hand, most signer tool usage complexity is in git branch
  (signing event) management... Which can be simplified if the signing tool
  handles it

Potential automation design
* tool knows the remote names "origin" and "fork" (pull and push remotes, respectively): This requires either standardizing every maintainers setup or storing local configuration -- probably both make sense (standard setup just works, but config is available)
* given a signing event name (branch name), the tool can now handle pulls, pushes and crucially creating clickable links for PRs.
signer <signing-event>` -- this could do everything from pulling the branch, explaining changes and what is going to happen, asking for signature, creating a commit, pushing the branch, and creating a link to make a PR. This would all work for forks or maintainers working in-repo
* Required tool config
  ```
  username = @jku
  pkcs11lib = /usr/lib/x86_64-linux-gnu/libykcs11.so
  ```

### Repository configuration

A lot of the configuration can just be embedded in the metadata (see Custom
metadata section), but there are some unsolved issues:
* directory structure: it would be nice to allow e.g. the metadata directory to
  be anywhere in the git repository but that location would have to be
  understood by both signing tool and repository actions
* expiry periods: this data should and likely can be embedded but the online
  and offline roles operate a little differently and it's not yet 100% clear
  how this will work
* Plan is to start with fully automated online roles but it may be a good idea
  to support online roles that create PRs instead of merging directly. The
  configuration for this is not designed

### Repository safety

TUF workflow will protect clients from attackers who can manipulate the git
repository (but don't have access to the offline signing keys). However, being
able to modify repository state could give attackers
* the ability mislead signers into signing something they should not sign.
* the ability create an entirely new TUF repository (misleading new clients
  that happen to use a Trust-On-First-Use approach)

There are mitigations that should be explored: mostly these boil down to a
single rule: signing tool and repository should not trust content from each
other.
