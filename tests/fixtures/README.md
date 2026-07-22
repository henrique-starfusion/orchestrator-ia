# Test Fixtures

This directory documents fixture conventions for the orchestrator test suite.

**All tests use temporary project directories only.** Each test creates an isolated workspace under:

```
$env:TEMP\orchestrator-tests-<guid>
```

Nothing in this folder is copied directly into real project paths. The real package root (local clone of `orchestrator-ia`) is referenced only via `-PackageRoot` when invoking installer scripts.

Fixtures for legacy migration and similar scenarios are created programmatically inside each test's temporary directory and removed in `finally` blocks after the test completes.
