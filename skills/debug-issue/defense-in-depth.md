# Defense in Depth: Validate at Every Layer

**Symptom:** a bug caused by invalid data is fixed with one check, and that one check feels like enough.
**Technique:** check the value on each layer it crosses. Then another code path, a later refactor or a test mock cannot carry it past every check.

One check removes this instance of the bug. A check per layer removes the possibility of it.

The four layer types are Input Boundary, Operation Check, Context Guard and Forensic Log.

## Method

1. Start from the bad value: find where it is born and list every consumer.
2. Draw its route: name each function or module it passes before the risky operation.
3. Place a layer of each type on that route: Input Boundary, Operation Check, Context Guard, Forensic Log.
4. Prove each layer on its own: write a test that skips the Input Boundary, and assert that the Operation Check throws.

### Layer 1: Input Boundary

The public function refuses arguments that no caller should ever send.

```typescript
function openWorkspace(label: string, rootDir: string) {
  if (!rootDir || rootDir.trim() === '') {
    throw new Error(`rootDir for "${label}" must not be empty`);
  }
  if (!existsSync(rootDir)) {
    throw new Error(`rootDir does not exist: ${rootDir}`);
  }
  if (!statSync(rootDir).isDirectory()) {
    throw new Error(`rootDir is not a directory: ${rootDir}`);
  }
  // ...
}
```

### Layer 2: Operation Check

The function that does the work checks that the value fits what it is about to do.

```typescript
function seedRepository(rootDir: string, tenant: string) {
  if (!rootDir) {
    throw new Error('seedRepository called without a rootDir');
  }
  // ...
}
```

### Layer 3: Context Guard

In one named context, here the test run, the operation refuses any target that could cause harm.

```typescript
async function runGitInit(rootDir: string) {
  const underTest = process.env.NODE_ENV === 'test';
  if (underTest) {
    const target = normalize(resolve(rootDir));
    const scratch = normalize(resolve(tmpdir()));
    const fromScratch = relative(scratch, target);
    if (/^\.\.(?:[\\/]|$)/.test(fromScratch) || isAbsolute(fromScratch)) {
      throw new Error(`Test run tried git init outside ${scratch}: ${target}`);
    }
  }
  // ...
}
```

### Layer 4: Forensic Log

Before the operation runs, a log entry records who called it and with what.

```typescript
async function runGitInit(rootDir: string) {
  const callers = new Error().stack;
  logger.debug('git init requested', { rootDir, cwd: process.cwd(), callers });
  // ...
}
```

## What each layer stops

| Layer | Stops |
|-------|-------|
| Input Boundary | Most bugs |
| Operation Check | Edge cases |
| Context Guard | Dangers specific to one context |
| Forensic Log | Whatever slips past the other three |

Evidence from the session: each layer stopped a case that the other three let through.

- Only the Forensic Log revealed a caller that misused the API.
- Platform-specific edge cases reached the Context Guard.
- Mocked tests went around the Operation Check.
- Callers on other code paths went around the Input Boundary.

## Worked case: empty project directory

An empty project directory made `git init` run inside the source tree. The value took four hops:

1. Test set-up produced an empty string.
2. Project creation received it.
3. Workspace creation passed it on.
4. git ran in `process.cwd()`.

Four guards went in, listed from the operation back to the caller:

- Just before `git init`, `RepoBootstrapper` writes a stack trace to the log.
- Under `NODE_ENV=test`, `RepoBootstrapper` throws if the target sits outside the OS temp directory.
- The workspace manager throws when handed an empty directory.
- Project creation accepts only a directory that exists, is writable and is not empty.

Afterwards the bug could not be reproduced, and the suite of 1847 tests ran green.

## Rules

- A single check fails the moment one path goes around it. Guard each hop the value takes.
- Aim for a structural guarantee: no route lets the bad value reach the operation.
