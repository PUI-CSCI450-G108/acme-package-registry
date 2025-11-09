# Structured logging smoke test

The `scripts/logging_smoke_test.py` helper makes it easy to validate the JSON
logging pipeline without worrying about shell-specific syntax. It works on both
POSIX shells and the Windows `cmd.exe` prompt.

## 1. Choose a log destination and level

Decide where you want the log file to be written and which verbosity to use.

* `LOG_LEVEL=0` — create the file and suppress log output.
* `LOG_LEVEL=1` — emit INFO logs.
* `LOG_LEVEL=2` — emit DEBUG logs.

Set the values for your shell:

### Windows `cmd.exe`
```bat
set LOG_FILE=%TEMP%\acme.log
set LOG_LEVEL=2
```

### PowerShell
```powershell
$env:LOG_FILE = "$env:TEMP/acme.log"
$env:LOG_LEVEL = "2"
```

### POSIX shells (`bash`, `zsh`, etc.)
```bash
export LOG_FILE=/tmp/acme.log
export LOG_LEVEL=2
```

## 2. Run the smoke-test script

From the repository root, execute:

```bash
python scripts/logging_smoke_test.py --user jane@example.com --endpoint /artifact/model-42 --model-id model-42 --latency 0.123
```

On Windows `cmd.exe` the command is identical.

You can customise the message or any of the optional fields. For example:

```bash
python scripts/logging_smoke_test.py "Registry warmup" --status 202 --request-id warmup-1
```

## 3. Inspect the output

Open the log file you configured (for example `%TEMP%\acme.log` or `/tmp/acme.log`).
Each line is a JSON object containing the timestamp, message, level, and the
Lambda metadata supplied through `log_event`.

If you have `CLOUDWATCH_LOG_GROUP`/`CLOUDWATCH_LOG_STREAM` configured, the same
entry is also sent to CloudWatch.
