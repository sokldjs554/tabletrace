"""Generate the gRPC stubs from proto/ into src/tabletrace/service/pb/ (needs grpcio-tools).

  python scripts/gen_proto.py
The generated files are committed so that running the server does not need grpcio-tools.
"""
from __future__ import annotations

import sys
from pathlib import Path

from grpc_tools import protoc

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    proto = ROOT / "proto" / "tabletrace" / "service" / "pb" / "tabletrace.proto"
    return protoc.main(["protoc", f"-I{ROOT / 'proto'}", f"--python_out={ROOT / 'src'}", f"--grpc_python_out={ROOT / 'src'}", str(proto)])


if __name__ == "__main__":
    sys.exit(main())
