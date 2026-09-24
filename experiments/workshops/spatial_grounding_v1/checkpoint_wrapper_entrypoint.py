"""Owned E3/F3 HTTP entry point; resource allocation is the coordinator's job."""

from __future__ import annotations

import os
from pathlib import Path
import sys


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in {"E3", "F3"}:
        raise SystemExit("usage: checkpoint_wrapper_entrypoint E3|F3")
    # Set before native imports; missing local assets must never trigger downloads.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    from .checkpoint_backends import build_pinned_edge_backend, build_pinned_flux_backend
    from .producer import NanoEvidenceProducer, make_nano_http_server
    from .runtime import _required_env

    model = sys.argv[1]
    backend = {"E3": build_pinned_edge_backend, "F3": build_pinned_flux_backend}[model]()
    host = _required_env(f"SGW01_{model}_HOST")
    if host != "127.0.0.1":
        raise SystemExit("owned checkpoint wrapper requires 127.0.0.1")
    producer = NanoEvidenceProducer(
        backend, trace_path=Path(_required_env("SGW01_TRACE_SIDECAR")),
        future_dir=Path(_required_env("SGW01_FUTURE_DIR")),
        attestation_path=Path(_required_env("SGW01_SERVER_ATTESTATION")),
        expected_config=backend.resolved_config,
    )
    make_nano_http_server(producer, host=host, port=int(_required_env(f"SGW01_{model}_PORT"))).serve_forever()


if __name__ == "__main__":
    main()
