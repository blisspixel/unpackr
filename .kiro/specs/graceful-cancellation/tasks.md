# Tasks: Graceful Cancellation

- [x] 1. Add `cancellation_requested` flag to UnpackrApp
- [x] 2. Register SIGINT handler in main() (first=flag, second=force exit)
- [x] 3. Check flag before each folder in run() loop
- [x] 4. Add cancellation check to SubprocessSafety.run_with_timeout()
- [~] 5. Track files created during extraction for cleanup (deferred - re-run handles leftovers)
- [x] 6. Show cancellation summary with partial stats
- [x] 7. Added cancellation checkpoints in loose video and junk folder loops

## Complete

Feature shipped in v1.3.0
