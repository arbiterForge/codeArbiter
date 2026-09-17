# Spec/plan conformance golden

The reviewed reference pair is stored once under `../reference/` and is treated
as immutable conformance input. This directory records its byte identities so
tests do not silently bless regenerated output:

```text
993ab984404fd92339bd42bd62d30a3db5f28a2311ad087740ee24d0c855cff3  spec.json
d206bff4525ce9498b0d20ee5621a1199eeef57fb986b25c0828ebb60fc2c6b4  spec.html
7d1a2e86dde48210cdc7362ea3270746cd2b6caf4468c464eb3ae4f5becd5356  plan.json
fdc917767b25928a5b27b1ecc5da89e3d3172d41ebe921ef0282c73077961bd8  plan.html
```

These files are draft reference artifacts, not approvals or execution evidence.
Changing any digest requires an explicit review of the original contract and
the independent conformance oracle; regeneration alone is not acceptance.

The independently serialized current-schema import is pinned separately. The
Python 3.14 conformance oracle parses the embedded model, serializes the declared
safe-integer/UTF-16-key-order profile without importing the Go canonicalizer, and
requires these identities plus the full rendered-byte identity:

```text
kind  normative_sha256                                                model_sha256                                                    html_sha256
spec  c14d6ac6673cb032ef42f1e3cd03e557eec10fba716bfd8831ae17d7cea83560  3c509e9042b40599b51c27c8881219c1ca99f49f55abf6e72292a8de6f2a3620  6432d7bb6241c6ae620bcda669698f9985ae4e57f949b2f5292de5e72771d043
plan  8cbb42800e1ce9ef86405decadbcf84bd6486515616d7cc3cce34d731f342830  cd0647912158fb02bd1681c116a4500b2f9bde6c91041d80467d71d1ebbc247e  977ee61b675d717a33519d07cb9a06b3f5b3195aad9c312e661d8b792b7b8626
```

The gate also performs a real `PENDING` to `IN_PROGRESS` transition and checks
that revision/model identity advance while normative identity remains stable.
