"""Tests for _updatelib — the update-available notifier's shared logic (spec:
.codearbiter/specs/update-available-notifier.md, AC-1..AC-6).

Covers: semver-tuple comparison (AC-6), the once-daily cache read/write and
is_stale gate (AC-4), the fail-silent HTTPS-only fetch (AC-5), the composed
refresh_if_stale best-effort refresh (AC-3/AC-4/AC-5), and the notice-line
render helper consumed by both SessionStart and the statusline (AC-1/AC-2).

Stdlib unittest only; no real network call is ever made — fetches are always
driven through an injected fake `opener` (see _FakeOpener/_FakeResp below), the
same seam fetch_latest_tag exposes in production for the hardened opener.
"""
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from unittest import mock

_HOOKS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

import _updatelib as U
from _helpers import redirect_home, restore_home


class _FakeUpdateHost:
    def __init__(self, target="ca", prefix="v", command="update ca"):
        self.update_target = target
        self.update_tag_prefix = prefix
        self.update_command = command


# =========================================================================== version parsing / compare (AC-6)
class TestParseVersion(unittest.TestCase):

    def test_simple_version(self):
        self.assertEqual(U.parse_version("2.9.0"), (2, 9, 0))

    def test_leading_v_tolerated(self):
        self.assertEqual(U.parse_version("v2.10.0"), (2, 10, 0))

    def test_build_metadata_ignored(self):
        self.assertEqual(U.parse_version("2.10.0+build.5"), (2, 10, 0))

    def test_prerelease_suffix_ignored(self):
        self.assertEqual(U.parse_version("2.10.0-rc1"), (2, 10, 0))

    def test_malformed_returns_none(self):
        self.assertIsNone(U.parse_version("not-a-version"))

    def test_empty_string_returns_none(self):
        self.assertIsNone(U.parse_version(""))

    def test_none_input_returns_none(self):
        self.assertIsNone(U.parse_version(None))

    def test_non_string_returns_none(self):
        self.assertIsNone(U.parse_version(2.9))


class TestVersionGt(unittest.TestCase):
    """AC-6: numeric-tuple comparison so 2.10.0 > 2.9.0 (NOT lexicographic)."""

    def test_minor_version_ten_beats_nine(self):
        self.assertTrue(U.version_gt("2.10.0", "2.9.0"))

    def test_lexicographic_trap_does_not_fire(self):
        # A naive string compare would say "2.9.0" > "2.10.0" ('9' > '1').
        self.assertFalse(U.version_gt("2.9.0", "2.10.0"))

    def test_equal_versions_not_greater(self):
        self.assertFalse(U.version_gt("2.9.0", "2.9.0"))

    def test_lesser_version_not_greater(self):
        self.assertFalse(U.version_gt("2.8.0", "2.9.0"))

    def test_malformed_candidate_yields_no_notice(self):
        self.assertFalse(U.version_gt("not-a-version", "2.9.0"))

    def test_malformed_installed_yields_no_notice(self):
        self.assertFalse(U.version_gt("2.10.0", "not-a-version"))

    def test_uneven_segment_counts_padded(self):
        self.assertTrue(U.version_gt("2.10", "2.9.9"))


class TestUpdateAvailable(unittest.TestCase):

    def test_true_when_latest_greater(self):
        self.assertTrue(U.update_available("2.9.0", "2.10.0"))

    def test_false_when_equal(self):
        self.assertFalse(U.update_available("2.9.0", "2.9.0"))

    def test_false_when_latest_lesser(self):
        self.assertFalse(U.update_available("2.9.0", "2.8.0"))


# =========================================================================== notice_line (AC-1 / AC-2)
class TestNoticeLine(unittest.TestCase):

    def test_ac1_greater_latest_yields_single_line_with_arrow(self):
        line = U.notice_line("2.8.2", "2.10.0")
        self.assertIsNotNone(line)
        self.assertNotIn("\n", line)
        self.assertIn("2.8.2", line)
        self.assertIn("2.10.0", line)
        self.assertIn("update available", line)
        self.assertIn("/plugin marketplace update codearbiter", line)

    def test_ac2_equal_versions_no_notice(self):
        self.assertIsNone(U.notice_line("2.9.0", "2.9.0"))

    def test_ac2_lesser_latest_no_notice(self):
        self.assertIsNone(U.notice_line("2.9.0", "2.8.0"))

    def test_missing_latest_no_notice(self):
        self.assertIsNone(U.notice_line("2.9.0", None))

    def test_malformed_latest_no_notice(self):
        self.assertIsNone(U.notice_line("2.9.0", "garbage"))

    def test_notice_uses_the_active_hosts_native_update_command(self):
        hosts = (
            _FakeUpdateHost("ca", "v", "/plugin marketplace update codearbiter"),
            _FakeUpdateHost("ca-codex", "ca-codex-v",
                            "codex plugin add ca-codex@codearbiter"),
            _FakeUpdateHost("ca-pi", "ca-pi-v",
                            "pi update npm:@arbiterforge/ca-pi"),
        )
        for host in hosts:
            with self.subTest(target=host.update_target):
                line = U.notice_line("0.7.4", "0.7.5", host=host)
                self.assertIn(f"(run {host.update_command})", line)

    def test_unknown_host_descriptor_suppresses_notice(self):
        self.assertIsNone(U.notice_line(
            "1.0.0", "9.0.0", host=_FakeUpdateHost(target=None, prefix=None, command=None)))


# =========================================================================== cache read/write + is_stale (AC-4)
class TestStateCache(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._tmp.name, "sub", "update-state.json")

    def tearDown(self):
        self._tmp.cleanup()

    def test_read_missing_file_returns_empty_dict(self):
        self.assertEqual(U.read_state(self.path), {})

    def test_write_then_read_round_trips(self):
        U.write_state({"latest": "2.10.0", "checked_at": 1000.0}, self.path)
        self.assertEqual(U.read_state(self.path),
                          {"latest": "2.10.0", "checked_at": 1000.0})

    def test_read_corrupt_json_degrades_to_empty_dict(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{ not valid json")
        self.assertEqual(U.read_state(self.path), {})

    def test_read_non_dict_json_degrades_to_empty_dict(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump([1, 2, 3], f)
        self.assertEqual(U.read_state(self.path), {})

    def test_write_creates_parent_dirs(self):
        U.write_state({"latest": "2.9.0", "checked_at": 1.0}, self.path)
        self.assertTrue(os.path.isfile(self.path))

    def test_write_never_raises_on_bad_path(self):
        # A path under a file (not a dir) can't be created — must degrade silently.
        blocked = os.path.join(self._tmp.name, "afile")
        with open(blocked, "w") as f:
            f.write("x")
        bad_path = os.path.join(blocked, "update-state.json")
        try:
            U.write_state({"latest": "2.9.0", "checked_at": 1.0}, bad_path)
        except Exception as e:  # noqa: BLE001
            self.fail(f"write_state raised: {e}")

    def test_legacy_unkeyed_cache_is_not_attributed_to_any_host(self):
        legacy = {"latest": "2.15.6", "checked_at": 1000.0}
        self.assertEqual(U.target_state(legacy, host=_FakeUpdateHost("ca", "v")), {})
        self.assertEqual(
            U.target_state(legacy, host=_FakeUpdateHost("ca-codex", "ca-codex-v")), {})

    def test_malformed_target_rows_degrade_to_empty(self):
        state = {"schema": 1, "targets": {"ca": "not-an-object"}}
        self.assertEqual(U.target_state(state, host=_FakeUpdateHost("ca", "v")), {})


class TestIsStale(unittest.TestCase):

    def test_none_checked_at_is_stale(self):
        self.assertTrue(U.is_stale(None, now=1_000_000))

    def test_within_interval_not_stale(self):
        self.assertFalse(U.is_stale(1_000_000, now=1_000_000 + 3600))

    def test_ac4_same_day_second_check_not_stale(self):
        checked_at = 1_000_000
        now = checked_at + 3600 * 2   # 2 hours later, same day
        self.assertFalse(U.is_stale(checked_at, now, interval=U.ONE_DAY))

    def test_past_interval_is_stale(self):
        checked_at = 1_000_000
        now = checked_at + U.ONE_DAY + 1
        self.assertTrue(U.is_stale(checked_at, now, interval=U.ONE_DAY))

    def test_malformed_checked_at_is_stale(self):
        self.assertTrue(U.is_stale("not-a-number", now=1_000_000))

    def test_non_finite_checked_at_is_stale(self):
        self.assertTrue(U.is_stale(float("nan"), now=1_000_000))
        self.assertTrue(U.is_stale(float("inf"), now=1_000_000))


# =========================================================================== fetch_latest_tag (AC-5)
class _FakeResp:
    """Minimal context-manager stand-in for the object urllib's opener.open()
    returns — used as the injected `opener`'s return value in every
    TestFetchLatestTag case below (fetch_latest_tag never touches real urllib
    internals in tests)."""

    def __init__(self, status=200, body=b"{}"):
        self.status = status
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeOpener:
    """Stand-in for the object `_build_opener()` / `urllib.request.build_opener()`
    returns. Records every `.open()` call (so a test can assert "no request was
    made") and either returns `resp` or raises `exc`."""

    def __init__(self, resp=None, exc=None):
        self.resp = resp
        self.exc = exc
        self.calls = []

    def open(self, req, timeout=None):
        self.calls.append((req, timeout))
        if self.exc is not None:
            raise self.exc
        if isinstance(self.resp, list):
            return self.resp.pop(0)
        return self.resp


class TestFetchLatestTag(unittest.TestCase):

    def test_https_only_rejects_http_without_network_attempt(self):
        opener = _FakeOpener(resp=_FakeResp())
        result = U.fetch_latest_tag(
            url="http://api.github.com/repos/x/y/releases/latest", opener=opener)
        self.assertIsNone(result)
        self.assertEqual(opener.calls, [], "a non-https url must never reach the opener")

    def test_success_selects_only_the_active_release_series(self):
        body = json.dumps([
            {"tag_name": "ca-pi-v0.8.5"},
            {"tag_name": "ca-codex-v0.7.5"},
            {"tag_name": "v2.15.6"},
            {"tag_name": "ca-sandbox-v1.4.0"},
        ]).encode("utf-8")
        opener = _FakeOpener(resp=_FakeResp(status=200, body=body))
        self.assertEqual(U.fetch_latest_tag(tag_prefix="ca-codex-v", opener=opener),
                         "0.7.5")

    def test_target_series_is_found_beyond_the_first_release_page(self):
        first_page = json.dumps([
            {"tag_name": f"v2.{minor}.0"} for minor in range(100)
        ]).encode("utf-8")
        second_page = json.dumps([
            {"tag_name": "ca-codex-v0.7.5"},
        ]).encode("utf-8")
        opener = _FakeOpener(resp=[
            _FakeResp(status=200, body=first_page),
            _FakeResp(status=200, body=second_page),
        ])

        self.assertEqual(
            U.fetch_latest_tag(tag_prefix="ca-codex-v", opener=opener),
            "0.7.5",
        )
        self.assertEqual(len(opener.calls), 2)
        self.assertIn("page=2", opener.calls[1][0].full_url)

    def test_incomplete_later_page_does_not_cache_a_partial_series_result(self):
        first_page = json.dumps(
            [{"tag_name": "ca-codex-v0.7.5"}]
            + [{"tag_name": f"v2.{minor}.0"} for minor in range(99)]
        ).encode("utf-8")
        invalid_second_pages = [
            _FakeResp(status=500, body=b"[]"),
            _FakeResp(status=200, body=b"{}"),
        ]

        for invalid_page in invalid_second_pages:
            with self.subTest(status=invalid_page.status, body=invalid_page._body):
                opener = _FakeOpener(resp=[
                    _FakeResp(status=200, body=first_page),
                    invalid_page,
                ])
                self.assertIsNone(U.fetch_latest_tag(
                    tag_prefix="ca-codex-v", opener=opener))

    def test_page_bound_does_not_cache_a_known_incomplete_enumeration(self):
        full_page = json.dumps(
            [{"tag_name": "ca-codex-v0.7.5"}]
            + [{"tag_name": f"v2.{minor}.0"} for minor in range(99)]
        ).encode("utf-8")
        opener = _FakeOpener(resp=[
            _FakeResp(status=200, body=full_page)
            for _ in range(U.MAX_RELEASE_PAGES)
        ])

        self.assertIsNone(U.fetch_latest_tag(
            tag_prefix="ca-codex-v", opener=opener))
        self.assertEqual(len(opener.calls), U.MAX_RELEASE_PAGES)

    def test_simultaneous_release_series_ignore_every_unrelated_tag(self):
        releases = [
            {"tag_name": "v2.15.6"},
            {"tag_name": "ca-codex-v0.7.5"},
            {"tag_name": "ca-pi-v0.8.5"},
            {"tag_name": "ca-sandbox-v1.4.0"},
            {"tag_name": "ca-codex-v0.7.4"},
        ]
        expected = {
            "v": "2.15.6",
            "ca-codex-v": "0.7.5",
            "ca-pi-v": "0.8.5",
            "ca-sandbox-v": "1.4.0",
        }
        for prefix, version in expected.items():
            with self.subTest(prefix=prefix):
                self.assertEqual(U.select_latest_tag(releases, prefix), version)

    def test_drafts_prereleases_and_malformed_tags_are_not_selected(self):
        releases = [
            {"tag_name": "ca-codex-v9.0.0", "draft": True},
            {"tag_name": "ca-codex-v8.0.0", "prerelease": True},
            {"tag_name": "ca-codex-vnot-semver"},
            {"tag_name": "ca-codex-v0.7.5"},
        ]
        self.assertEqual(U.select_latest_tag(releases, "ca-codex-v"), "0.7.5")

    def test_network_error_fails_silent(self):
        import urllib.error
        opener = _FakeOpener(exc=urllib.error.URLError("no network"))
        self.assertIsNone(U.fetch_latest_tag(opener=opener))

    def test_timeout_fails_silent(self):
        import socket
        opener = _FakeOpener(exc=socket.timeout())
        self.assertIsNone(U.fetch_latest_tag(opener=opener))

    def test_non_200_fails_silent(self):
        opener = _FakeOpener(resp=_FakeResp(status=500, body=b"{}"))
        self.assertIsNone(U.fetch_latest_tag(opener=opener))

    def test_unparseable_body_fails_silent(self):
        opener = _FakeOpener(resp=_FakeResp(status=200, body=b"not json"))
        self.assertIsNone(U.fetch_latest_tag(opener=opener))

    def test_missing_tag_name_fails_silent(self):
        body = json.dumps([{"no_tag": True}]).encode("utf-8")
        opener = _FakeOpener(resp=_FakeResp(status=200, body=body))
        self.assertIsNone(U.fetch_latest_tag(opener=opener))

    def test_default_opener_is_the_hardened_https_only_one(self):
        # Production (no injected opener) must build via _build_opener(), the
        # HTTPS-only-redirect-hardened factory — not a bare urllib.request.urlopen.
        with mock.patch.object(U, "_build_opener",
                                return_value=_FakeOpener(resp=_FakeResp(
                                    body=json.dumps([{"tag_name": "v2.9.0"}]).encode()))) as m:
            self.assertEqual(U.fetch_latest_tag(), "2.9.0")
            m.assert_called_once()

    # ----------------------------------------------------------------- redirect hardening (defense-in-depth)
    def test_redirect_handler_refuses_http_target(self):
        """The core mechanism: _HTTPSOnlyRedirectHandler.redirect_request must
        return None (refuse to build a follow-up request) when the Location
        header points at a non-https url — this is what stops urllib's default
        opener from transparently following an https->http downgrade."""
        handler = U._HTTPSOnlyRedirectHandler()
        req = urllib.request.Request(U.UPDATE_API_URL)
        result = handler.redirect_request(
            req, fp=None, code=302, msg="Found", headers={},
            newurl="http://evil.example/steal")
        self.assertIsNone(result, "a redirect to a non-https target must be refused")

    def test_redirect_handler_allows_https_target(self):
        handler = U._HTTPSOnlyRedirectHandler()
        req = urllib.request.Request(U.UPDATE_API_URL)
        result = handler.redirect_request(
            req, fp=None, code=302, msg="Found", headers={},
            newurl="https://api.github.com/repos/x/y/releases/999999")
        self.assertIsNotNone(result, "a same-scheme https redirect must still be followed")

    def test_fetch_returns_none_when_opener_refuses_http_redirect(self):
        """End-to-end: when the (real or fake) opener raises because our redirect
        handler refused an https->http downgrade, fetch_latest_tag degrades to
        None exactly like every other fetch failure (fail-silent, AC-3/AC-5) —
        it does NOT fall through to reading a body served over http."""
        import urllib.error
        refused = urllib.error.HTTPError(
            U.UPDATE_API_URL, 302, "Found", {"Location": "http://evil.example/steal"}, None)
        # #462: HTTPError is itself a file-like response object. Constructed with
        # fp=None it still allocates a spooled temp file, and letting the garbage
        # collector reclaim it emits `ResourceWarning: Implicitly cleaning up
        # <HTTPError 302>` at an unrelated point in the run. Closing it here is
        # what keeps the suite's warning output empty, so a NEW leak is visible
        # instead of lost in the noise.
        self.addCleanup(refused.close)
        opener = _FakeOpener(exc=refused)
        self.assertIsNone(U.fetch_latest_tag(opener=opener))
        # Exactly one call was attempted (the initial request); no follow-up
        # request to the http:// target was ever made through this opener.
        self.assertEqual(len(opener.calls), 1)


# =========================================================================== refresh_if_stale (AC-3 / AC-4)
class TestRefreshIfStale(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._tmp.name, "update-state.json")

    def tearDown(self):
        self._tmp.cleanup()

    def test_stale_cache_calls_fetcher_and_writes_state(self):
        calls = []

        def fetcher():
            calls.append(1)
            return "2.10.0"

        state = U.refresh_if_stale(now=2_000_000, fetcher=fetcher, path=self.path)
        self.assertEqual(len(calls), 1)
        target = U.target_state(state)
        self.assertEqual(target["latest"], "2.10.0")
        self.assertEqual(target["checked_at"], 2_000_000)
        self.assertEqual(U.read_state(self.path), state)

    def test_ac4_fresh_cache_same_day_makes_no_fetch_call(self):
        first_now = 2_000_000
        U.write_state({"schema": 1, "targets": {
            "ca": {"latest": "2.9.0", "checked_at": first_now},
        }}, self.path)

        calls = []

        def fetcher():
            calls.append(1)
            return "2.10.0"

        second_now = first_now + 3600  # same day, well under ONE_DAY
        state = U.refresh_if_stale(now=second_now, fetcher=fetcher, path=self.path)
        self.assertEqual(calls, [], "a fresh cache must make NO network call")
        target = U.target_state(state)
        self.assertEqual(target["latest"], "2.9.0")
        self.assertEqual(target["checked_at"], first_now, "checked_at unchanged on no-op")

    def test_ac3_fetcher_raising_does_not_propagate(self):
        def bad_fetcher():
            raise OSError("network unreachable")

        try:
            state = U.refresh_if_stale(now=3_000_000, fetcher=bad_fetcher, path=self.path)
        except Exception as e:  # noqa: BLE001
            self.fail(f"refresh_if_stale must fail-silent, raised: {e}")
        # Cache is still updated (checked_at) so we don't retry every session;
        # latest stays whatever it was before (nothing, here).
        target = U.target_state(state)
        self.assertIsNone(target.get("latest"))
        self.assertEqual(target["checked_at"], 3_000_000)

    def test_fetcher_raising_preserves_prior_latest(self):
        U.write_state({"schema": 1, "targets": {
            "ca": {"latest": "2.9.0", "checked_at": 1_000},
        }}, self.path)

        def bad_fetcher():
            raise OSError("network unreachable")

        now = 1_000 + U.ONE_DAY + 1
        state = U.refresh_if_stale(now=now, fetcher=bad_fetcher, path=self.path)
        self.assertEqual(U.target_state(state)["latest"], "2.9.0",
                         "a failed refresh keeps the last-known latest")

    def test_fetcher_returning_none_preserves_prior_latest(self):
        U.write_state({"schema": 1, "targets": {
            "ca": {"latest": "2.9.0", "checked_at": 1_000},
        }}, self.path)
        now = 1_000 + U.ONE_DAY + 1
        state = U.refresh_if_stale(now=now, fetcher=lambda: None, path=self.path)
        self.assertEqual(U.target_state(state)["latest"], "2.9.0")

    def test_each_target_has_an_independent_freshness_and_latest_value(self):
        codex = _FakeUpdateHost("ca-codex", "ca-codex-v", "codex update")
        pi = _FakeUpdateHost("ca-pi", "ca-pi-v", "pi update")
        U.refresh_if_stale(now=1_000, fetcher=lambda: "0.7.5",
                           path=self.path, host=codex)
        calls = []
        state = U.refresh_if_stale(
            now=1_001, fetcher=lambda: calls.append(1) or "0.8.5",
            path=self.path, host=pi)
        self.assertEqual(calls, [1], "a fresh Codex row must not suppress Pi's refresh")
        self.assertEqual(U.target_state(state, host=codex),
                         {"latest": "0.7.5", "checked_at": 1_000})
        self.assertEqual(U.target_state(state, host=pi),
                         {"latest": "0.8.5", "checked_at": 1_001})

    def test_concurrent_same_target_refresh_runs_only_one_fetcher(self):
        first_fetch_entered = threading.Event()
        release_first_fetch = threading.Event()
        second_refresh_done = threading.Event()
        calls = []
        results = []
        errors = []

        def fetcher():
            calls.append(1)
            if len(calls) == 1:
                first_fetch_entered.set()
                if not release_first_fetch.wait(timeout=5):
                    raise TimeoutError("test did not release first fetch")
            return "2.10.0"

        def refresh(done=None):
            try:
                results.append(U.refresh_if_stale(
                    now=2_000_000, fetcher=fetcher, path=self.path))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                if done is not None:
                    done.set()

        first = threading.Thread(target=refresh)
        first.start()
        self.assertTrue(first_fetch_entered.wait(timeout=5))

        second = threading.Thread(target=refresh, args=(second_refresh_done,))
        second.start()
        self.assertTrue(second_refresh_done.wait(timeout=5))
        self.assertEqual(len(calls), 1,
                         "a same-target refresh reservation must suppress a racing fetch")

        release_first_fetch.set()
        first.join(timeout=5)
        second.join(timeout=5)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)

    def test_lock_acquisition_failure_suppresses_fetch(self):
        calls = []
        with mock.patch.object(U, "acquire_lock", return_value=None):
            state = U.refresh_if_stale(
                now=2_000_000,
                fetcher=lambda: calls.append(1) or "2.10.0",
                path=self.path,
            )

        self.assertEqual(calls, [])
        self.assertEqual(state, {})

    def test_failed_reservation_persistence_suppresses_fetch(self):
        calls = []
        with mock.patch.object(U, "write_state", return_value=None):
            state = U.refresh_if_stale(
                now=2_000_000,
                fetcher=lambda: calls.append(1) or "2.10.0",
                path=self.path,
            )

        self.assertEqual(calls, [])
        self.assertEqual(state, {})

    def test_legacy_cache_refresh_migrates_without_reusing_unrelated_latest(self):
        U.write_state({"latest": "2.15.6", "checked_at": 999}, self.path)
        codex = _FakeUpdateHost("ca-codex", "ca-codex-v", "codex update")
        state = U.refresh_if_stale(now=1_000, fetcher=lambda: None,
                                   path=self.path, host=codex)
        self.assertIsNone(U.target_state(state, host=codex).get("latest"))
        self.assertNotIn("latest", state)

    def test_target_written_during_fetch_is_preserved_by_the_final_merge(self):
        codex = _FakeUpdateHost("ca-codex", "ca-codex-v", "codex update")
        claude = _FakeUpdateHost("ca", "v", "claude update")

        def fetcher():
            U.write_state({"schema": 1, "targets": {
                "ca": {"latest": "2.15.7", "checked_at": 2_000},
            }}, self.path)
            return "0.7.6"

        state = U.refresh_if_stale(now=2_001, fetcher=fetcher,
                                   path=self.path, host=codex)
        self.assertEqual(U.target_state(state, host=claude),
                         {"latest": "2.15.7", "checked_at": 2_000})
        self.assertEqual(U.target_state(state, host=codex),
                         {"latest": "0.7.6", "checked_at": 2_001})
        self.assertEqual(U.read_state(self.path), state)

    def test_newer_same_target_refresh_is_not_overwritten_out_of_order(self):
        codex = _FakeUpdateHost("ca-codex", "ca-codex-v", "codex update")

        def slower_older_fetcher():
            U.write_state({"schema": 1, "targets": {
                "ca-codex": {"latest": "0.7.6", "checked_at": 1_001},
            }}, self.path)
            return "0.7.5"

        state = U.refresh_if_stale(
            now=1_000,
            fetcher=slower_older_fetcher,
            path=self.path,
            host=codex,
        )

        self.assertEqual(U.target_state(state, host=codex), {
            "latest": "0.7.6",
            "checked_at": 1_001,
        })
        self.assertEqual(U.read_state(self.path), state)


# =========================================================================== installed_version / plugin_root
class TestInstalledVersion(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _write_manifest(self, version):
        d = os.path.join(self.root, ".claude-plugin")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "plugin.json"), "w", encoding="utf-8") as f:
            json.dump({"name": "ca", "version": version}, f)

    def test_reads_version_from_manifest(self):
        self._write_manifest("2.8.2")
        self.assertEqual(U.installed_version(self.root), "2.8.2")

    def test_missing_manifest_returns_none(self):
        self.assertIsNone(U.installed_version(self.root))

    def test_corrupt_manifest_returns_none(self):
        d = os.path.join(self.root, ".claude-plugin")
        os.makedirs(d)
        with open(os.path.join(d, "plugin.json"), "w", encoding="utf-8") as f:
            f.write("{ not valid")
        self.assertIsNone(U.installed_version(self.root))

    def test_real_plugin_manifest_resolves(self):
        # The actual shipped plugin.json must have a parseable version string.
        real_root = os.path.dirname(_HOOKS_DIR)
        v = U.installed_version(real_root)
        self.assertIsNotNone(v)
        self.assertIsNotNone(U.parse_version(v))


class TestInstalledVersionHostAware(unittest.TestCase):
    """#263 (reliability-002/observability-003): installed_version() must
    resolve the manifest via host.manifest_relpath(), not a hard-coded
    `.claude-plugin/plugin.json` — a ca-codex install ships its manifest at
    `.codex-plugin/plugin.json` ONLY, so the hard-coded path silently
    returned None and the update-available notice never fired on Codex."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    class _FakeCodexHost:
        def manifest_relpath(self):
            return os.path.join(".codex-plugin", "plugin.json")

    def _write_manifest(self, subdir, version):
        d = os.path.join(self.root, subdir)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "plugin.json"), "w", encoding="utf-8") as f:
            json.dump({"name": "x", "version": version}, f)

    def test_codex_shaped_install_reads_codex_plugin_dir(self):
        # No .claude-plugin/ at all — a ca-codex-shaped install.
        self._write_manifest(".codex-plugin", "3.1.0")
        self.assertEqual(
            U.installed_version(self.root, host=self._FakeCodexHost()), "3.1.0")

    def test_codex_host_ignores_claude_plugin_dir(self):
        # Only .claude-plugin/ present (no .codex-plugin/) — must still miss,
        # never accidentally fall back to the wrong host's manifest.
        self._write_manifest(".claude-plugin", "9.9.9")
        self.assertIsNone(U.installed_version(self.root, host=self._FakeCodexHost()))

    def test_default_host_still_reads_claude_plugin_dir(self):
        # No host arg passed at all — resolves via hostapi.load_host(), which
        # in this bare-core checkout (no _host.py beside _updatelib.py) is the
        # Claude default Host(); behavior must stay byte-identical to before.
        self._write_manifest(".claude-plugin", "2.8.2")
        self.assertEqual(U.installed_version(self.root), "2.8.2")

    def test_real_ca_codex_manifest_resolves_via_codex_host(self):
        # The actual shipped ca-codex install: root is plugins/ca-codex, its
        # manifest lives at .codex-plugin/plugin.json ONLY. _HOOKS_DIR is
        # .../plugins/ca/hooks, so climb two levels to plugins/ and sideways
        # into ca-codex/ rather than string-replacing (avoids any risk of a
        # false substring match elsewhere in the path).
        plugins_dir = os.path.dirname(os.path.dirname(_HOOKS_DIR))
        codex_root = os.path.join(plugins_dir, "ca-codex")
        codex_hooks = os.path.join(codex_root, "hooks")
        sys.path.insert(0, codex_hooks)
        try:
            import _host as _codex_host_mod
            v = U.installed_version(codex_root, host=_codex_host_mod.HOST)
        finally:
            sys.path.remove(codex_hooks)
            sys.modules.pop("_host", None)
        self.assertIsNotNone(v)
        self.assertIsNotNone(U.parse_version(v))


class TestStatePath(unittest.TestCase):
    """The cache is user-global (~/.codearbiter/...), NOT under project .codearbiter/."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._saved_home = redirect_home(self._tmp.name)
        self._saved_env = os.environ.pop("CODEARBITER_UPDATE_STATE", None)

    def tearDown(self):
        restore_home(self._saved_home)
        if self._saved_env is not None:
            os.environ["CODEARBITER_UPDATE_STATE"] = self._saved_env
        self._tmp.cleanup()

    def test_default_path_is_user_global_not_project_scoped(self):
        p = U.state_path()
        self.assertTrue(p.startswith(self._tmp.name))
        self.assertIn(".codearbiter", p)
        self.assertNotIn("project", p)

    def test_env_override_wins(self):
        os.environ["CODEARBITER_UPDATE_STATE"] = os.path.join(self._tmp.name, "custom.json")
        try:
            self.assertEqual(U.state_path(), os.path.join(self._tmp.name, "custom.json"))
        finally:
            os.environ.pop("CODEARBITER_UPDATE_STATE", None)


if __name__ == "__main__":
    unittest.main()
