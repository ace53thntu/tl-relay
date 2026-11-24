# How to write good tests

Load this page when you write or change a test. Load it too when you add a mock, or add a cleanup or helper method that only tests use.

Every test must pass two checks. It names the break it catches, and it exercises the real thing.

```
Break named. Real code exercised.
```

Strict TDD meets both checks at no extra cost:
- The first holds because the red run shows the test failing against real code. That observed failure proves the test can fail.
- For the second, run the test against real dependencies from the start. A mock is allowed only once a dependency is shown to be slow or external.

## Gate checks

### Before you write a test body

Name the production change that would make the test fail.
- No change comes to mind: redesign the test around behavior you can observe.
- The only trigger is edited source text: run the artifact and assert its effects.
- Only an intentional decision can fail it: you have a change detector. Test the behavior that depends on the decision.

Then trace the expected value. Does it reuse logic or helpers from the code under test? Replace it with a literal or a hand-checked fixture.

### Before you add a mock or a test helper

1. List the side effects of the real method. Keep real the ones your test depends on, and mock the slow or external level beneath them.
2. Shape each mock response like the complete real structure.
3. Place a method that only tests call in test utilities, not in production.
4. If you are about to assert on the mock itself, unmock it or delete the assertion.

### Before you finish: the mutation check

Mutate the production code in your head. Every realistic mutation should fail at least one test. Try these:
- a wrong constant or argument;
- the wrong branch handler;
- a missing state change or side effect;
- an empty or default return;
- missing validation for zero, empty, nil, unauthorized, or malformed input.

If no test catches a mutation, either the behavior is unprotected or a test is tautological.

## Name the break

Ask two questions before the test body. Which production change should fail this test? Is that change a bug or a decision?

Keep the test only if one of these faults turns it red:
- the code takes the wrong branch;
- a side effect never happens;
- an argument carries the wrong value;
- a boundary case is mishandled;
- a contract that callers rely on breaks.

### Derive expectations independently

Take expected values from literals and hand-checked fixtures. Prefer table-driven tests whose rows carry a literal `want` field.

An expectation computed by the code under test or its helpers shares that code's bugs, so the assertion passes even when the code is wrong.

Bad: one formatter produces both sides, so the assertion is always true.

```typescript
test('formats the invoice total', () => {
  const expected = formatTotal([{ price: 1500, qty: 3 }]);
  expect(formatTotal([{ price: 1500, qty: 3 }])).toBe(expected);
});
```

Good: the expected value is a string you worked out by hand.

```typescript
test('formats the invoice total for three line items', () => {
  expect(formatTotal([{ price: 1500, qty: 3 }])).toBe('$45.00');
});
```

### No change detectors

A test that only an intentional decision can fail breaks at every redesign and misses real bugs. Constant values, exact message wording, and private structure are typical triggers. Test the behavior that depends on the decision instead.

Do not assert that `MAX_LOGIN_ATTEMPTS` equals 3. Assert that the third wrong password locks the account and that a fourth attempt is refused.

### Behavior over text

Matching a line in a script, skill, or config shows only that the file still says what it says. Pick the evidence by what the file is:

| File | Evidence that counts |
|---|---|
| Script | Run it on controlled input. Assert its output, side effects, or exit code. |
| Document an agent follows | Observe what the consuming agent does. |
| Prose that people read | None. It needs no test. |

### Your code, not the framework

Ask whose behavior each assertion checks.
- Your own code at a boundary: test it. Route registrations, emitted queries, and outgoing payloads all count.
- A library's or framework's behavior: leave it untested. Its maintainers' suite already covers it. The usual mistake asserts that a router calls a registered handler.
- One exception: if upstream behavior once surprised you, record that assumption in one narrow characterization test named after it.
- Your own trivial code, such as constructors, getters, constants, and pure pass-through: test it only when it does work. Work means validation, normalizing, defaults, derivation, enforcing a rule, or a side effect. If it does none, assert on the earliest consumer-visible result that relies on it.

## Exercise the real thing

Keep the mock, and an assertion on it passes. Remove the mock, and the assertion fails. Neither outcome depends on the real component, so never assert on a mock. Assert what the real component does. When the assertion targets the mock itself, unmock it or delete the assertion.

Bad: the test looks for a stand-in element.

```typescript
render(<Page />);
expect(screen.getByTestId('footer-mock')).toBeInTheDocument();
```

Good: the test looks for the real footer by its role.

```typescript
render(<Page />);
expect(screen.getByRole('contentinfo')).toBeInTheDocument();
```

Your human partner phrased the correction as a question: "Are we testing the behavior of a mock?"

### Mock at the right level

1. Find every side effect of the real method before you replace it.
2. Mark the ones your test depends on. Those stay real.
3. Mock only the slow or external operation beneath them.

Bad: mocking `OrderRepository.saveAndIndex` swallows the index write. The duplicate-order check reads that index, so it now sees nothing.

```typescript
vi.mock('./OrderRepository', () => ({
  OrderRepository: { saveAndIndex: vi.fn().mockResolvedValue(undefined) },
}));
```

Good: mock only `PaymentGateway`, which is slow and external. The index write stays real, and the stubbed charge mirrors the documented response in full.

```typescript
vi.mock('./PaymentGateway', () => ({
  PaymentGateway: {
    charge: vi.fn().mockResolvedValue({
      id: 'ch_001', status: 'succeeded', amount: 4500, currency: 'usd',
      createdAt: '2026-01-01T00:00:00Z', receiptUrl: 'https://pay.test/r/ch_001',
    }),
  },
}));
```

### Specific doubles

Check what the contract fixes. Does it fix the arguments, the call count, or the call order? Assert each one it fixes. A spy with no expectations passes for any call, right or wrong.

Give the success, error, and malformed branches separate fixtures or spies. A call down the wrong branch then cannot meet the expectation.

### Complete data

Put every documented field of the real response into the mock, including fields the test never reads. The `PaymentGateway` stub above carries all six for this reason. Suppose downstream code reads a field you left out. It gets nothing, and no error appears. The unit test stays green while the integration is broken.

### Production classes hold production methods

Cleanup that only tests need goes in test utilities. A `destroy()` on the production class is the wrong home.

Two questions decide it. Do only tests call this method? Does the class own the lifecycle of that resource? Move the method to test utilities if only tests call it, or if the class does not own that lifecycle.

### Real components over elaborate mocks

Switch to an integration test with real components when any of these happen:
- mock setup outgrows the test logic;
- the mocks miss methods the real components have;
- tests break whenever the mock changes.

Unsure what to mock? Run the test against the real implementation first. Observe what actually needs to happen.

Your human partner asks: "Do we need to be using a mock here?"

## Ship tests in the same change as the code

A change is complete once it has passed through all three steps: failing test, minimal implementation, refactor.

Which tests ship with it:
- Each behavior the change adds: the tests that behavior needs, and no more.
- Trivial code and prose that people read: none.
- A test that exists only to satisfy the process: none. Someone must maintain it for as long as it exists.

## Quick reference

| You are about to... | Do this |
|---|---|
| Write any test | Name the break. It must be a bug, not a decision. |
| Build an expected value | Derive it by hand. Never with the code under test. |
| Test a script or document | Run it, or pressure-test its consumer. Never grep its text. |
| Write a test around a library you depend on | Cover your boundary contract. Skip the mechanics the library documents. |
| Assert on a mocked element | Test the real component, or unmock it. |
| Mock a method | Learn its side effects, then mock the slow or external level. |
| Build a mock response | Mirror the real structure completely. |
| Add cleanup that only tests use | Put it in test utilities. |
| Watch mock setup balloon | Switch to an integration test with real components. |
| Finish a test file | Run the mutation check. |

## Warning signs

Expected values:
- The assertion compares against the same object the setup built.
- You must run a loop, builder, or helper to learn what the expected value is.

When it goes red:
- Only a panic, a crash, or a selector that matches nothing can turn it red.
- It goes red each time someone changes a decision on purpose, and stays green when a real bug lands.

What it checks:
- It searches source text, or checks that a deleted symbol is still absent.
- It checks something the framework does, so it would keep its meaning with your code gone.
- It was written to raise coverage and asserts no outcome and no side effect.

Mocks and helpers:
- It looks up a `*-mock` test ID, or goes red as soon as the mock is removed.
- Some method on a production class is called only from test files.
- Mock setup fills more than half the test, or you cannot say why the mock is there.
- A mock exists "just to be safe".
