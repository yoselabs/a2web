"""Browser-backend plugin manifests — one file per rendering engine.

Each module declares `MANIFEST = PluginManifest(...)` with a `BrowserBackend`
factory. `select_backend` (state.py) discovers them via `load_surface`.
"""
