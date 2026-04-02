# nornir-shared

## Logging convention

`nornir_shared.misc.SetupLogging` is the standard entry point for persistent logging across Nornir projects.

- Set `NORNIR_LOG_ROOT` to enable unified file logging.
- File logs are written to `<NORNIR_LOG_ROOT>/<YYYY-MM-DD>/`.
- Session files are named:
  - `nornir-session-<YYYYMMDD-HHMMSS>.log`
  - `nornir-session-<YYYYMMDD-HHMMSS>-errors.log`
- Keep project identity in logger names (for example `pyre.*`, `nornir_buildmanager.*`) rather than per-project file paths.

### Multiprocessing

For multiprocess workloads, use queue-based logging with a single file writer:

- Parent process starts the listener with `nornir_shared.misc.StartMultiprocessLoggingListener()`.
- Worker processes are configured with `nornir_shared.misc.ConfigureWorkerQueueLogging(...)`.
- Stop the listener at shutdown with `nornir_shared.misc.StopMultiprocessLoggingListener()`.

The parent creates `NORNIR_LOG_SESSION_ID` before worker creation, and workers inherit/reuse that session ID so all process logs land in one session log pair.

### Important guidance

- Do not create ad hoc debug files such as `debug-*.log`.
- Do not hardcode absolute log locations in project code.
- `nornir_shared.prettyoutput` is for user-facing console/status output and should not own persistent file-log sink paths.
