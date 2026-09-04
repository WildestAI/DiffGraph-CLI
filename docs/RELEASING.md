# Releasing native DiffGraph CLI binaries

Pushing a tag beginning with `v` (for example, `v1.1.0`) starts the **Release
native binaries** GitHub Actions workflow. The workflow is intentionally tag
only; a pull request or branch push cannot publish a release.

## What the workflow produces

Each target is built on a runner of the same operating system and CPU
architecture, then runs its own `wild --help` smoke test:

- `wild-linux-x64`
- `wild-linux-arm64`
- `wild-macos-x64`
- `wild-macos-arm64`
- `wild-windows-x64.exe`

The publish job downloads those five artifacts and fails before creating a
release unless every expected file is present and there are exactly five
binaries. It writes `checksums.txt` with SHA-256 checksums and uploads it with
the binaries to the GitHub release.

## Credential safety

`build.py` creates a one-file PyInstaller binary without `--add-data` or
`--add-binary`. It rejects a workspace containing any `.env` file before
PyInstaller runs. This replaces the legacy behavior that generated a spec file
and edited it to bundle `.env`. A binary may still read a user-provided `.env`
next to the executable at runtime; that file is never embedded in a release.
Use environment variables in CI and for releases.

## Runner availability

The ARM jobs require GitHub-hosted ARM labels (`ubuntu-24.04-arm` and
`macos-14`); the Intel macOS job uses `macos-13`. Availability and billing for
these labels depend on the repository visibility and the GitHub plan. If a
label is unavailable, the workflow fails at scheduling rather than silently
cross-compiling an incorrect binary. Update the matrix only after confirming an
alternative runner is native for the target architecture.

## Local Linux check

On Linux, the equivalent build and smoke test are:

```bash
python -m pip install -r requirements.txt
python build.py --output-dir release --name wild
./release/wild --help
```

Do not leave a `.env` in the checkout when invoking `build.py`; it fails closed
by design.
