#!/usr/bin/env python3
"""Tests the real executable through the stdlib installed-payload bridge."""
from __future__ import annotations
import hashlib
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/"core/pysrc"))
from _artifactlib import ArtifactClient, ArtifactError, checked_spec_index
INSTALLATION = None

def setUpModule():
    global INSTALLATION
    configured = os.environ.get("ARTIFACT_TEST_INSTALLATION")
    if configured:
        INSTALLATION = Path(configured).resolve(strict=True)
    else:
        temporary = tempfile.TemporaryDirectory(prefix="ca-artifact-test-install-")
        unittest.addModuleCleanup(temporary.cleanup)
        INSTALLATION = Path(temporary.name)/"payload"
        subprocess.run([sys.executable,str(REPO/"tools/build-artifacts.py"),
                        "--output",str(INSTALLATION)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/"repo";self.root.mkdir()
        self.client=ArtifactClient(self.root,INSTALLATION)

    def create(self):
        return self.client.call("create",{"operation_id":"bridge-spec-create","artifact_id":"SPEC-BRIDGE","kind":"spec","slug":"bridge","title":"Bridge fixture","summary":"Incomplete draft, not an approved fixture."})

    def test_real_cli_draft_and_index(self):
        caps=self.client.call("capabilities");self.assertEqual(caps["public_registrations_added"],0)
        self.create();items=list(self.client.index("spec"));self.assertEqual(len(items),1)
        self.assertFalse(items[0]["authority"]["authority_verified"])
        result=self.client.call("validate",{"artifact_id":"SPEC-BRIDGE","gate":"ready"},permit_invalid=True)
        self.assertFalse(result["valid"])
        self.assertEqual(checked_spec_index(self.root,INSTALLATION),[])

    def test_tampered_view_is_not_readable(self):
        self.create();p=self.root/".codearbiter/specs/bridge.html"
        p.write_bytes(p.read_bytes().replace(b"Bridge fixture",b"Modified view",1))
        with self.assertRaises(ArtifactError) as got:list(self.client.index())
        self.assertEqual(got.exception.code,"RENDER_DRIFT")

    def test_unknown_request_fields(self):
        with self.assertRaises(ArtifactError):self.client.call("create",{"force":True})

    def test_changed_installed_binary(self):
        dest=Path(self.tmp.name)/"installation";shutil.copytree(INSTALLATION,dest)
        system={"Linux":"linux","Darwin":"darwin","Windows":"windows"}[platform.system()]
        arch={"x86_64":"amd64","amd64":"amd64","aarch64":"arm64","arm64":"arm64"}[platform.machine().lower()]
        manifest=json.loads((dest/"release.json").read_text());name=manifest["binaries"][system+"/"+arch]["file"]
        p=dest/name;p.write_bytes(p.read_bytes()+b"changed")
        with self.assertRaises(ArtifactError) as got:ArtifactClient(self.root,dest).call("capabilities")
        self.assertEqual(got.exception.code,"PACKAGE_INTEGRITY")

    def test_symlink_binary_rejected(self):
        dest=Path(self.tmp.name)/"installation";dest.mkdir()
        shutil.copy(INSTALLATION/"release.json",dest/"release.json")
        for p in INSTALLATION.glob("ca-artifact-*"):(dest/p.name).symlink_to(p)
        with self.assertRaises(ArtifactError):ArtifactClient(self.root,dest).call("capabilities")

    def test_linked_or_reparse_installation_directory_rejected(self):
        linked=Path(self.tmp.name)/"linked-installation"
        if os.name == "nt":
            subprocess.run(["cmd","/c","mklink","/J",str(linked),str(INSTALLATION)],
                           check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        else:
            linked.symlink_to(INSTALLATION,target_is_directory=True)
        with self.assertRaises(ArtifactError):ArtifactClient(self.root,linked)

    def test_artifact_mutations_never_execute_content(self):
        self.create();identity=self.client.call("identity",{"artifact_id":"SPEC-BRIDGE"})
        marker=self.root/"SHOULD_NOT_EXIST"
        request={"artifact_id":"SPEC-BRIDGE","operation_id":"bridge-inert-update","expected":{"revision":identity["revision"],"model_sha256":identity["model_sha256"]},"changes":[{"op":"record.update","symbol":"INTENT-01","fields":{"problem":f"$(touch {marker}) <script>alert(1)</script>"}}]}
        self.client.call("apply",request);self.assertFalse(marker.exists())
        data=self.client.call("read",{"artifact_id":"SPEC-BRIDGE","symbol":"INTENT-01","mode":"exact"})
        self.assertIn("<script>",data["record"]["problem"])

    def test_helper_child_receives_no_parent_environment(self):
        real_popen = subprocess.Popen
        calls = []

        def recording_popen(*args, **kwargs):
            calls.append(kwargs.copy())
            return real_popen(*args, **kwargs)

        with mock.patch.object(subprocess, "Popen", side_effect=recording_popen):
            self.client.call("capabilities")
        self.assertEqual(calls[-1].get("env"), {})

if __name__=="__main__":unittest.main(verbosity=2)
