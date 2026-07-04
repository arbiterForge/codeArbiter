# /ca:config branch — pre-merge TODO (delete this file before merging)

Branch parked until hands-on testing at home. Docs passes to do on PC, not in
a cloud session:

- [ ] **CHANGELOG.md** — a 2.9.0 entry was drafted in the feature commit;
      review/rewrite it (and re-date it) before release.
- [ ] **README.md** — the Configuration section now points at /ca:config, the
      version/command badges were bumped to 2.9.0 / 40, and a catalog row was
      added (the badge-consistency CI gate requires the counts). Review the
      wording; rework freely.
- [ ] **Docs site (site/)** — NOT updated yet, apart from the new
      test/generator/config-registry-consistency.test.ts. Needs: whatever
      hand-authored page or concepts coverage /ca:config should get, and a
      look at whether forge-status / the Forge pages should link the registry.
- [ ] **Hands-on testing** — the standalone picker (raw arrow-key mode in a
      real terminal, Windows included), `configtool.py launch` on a desktop
      (tmux split / new window), and a real /ca:config session flow.

Reference: full inventory lives in plugins/ca/config/registry.json; the
anti-drift gate is .github/scripts/test_config_registry.py.
