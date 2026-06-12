#!/usr/bin/env python3
"""Serve the static frontend with precompressed asset support."""

from __future__ import annotations

import argparse
import functools
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = REPO_ROOT / "src" / "frontend"


class CompressedStaticHandler(SimpleHTTPRequestHandler):
    def send_head(self):
        raw_path = self.translate_path(self.path)
        if os.path.isfile(raw_path):
            accepted = self.headers.get("Accept-Encoding", "")
            for encoding, suffix in (("br", ".br"), ("gzip", ".gz")):
                compressed_path = raw_path + suffix
                if encoding in accepted and os.path.isfile(compressed_path):
                    return self._send_compressed_file(
                        raw_path,
                        compressed_path,
                        encoding,
                    )

        return super().send_head()

    def _send_compressed_file(self, raw_path: str, compressed_path: str, encoding: str):
        try:
            response_file = open(compressed_path, "rb")
        except OSError:
            self.send_error(404, "File not found")
            return None

        self.send_response(200)
        self.send_header("Content-Type", self.guess_type(raw_path))
        self.send_header("Content-Encoding", encoding)
        self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(os.fstat(response_file.fileno()).st_size))
        self.end_headers()
        return response_file


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--directory", type=Path, default=FRONTEND_ROOT)
    args = parser.parse_args()

    handler = functools.partial(
        CompressedStaticHandler,
        directory=str(args.directory),
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving {args.directory} on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
