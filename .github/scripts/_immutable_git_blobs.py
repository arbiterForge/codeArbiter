"""Bounded, transaction-local immutable Git blob transport for readiness.

Only positive bytes are cached. No proof, authentication, absence or readiness
decision lives here. A single worker owns both pipes; its caller bounds every
exchange and contains the child if any pipe or process stops responding.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path, PurePosixPath
import queue
import re
import subprocess
import threading
import time

from _boundedproc import start, terminate_tree
from _gitexec import git_executable, root_bound_git_env

MAX_BLOB = 16 * 1024 * 1024
MAX_TOTAL = 256 * 1024 * 1024
MAX_QUERIES = 16384
QUERY_SECONDS = 10
TRANSACTION_SECONDS = 120
_active = ContextVar('readiness_immutable_blob_transaction', default=None)


class BlobReadError(ValueError):
    pass


def _query(source, path):
    if (not isinstance(source, str) or not re.fullmatch(r'(?!0{40}$)[0-9a-f]{40}', source)
            or not isinstance(path, str)):
        raise BlobReadError('exact immutable source and literal path required')
    pure = PurePosixPath(path)
    if (not path or str(pure) != path or pure.is_absolute() or '..' in pure.parts
            or path == '.' or ':' in path or '\\' in path
            or any(ord(c) < 32 or ord(c) == 127 for c in path)):
        raise BlobReadError('invalid literal immutable blob path')
    try:
        encoded = path.encode('utf-8', 'strict')
    except UnicodeError:
        raise BlobReadError('invalid literal immutable blob path') from None
    if len(encoded) > 4096:
        raise BlobReadError('immutable blob path exceeds bound')
    return source.encode('ascii') + b':' + encoded


def _exact(stream, count):
    chunks = []
    while count:
        value = stream.read(min(count, 1024 * 1024))
        if not value:
            raise BlobReadError('truncated immutable blob payload')
        chunks.append(value)
        count -= len(value)
    return b''.join(chunks)


class Reader:
    def __init__(self, repo):
        self.repo = Path(repo).resolve()
        self.cache = {}
        self.total = self.queries = 0
        self.deadline = time.monotonic() + TRANSACTION_SECONDS
        self.process = self.worker = None
        self.requests = queue.Queue(maxsize=1)
        self.results = queue.Queue(maxsize=1)
        self.closed = False
        self.lock = threading.Lock()

    def _start(self):
        env = root_bound_git_env()
        env.update(GIT_NO_REPLACE_OBJECTS='1', GIT_NO_LAZY_FETCH='1', GIT_TERMINAL_PROMPT='0')
        self.process = start([git_executable(), '--no-replace-objects', '--no-lazy-fetch',
                              '-C', str(self.repo), 'cat-file', '--batch'],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, env=env)
        self.worker = threading.Thread(target=self._io, name='immutable-git-blobs', daemon=True)
        self.worker.start()

    def _io(self):
        process = self.process
        def publish(success, value):
            # A timed-out caller may have abandoned its result while this
            # worker unwinds. Never block cleanup on an unconsumed response.
            try:
                self.results.put_nowait((success, value))
            except queue.Full:
                pass
        try:
            while True:
                query = self.requests.get()
                if query is None:
                    process.stdin.close()
                    if process.stdout.read(1):
                        raise BlobReadError('unexpected immutable blob trailing output')
                    if process.wait() != 0:
                        raise BlobReadError('immutable blob reader failed')
                    publish(True, None)
                    return
                process.stdin.write(query + b'\n')
                process.stdin.flush()
                header = process.stdout.readline(4352)
                if header == query + b' missing\n':
                    # Successful protocol response, not an absence assertion or
                    # a cache entry. Other current inputs may still be read.
                    publish(False, BlobReadError('immutable blob unavailable'))
                    continue
                match = re.fullmatch(rb'([0-9a-f]{40}|[0-9a-f]{64}) blob (0|[1-9][0-9]*)\n', header)
                if match is None:
                    raise BlobReadError('malformed immutable blob header or object type')
                size = int(match[2])
                if size > MAX_BLOB or self.total + size > MAX_TOTAL:
                    raise BlobReadError('immutable blob byte bound exceeded')
                value = _exact(process.stdout, size)
                if process.stdout.read(1) != b'\n':
                    raise BlobReadError('malformed immutable blob framing')
                self.total += size
                publish(True, value)
        except (OSError, ValueError) as error:
            self.closed = True
            publish(False, BlobReadError(str(error)))
        finally:
            for stream in (process.stdin, process.stdout):
                try:
                    stream.close()
                except OSError:
                    pass

    def _exchange(self, query):
        remaining = min(QUERY_SECONDS, self.deadline - time.monotonic())
        if remaining <= 0:
            self._abort()
            raise BlobReadError('immutable blob transaction deadline exceeded')
        self.requests.put_nowait(query)
        try:
            success, value = self.results.get(timeout=remaining)
        except queue.Empty:
            containment = self._abort()
            raise BlobReadError('immutable blob read timed out; containment=' + containment) from None
        if not success:
            if self.closed:
                containment = self._abort()
                raise BlobReadError(str(value) + '; containment=' + containment) from None
            raise value
        return value

    def read(self, source, path):
        query = _query(source, path)  # Reject injection before even starting Git.
        with self.lock:
            if self.closed:
                raise BlobReadError('immutable blob transaction is closed')
            key = (source, path)
            if key in self.cache:
                return self.cache[key]
            if self.queries >= MAX_QUERIES:
                self._abort()
                raise BlobReadError('immutable blob query bound exceeded')
            self.queries += 1
            if self.process is None:
                self._start()
            value = self._exchange(query)
            self.cache[key] = value
            return value

    def _abort(self):
        self.closed = True
        try:
            self.requests.put_nowait(None)
        except queue.Full:
            pass
        containment = terminate_tree(self.process) if self.process is not None else 'exited'
        if self.worker is not None:
            self.worker.join(timeout=3)
        self.cache.clear()
        return containment

    def close(self):
        try:
            if not self.closed and self.process is not None:
                self._exchange(None)
        finally:
            if self.process is not None and self.process.poll() is None:
                self._abort()
            elif self.worker is not None:
                self.worker.join(timeout=3)
            self.closed = True
            self.cache.clear()


@contextmanager
def transaction(repo):
    repo = Path(repo).resolve()
    current = _active.get()
    if current is not None and current.repo == repo:
        yield current
        return
    reader = Reader(repo)
    token = _active.set(reader)
    primary = None
    try:
        yield reader
    except BaseException as error:
        primary = error
        raise
    finally:
        _active.reset(token)
        try:
            reader.close()
        except (BlobReadError, OSError):
            if primary is None:
                raise
            primary.add_note('Immutable Git reader cleanup also failed; original exception and cause preserved.')


def read(repo, source, path):
    with transaction(repo) as reader:
        return reader.read(source, path)
