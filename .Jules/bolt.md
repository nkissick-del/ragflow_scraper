## 2026-01-29 - Shared StateTracker Instance
**Learning:** `ServiceContainer` caches `StateTracker` instances, but `BaseScraper` was creating new instances. This caused the UI to show stale state and wasted IO resources by reloading state files multiple times.
**Action:** When working with services that manage state or expensive resources, always check if they are provided via the `ServiceContainer` before instantiating them directly.
