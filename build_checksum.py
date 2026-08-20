import hashlib
import sys
from pathlib import Path


def write_checksum(executable_path, checksum_path):
    executable = Path(executable_path)
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    Path(checksum_path).write_text(
        f"{digest}  {executable.name}",
        encoding="ascii",
    )


if __name__ == "__main__":
    write_checksum(sys.argv[1], sys.argv[2])
