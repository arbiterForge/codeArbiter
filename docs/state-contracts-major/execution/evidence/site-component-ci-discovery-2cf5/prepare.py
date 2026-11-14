from pathlib import Path
import subprocess
R=Path('C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter')
O=Path(__file__).resolve().parent
GIT='C:/Program Files/Git/cmd/git.exe'
SOURCE='2cf5fafac374791e6fc7c0c98d0a6f43c275c82c'
for p in ['site/package.json','.github/workflows/docs.yml','.github/scripts/test_ci_impact.py']:
 b=subprocess.check_output([GIT,'show',SOURCE+':'+p],cwd=R)
 assert b==(R/p).read_bytes(),p
 target=O/'candidate'/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b)
test=O/'candidate/.github/scripts/test_ci_impact.py'
s=test.read_text(encoding='utf8')
needle='    def test_diagnostic_exceptions_reject_publication_bypasses_and_unbounded_uploads(self):'
new='''    def test_component_suite_is_discovered_and_success_gates_pages_upload(self):
        scripts = json.loads((REPO_ROOT / "site/package.json").read_text(encoding="utf-8"))["scripts"]
        self.assertEqual(scripts.get("test:components"),
                         "playwright test --config=playwright.components.config.ts",
                         "component specs are outside the production browser testDir")
        config = (REPO_ROOT / "site/playwright.components.config.ts").read_text(encoding="utf-8")
        self.assertRegex(config, r"testDir:\\s*['\\\"]\\./test/components['\\\"]")
        self.assertRegex(config, r"channel:\\s*['\\\"]chrome['\\\"]")
        build = re.sub(r"(?m)\\s+#.*$", "", workflow_jobs(
            DOCS_WORKFLOW.read_text(encoding="utf-8"))["build"])

        def assert_lane(candidate):
            self._assert_build_control_flow(candidate)
            steps = re.split(r"(?m)(?=^      - )", candidate)[1:]
            selected = [step for step in steps
                        if re.search(r"(?m)^        run: npm run test:components$", step)]
            self.assertEqual(len(selected), 1, "component suite must execute exactly once")
            self.assertLess(candidate.index("run: google-chrome --version"),
                            candidate.index("run: npm run test:components"))
            self.assertLess(candidate.index("run: npm run test:components"),
                            candidate.index("uses: actions/upload-pages-artifact@"))

        assert_lane(build)
        for mutation in (
            build.replace("run: npm run test:components", "run: npm run test:browser", 1),
            build.replace("        run: npm run test:components",
                          "        if: false\\n        run: npm run test:components", 1),
            build.replace("        run: npm run test:components",
                          "        continue-on-error: true\\n        run: npm run test:components", 1),
        ):
            with self.subTest(mutation=mutation):
                self.assertNotEqual(mutation, build)
                with self.assertRaises(AssertionError):
                    assert_lane(mutation)

'''
assert s.count(needle)==1
test.write_text(s.replace(needle,new+needle),encoding='utf8',newline='\n')
print(O)
