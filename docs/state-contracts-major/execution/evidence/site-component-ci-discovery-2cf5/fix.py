from pathlib import Path
O=Path(__file__).resolve().parent
site=O/'candidate/site';site.mkdir(exist_ok=True)
p=site/'package.json';s=p.read_text(encoding='utf8')
needle='    "test:browser": "playwright test",'
assert s.count(needle)==1
p.write_text(s.replace(needle,needle+'\n    "test:components": "playwright test --config=playwright.components.config.ts",'),encoding='utf8',newline='\n')
p=O/'candidate/.github/workflows/docs.yml';s=p.read_text(encoding='utf8')
needle='      - name: Browser publication gate\n'
assert s.count(needle)==1
s=s.replace(needle,'      - name: Browser component acceptance\n        run: npm run test:components\n'+needle)
p.write_text(s,encoding='utf8',newline='\n')
p=O/'candidate/.github/scripts/test_ci_impact.py';s=p.read_text(encoding='utf8')
assert s.count('if name != "test:browser":')==1
s=s.replace('if name != "test:browser":','if name not in {"test:browser", "test:components"}:')
needle='            "google-chrome --version", "npm run test:browser",'
assert s.count(needle)==1
s=s.replace(needle,'            "google-chrome --version", "npm run test:components", "npm run test:browser",')
p.write_text(s,encoding='utf8',newline='\n')
# Exact existing component configuration, needed by the cross-file contract.
import subprocess
R=Path('C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter')
(site/'playwright.components.config.ts').write_bytes(subprocess.check_output(['C:/Program Files/Git/cmd/git.exe','show','2cf5fafac374791e6fc7c0c98d0a6f43c275c82c:site/playwright.components.config.ts'],cwd=R))
