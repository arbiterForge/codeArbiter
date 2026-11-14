"""Acquire the reviewed Linux-only builder for the bounded CI qualification."""
import argparse
from contextlib import ExitStack, contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import stat
import subprocess
import sys
import tarfile
import tempfile
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

VERSION = "1.41.0"
ARCHIVE_SIZE = 3717141
ARCHIVE_SHA256 = "0f55de7874507b9cf7502113120bd96f2ab6979f78d10eaf2eb2ade9207b3af6"
URL = "https://github.com/railwayapp/nixpacks/releases/download/v1.41.0/nixpacks-v1.41.0-x86_64-unknown-linux-musl.tar.gz"
MAX_BINARY = 16 * 1024 * 1024


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def verified_binary(raw):
    require(len(raw) == ARCHIVE_SIZE, "archive size mismatch")
    require(hashlib.sha256(raw).hexdigest() == ARCHIVE_SHA256, "archive digest mismatch")
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        member = archive.next()
        require(member is not None and member.name == "nixpacks" and member.isreg()
                and not member.issparse() and 64 <= member.size <= MAX_BINARY,
                "archive member is unsupported")
        stream = archive.extractfile(member)
        require(stream is not None, "archive member is unreadable")
        binary = stream.read(member.size + 1)
        require(len(binary) == member.size and archive.next() is None,
                "archive member population differs")
    require(binary[:7] == b"\x7fELF\x02\x01\x01"
            and int.from_bytes(binary[18:20], "little") == 62,
            "ELF must be Linux x86_64 little-endian 64-bit")
    return binary


def approved_url(url):
    parsed = urlsplit(url)
    require(parsed.scheme == "https" and parsed.hostname in
            {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}
            and parsed.port in (None, 443) and parsed.username is None and parsed.password is None,
            "download redirect is not approved HTTPS")


class Redirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, url):
        approved_url(url)
        return super().redirect_request(request, response, code, message, headers, url)


def download():
    approved_url(URL)
    # Public release: no ambient proxy or authorization header is forwarded.
    opener = build_opener(ProxyHandler({}), Redirect())
    with opener.open(URL, timeout=30) as response:
        approved_url(response.geturl())
        return response.read(ARCHIVE_SIZE + 1)


def process_environment():
    return {key: os.environ[key] for key in
            ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP") if key in os.environ}


def safe_directory(path):
    path = Path(path).absolute()
    require(not any(ord(c) < 32 for c in str(path)), "output path contains controls")
    for parent in (path, *path.parents):
        info = parent.lstat()
        require(stat.S_ISDIR(info.st_mode) and not parent.is_symlink()
                and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                "output directory has a link or non-directory ancestor")
    return path


def acquire(parent):
    require(platform.system() == "Linux" and platform.machine() in ("x86_64", "amd64"),
            "only the reviewed Linux amd64 profile is supported")
    parent = safe_directory(parent)
    binary = verified_binary(download())
    # New owned directory and exclusive leaf; archive extraction writes nothing.
    target = Path(tempfile.mkdtemp(prefix="ca-nixpacks-reviewed-", dir=parent))
    executable = target / "nixpacks"
    with executable.open("xb") as stream:
        stream.write(binary)
        stream.flush()
        os.fsync(stream.fileno())
    executable.chmod(0o755)
    observed = subprocess.run([str(executable), "--version"], env=process_environment(),
                              stdin=subprocess.DEVNULL, capture_output=True, timeout=10, check=True)
    require(observed.stdout.strip() == ("nixpacks " + VERSION).encode(), "builder version differs")
    return {"format": "codearbiter.nixpacks-acquisition/1", "version": VERSION,
            "scope": "Linux amd64; fixed plan generation only; no image or workflow qualification",
            "archive_sha256": ARCHIVE_SHA256, "binary_sha256": hashlib.sha256(binary).hexdigest(),
            "bin_dir": str(target)}


def regular_command_file(info):
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
            and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
            "GitHub path file is linked or not regular")


@contextmanager
def command_file(path):
    path = Path(path).absolute()
    safe_directory(path.parent)
    before = path.lstat()
    regular_command_file(before)
    descriptor = os.open(path, os.O_RDWR | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        regular_command_file(opened)
        require((before.st_dev, before.st_ino) == (opened.st_dev, opened.st_ino),
                "GitHub path file identity changed")
        yield descriptor, path
    finally:
        os.close(descriptor)


def append_path(command, directory):
    descriptor, path = command
    safe_directory(path.parent)
    current, observed = os.fstat(descriptor), path.lstat()
    regular_command_file(current)
    regular_command_file(observed)
    require((current.st_dev, current.st_ino) == (observed.st_dev, observed.st_ino),
            "GitHub path file identity changed")
    end = os.lseek(descriptor, 0, os.SEEK_END)
    separator = b""
    if end:
        os.lseek(descriptor, -1, os.SEEK_END)
        separator = b"" if os.read(descriptor, 1) == b"\n" else b"\n"
    line = separator + (directory + "\n").encode("utf-8")
    require(os.write(descriptor, line) == len(line), "GitHub path append was incomplete")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", default=os.environ.get("RUNNER_TEMP"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--github-path", action="store_true")
    args = parser.parse_args()
    try:
        require(args.parent, "runner temporary directory is required")
        parent = safe_directory(args.parent)
        output = Path(args.output).absolute()
        require(output.parent == parent and not output.exists() and not output.is_symlink(),
                "a new receipt in the runner temporary directory is required")
        with ExitStack() as stack:
            command = stack.enter_context(command_file(os.environ["GITHUB_PATH"])) if args.github_path else None
            record = acquire(parent)
            with output.open("x", encoding="utf-8") as stream:
                json.dump(record, stream, indent=2)
                stream.write("\n")
            if command is not None:
                append_path(command, record["bin_dir"])
        print("Reviewed Nixpacks " + VERSION + " acquired for the bounded Linux profile")
        return 0
    except (OSError, ValueError, KeyError, URLError, tarfile.TarError, subprocess.SubprocessError) as error:
        reason = str(error) if isinstance(error, ValueError) else type(error).__name__
        print("Nixpacks acquisition refused: " + reason, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
