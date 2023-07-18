## TUF-on-CI Downloader client example

TODO: There is currently no client code here.

A standard TUF client should work with one caveat: if the TUF-on-CI repository uses
sigstore signatures, these must be supported in the downloader client (and no tuf libraries
currently do that by default: python-tuf and securesystemslib can be configured to do so).

