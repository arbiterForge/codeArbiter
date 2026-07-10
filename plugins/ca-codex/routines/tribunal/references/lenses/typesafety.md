# typesafety — lens mandate

Executed by `tribunal-typesafety-reviewer`. Write contract + evidence discipline: `finding-record.md`. Skip entirely if the language has no static type system.

## Checklist
- Footgun public interfaces: easy to call wrong, no defaults, silent coercion.
- Weak/implicit typing where the language supports better; `any` where a real type exists.
- Type-escape hatches: `as any`, `as unknown as X`, `@ts-ignore`, `@ts-expect-error`, untyped fixtures.
- Unhelpful error messages; undocumented invariants; naming-convention drift within a unit.

## Exposure
Count of public interfaces / exported signatures inspected.

## Out of scope
Test-double typing drift (test-fidelity).
