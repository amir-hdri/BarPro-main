## 2024-05-06 - Label in Name Accessibility
**Learning:** Adding an `aria-label` to a button completely overrides its visible text for screen readers. If a button already has visible text (e.g., `📍 مبدا` or `🔄 بروزرسانی`), adding an English `aria-label` like "Select origin" introduces a WCAG 2.5.3 (Label in Name) violation. Voice dictation software users won't be able to trigger it by saying the visible text, and it creates a jarring language mismatch for localized users.
**Action:** Only add `aria-label` attributes to strictly icon-only buttons (like `☰` or `🌓`). For these buttons, ensure the `aria-label` language matches the surrounding application text (e.g., Persian instead of English) for a cohesive screen reader experience.

## 2024-05-07 - Test Artifact Cleanup
**Learning:** Running test suites can generate unwanted local artifacts like `.db` files (`bot_stats.db`). Staging these files via indiscriminate `git add` pollutes the commit history, introduces bloat, and creates potential security/environment risks.
**Action:** Always verify the Git status and selectively add modified files (`git add <file_path>`) rather than `git add .`, especially after running test suites. Remove any generated test artifacts from the working tree before creating a commit.

## 2026-05-07 - Test Artifact Cleanup
**Learning:** Running test suites can generate unwanted local artifacts like `.db` files (`bot_stats.db`). Staging these files via indiscriminate `git add` pollutes the commit history, introduces bloat, and creates potential security/environment risks.
**Action:** Always verify the Git status and selectively add modified files (`git add <file_path>`) rather than `git add .`, especially after running test suites. Remove any generated test artifacts from the working tree before creating a commit.
