# Migration: volsurface → volfoundry

The pre-release package `volsurface` (v0.0.1) has been renamed to **VolFoundry**
as part of the production-quality open-source release.

## What changed

| Before | After |
|--------|-------|
| `volsurface` | `volfoundry` |
| `from volsurface.data.fetcher import DeribitPublicClient` | `from volfoundry.data.fetcher import DeribitPublicClient` |
| Package layout: `volsurface/` | Package layout: `src/volfoundry/` |

## Why no compatibility shim

VolFoundry is pre-1.0. The old import path `volsurface` is not preserved because
it conflicts with the intended production brand and could collide with unrelated
packages. The clean rename avoids confusion for new users.

## How to migrate

A global find-and-replace is sufficient:

```bash
# Replace all imports in your code:
sed -i 's/from volsurface\./from volfoundry./g' *.py
sed -i 's/import volsurface\./import volfoundry./g' *.py
```

The subpackage structure, function names, and APIs are unchanged — only the
top-level package name differs.

## Timeline

- `volsurface` v0.0.1: pre-release research prototype (no longer maintained).
- `volfoundry` v0.1.0: first production-quality release.
