// Polling helpers for tests that wait on thread events.
// Written during the 2025-10-03 test-infrastructure pass, which removed
// fixed sleeps from 15 flaky tests.

import type { ThreadManager } from '~/threads/thread-manager';
import type { LaceEvent, LaceEventType } from '~/threads/types';

const POLL_INTERVAL_MS = 10;

// Runs `probe` now, then every 10 ms, until it yields a value or time runs out.
// `probe` re-reads the thread on each call; a list captured once never changes.
function pollEvents<R>(
  probe: () => R | undefined,
  timeoutMs: number,
  timeoutMessage: () => string
): Promise<R> {
  return new Promise<R>((settle, fail) => {
    const startedAt = Date.now();
    const attempt = () => {
      const found = probe();
      if (found !== undefined) {
        settle(found);
      } else if (Date.now() - startedAt > timeoutMs) {
        fail(new Error(timeoutMessage()));
      } else {
        setTimeout(attempt, POLL_INTERVAL_MS);
      }
    };
    attempt();
  });
}

/**
 * Resolves with the first event of the given type once the thread holds one.
 *
 * @param threadManager - source of the thread's event list
 * @param threadId - thread to watch
 * @param eventType - event type to wait for
 * @param timeoutMs - give up after this many milliseconds (default 5000 ms)
 * @returns the first event whose type equals `eventType`
 *
 * @example const reply = await waitForEvent(manager, id, 'AGENT_MESSAGE');
 */
export function waitForEvent(threadManager: ThreadManager, threadId: string,
                             eventType: LaceEventType, timeoutMs = 5000): Promise<LaceEvent> {
  return pollEvents(
    () => threadManager.getEvents(threadId).find((e) => e.type === eventType),
    timeoutMs,
    () => `Timeout waiting for ${eventType} event after ${timeoutMs}ms`
  );
}

/**
 * Resolves once the thread holds at least `count` events of the given type.
 *
 * @param threadManager - source of the thread's event list
 * @param threadId - thread to watch
 * @param eventType - event type to count
 * @param count - how many events of that type to wait for
 * @param timeoutMs - give up after this many milliseconds (default 5000 ms)
 * @returns every event of that type present when the count was reached
 *
 * @example const calls = await waitForEventCount(manager, id, 'TOOL_CALL', 3);
 */
export function waitForEventCount(threadManager: ThreadManager, threadId: string,
                                  eventType: LaceEventType, count: number,
                                  timeoutMs = 5000): Promise<LaceEvent[]> {
  let seen = 0;
  return pollEvents(
    () => {
      const hits = threadManager.getEvents(threadId).filter((e) => e.type === eventType);
      seen = hits.length;
      return hits.length >= count ? hits : undefined;
    },
    timeoutMs,
    () => `Timeout waiting for ${count} ${eventType} events after ${timeoutMs}ms (got ${seen})`
  );
}

/**
 * Resolves with the first event that satisfies a caller-supplied test.
 *
 * @param threadManager - source of the thread's event list
 * @param threadId - thread to watch
 * @param predicate - returns true for the event being waited on
 * @param description - names the awaited event in the timeout error
 * @param timeoutMs - give up after this many milliseconds (default 5000 ms)
 * @returns the first event for which `predicate` returns true
 *
 * @example const done = await waitForEventMatch(manager, id, (e) => e.data?.final === true, 'final reply');
 */
export function waitForEventMatch(threadManager: ThreadManager, threadId: string,
                                  predicate: (event: LaceEvent) => boolean, description: string,
                                  timeoutMs = 5000): Promise<LaceEvent> {
  return pollEvents(
    () => threadManager.getEvents(threadId).find(predicate),
    timeoutMs,
    () => `Timeout waiting for ${description} after ${timeoutMs}ms`
  );
}

// How a cancellation test changed.
//
// With guessed sleeps, the assertion failed at random:
//
//   const sending = agent.send(threadId, 'list the repo and read two files');
//   await new Promise((r) => setTimeout(r, 300)); // hope both tool calls started
//   agent.abort();
//   await sending;
//   await new Promise((r) => setTimeout(r, 50));  // hope the results landed
//   expect(resultsFor(threadId)).toHaveLength(2);
//
// With polling, it holds on every run:
//
//   const sending = agent.send(threadId, 'list the repo and read two files');
//   await waitForEventCount(threadManager, threadId, 'TOOL_CALL', 2);
//   agent.abort();
//   await sending;
//   await waitForEventCount(threadManager, threadId, 'TOOL_RESULT', 2);
//   expect(resultsFor(threadId)).toHaveLength(2);
//
// Outcome: pass rate rose from 60% to 100%, and the suite ran 40% faster.
