## Release process

1. Ensure `docs/CHANGELOG.md` contains a summary of notable changes since the
   prior release. Check that all required changes to workflows that
   call our actions are clearly documented.
2. Update version number in `signer/pyproject.toml` and `repo/pyproject.toml`
3. Create a PR with the updated CHANGELOG and version bumps.
4. Once the PR is merged, create a signed tag for the version number on the merge commit
  `git tag --sign vA.B.C -m "vA.B.C"`
6. Push the tag to GitHub `git push origin vA.B.C`. This triggers release workflow
7. [Review deployment](https://docs.github.com/en/actions/managing-workflow-runs/reviewing-deployments)
on GitHub. On approval both the PyPI signer release and the GitHub release will be deployed