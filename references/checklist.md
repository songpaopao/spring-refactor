# Spring Service Refactoring Checklist

Use this checklist before and during a refactor.

## 1. External Contract

- Which public method or endpoint is the real entry point?
- What inputs, outputs, and exceptions are externally observable?
- Is the caller depending on null handling, default values, status codes, or error messages?
- Is any contract change required? If yes, stop and declare it first.

## 2. Flow Stages

Mark the current code by stage:

- condition validation
- parameter construction
- business processing
- post-processing

If one block mixes multiple stages, split it before extracting abstractions.

For stateful methods, also mark:

- lock acquisition and release
- other resource acquisition and release
- acquisition success flags or initialization flags
- cache read and cache write
- DB write
- auto-triggered post actions

## 3. Responsibility Boundaries

Look for logic that should move apart:

- validation logic
- DTO or VO conversion
- domain decision logic
- query orchestration
- write orchestration
- async side effects
- response assembly

Name extracted methods after the responsibility, not after the syntax.
Treat unclear naming as a refactor failure, not a style nit.

Reject names such as:

- `handle`, `process`, `common`, `helper`, `util`
- `data`, `obj`, `result`, `tmp`
- names that do not reveal stage or business meaning

## 4. Safe Extraction Heuristics

Prefer these moves first:

- extract private stage methods
- introduce a local context object for shared workflow data
- introduce a transition context object for lock key, cache state, counters, and filtered IDs
- isolate repeated repository or mapper preparation
- isolate lock and release flow
- isolate resource cleanup flow
- isolate acquisition result flags so cleanup conditions are obvious
- isolate cache TTL and invalidation policy
- move post-processing out of the main transaction path when behavior stays the same

Delay these moves unless clearly justified:

- base classes
- generic utility classes
- wide shared abstractions
- cross-module refactors

## 5. Performance Review

Check only after readability improves, or when the user asks for optimization:

- duplicate queries
- repeated remote calls
- avoidable object conversion
- repeated scans over the same collection
- unnecessary writes

Do not change side-effect order or transactional behavior silently.

## 6. Final Check

- Does the entry method read as a clean workflow?
- Are the four stages visible?
- Are there comments marking major stages or explaining non-obvious business intent?
- Are method and variable names explicit enough that the workflow can be understood without reading every implementation detail?
- Are cleanup points still obvious, especially `finally`, `try-with-resources`, context restore, unlock, or shutdown paths?
- Are cleanup operations correctly guarded so only successfully acquired or initialized resources are released?
- Did any public signature change?
- Did return structure or exception behavior change?
- Are tests present for the touched path?

## 7. Post-Refactor Review

- Re-read the changed entry method without looking at internals first. Does the flow still make sense line by line?
- Did any extracted helper mix more than one stage without necessity?
- Did the refactor leave enough comments for the next reader to understand stage boundaries and critical business decisions quickly?
- Did any new method, context object, or variable get a vague name that hides responsibility or business meaning?
- Did the refactor introduce vague abstractions, utility dumping, or premature reuse?
- Did query order, write order, async logging, notifications, or transaction boundaries shift?
- Did lock handling, cache mutation, TTL refresh, or auto-claim side effects shift in a way that changes state semantics?
- Did any cleanup path regress, including lock release, thread-pool shutdown, stream close, or thread-local context restore?
- Did any cleanup become unconditional even though acquisition or initialization may fail?
- Does the diff show hidden contract drift even though the method signature stayed the same?
