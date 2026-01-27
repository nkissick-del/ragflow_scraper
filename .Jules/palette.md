## 2026-01-27 - Add loading states to Run Scraper buttons
**Learning:** Declarative UX improvements (like adding CSS classes for loading states) can conflict with existing imperative JavaScript that manually manipulates the DOM (e.g., `textContent = 'Starting...'`).
**Action:** When refactoring for UX, always inspect associated JavaScript event handlers to ensure they don't overwrite or conflict with the new declarative behaviors.
