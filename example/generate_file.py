#!/usr/bin/env python3
"""
Utility script to generate a large text file for testing.

Default: writes a ~200 MB text file to example/input/big_200mb.txt

Usage examples:
  - Default 200 MB file:
      python example/generate_file.py

  - Custom size (e.g., 50 MB):
      python example/generate_file.py --size-mb 50

  - Custom output path and line content:
      python example/generate_file.py --out example/input/myfile.txt --line "sample data"
"""

import argparse
import os
from pathlib import Path


def generate_text_file(output_path: Path, size_mb: int, line: str, chunk_size_bytes: int = 1024 * 1024) -> None:
    """Generate a text file approximately size_mb megabytes in size using chunked writes.

    Args:
        output_path: Destination file path.
        size_mb: Target size in megabytes.
        line: Single line of text to repeat. A trailing newline will be ensured.
        chunk_size_bytes: Number of bytes to write per chunk (default 1 MiB).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Ensure the line ends with a newline
    if not line.endswith("\n"):
        line = line + "\n"

    target_size_bytes = size_mb * 1024 * 1024

    # Build a chunk by repeating the line until it meets/exceeds chunk_size_bytes
    line_bytes = line.encode("utf-8")
    if len(line_bytes) == 0:
        line_bytes = b"\n"

    repetitions = max(1, chunk_size_bytes // len(line_bytes))
    chunk = line_bytes * repetitions

    # Adjust chunk to be at most chunk_size_bytes
    if len(chunk) > chunk_size_bytes:
        chunk = chunk[:chunk_size_bytes]

    written = 0
    with open(output_path, "wb") as f:
        while written + len(chunk) <= target_size_bytes:
            f.write(chunk)
            written += len(chunk)

        # Write the remainder to hit the target size as close as possible
        remainder = target_size_bytes - written
        if remainder > 0:
            # Use a slice of the chunk to fill the remainder
            f.write(chunk[:remainder])
            written += remainder

    # Optionally ensure exact size (already precise above), but double-check with filesystem
    actual_size = output_path.stat().st_size
    if actual_size != target_size_bytes:
        # Truncate or expand with newlines to match exactly (rare edge cases)
        with open(output_path, "ab") as f:
            if actual_size > target_size_bytes:
                # Truncate by reopening with r+b and truncating
                with open(output_path, "r+b") as tf:
                    tf.truncate(target_size_bytes)
            elif actual_size < target_size_bytes:
                f.write(b"\n" * (target_size_bytes - actual_size))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a large text file for testing.")
    parser.add_argument(
        "--size-mb",
        type=int,
        default=200,
        help="Target file size in megabytes (default: 200)",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=str(Path(__file__).resolve().parent / "input" / "big_200mb.txt"),
        help="Output file path (default: example/input/big_200mb.txt)",
    )
    parser.add_argument(
        "--line",
        type=str,
        default="This is a sample line for generating a large text file.",
        help="Line content to repeat in the file.",
    )
    parser.add_argument(
        "--chunk-size-bytes",
        type=int,
        default=1024 * 1024,
        help="Chunk size for buffered writes in bytes (default: 1048576)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = Path(args.out)
    generate_text_file(output_path=output_path, size_mb=args.size_mb, line=args.line, chunk_size_bytes=args.chunk_size_bytes)
    print(f"Generated file: {output_path} ({args.size_mb} MB)")


if __name__ == "__main__":
    main()
