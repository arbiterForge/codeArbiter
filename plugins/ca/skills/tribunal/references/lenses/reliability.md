# reliability — lens mandate

Executed by `tribunal-reliability-reviewer`. Evidence-or-drop on every check.

## Checklist
- Async inventory: every `await`, `Promise`, and `.then()` chain has a `.catch`/`try-catch`.
- Error-propagation trace: for every `catch`, what happens next. Acceptable — rethrow, typed fallback, central handler, or a state update notifying the caller. Unacceptable — log-and-return-`undefined`, or swallow entirely. Flag every catch that does not propagate a meaningful signal.
- Race surface: two+ async operations writing shared state (component state, globals, filesystem, DB rows) without locking/serialization; handlers that fire before a prior invocation completes; polling loops without cancellation; message handlers mutating state without queueing.
- Resource lifecycle: every subscription, listener, connection, or timer set up in an init hook has a teardown in cleanup/unmount.
- Boundary conditions: empty, null, single-item collections; zero-value numerics; null API responses.
- Orphan state: state written conditionally but read unconditionally; mutation after unmount (stale closure).

## Exposure
Count of async sites (await/Promise/then) inspected.

## Out of scope
Performance (performance); injection/authz (appsec).
