# Log redaction

Floppy removes credentials from log output before a handler writes the output.
This page records the contract, because the boundary is easy to move by
accident and a fault in it is silent: the log looks correct, and the secret is
in it.

## Where the boundary is

`src/config/__init__.py` installs a log record factory during process start.
Python calls this factory for every log record, in every process: Django,
Celery, the Gunicorn workers, and background tasks.

```text
HTTP request
     |
     v
Nginx (port 8000) -----> access log: "$request_method $uri $server_protocol"
     |                   Query strings and referrers are not written.
     v
Gunicorn (port 8001) --> accesslog = None. Nginx owns the request log.
     |                   Gunicorn still writes its error log.
     v
Django / Celery / workers
     |
     |  logger.info("...", value)
     v
install_redacting_log_record_factory()   <- src/app/log_safety.py
     |  1. Renders the "%" arguments one time.
     |  2. Redacts the rendered text.
     |  3. Redacts the traceback text and clears record.exc_info.
     |  4. Redacts record.stack_info.
     |  5. On any error, replaces the message and keeps nothing.
     v
Handlers: console (stdout) and the rotating file (floppy.log)
```

The factory runs before the handlers. Therefore the redaction applies to
container output, to the log file on disk, and to the sanitized log download in
Settings > Advanced. A handler cannot see the original text.

## Three rules that are easy to break

**Install the factory before the handlers run.** `config/__init__.py` is the
first module Django, Celery, and Gunicorn import. Move the installation later,
and the records that the start sequence writes are not redacted.

**Keep the failure closed.** `config/__init__.py` accepts one import fault: an
absent `app` package, which the isolated data path checks produce on purpose.
It raises every other fault. A broad `except` gives a process that starts
normally and writes unredacted logs, with no warning.

**Do not send the original record to a handler.** If the factory cannot render
or redact a message, it replaces the message with `Log message redaction
failed` and clears the exception and stack fields. An unrendered record must
not reach a handler.

`src/app/tests/test_log_safety.py` and
`src/app/tests/test_data_paths.py::test_config_import_reports_a_missing_log_safety_dependency`
enforce these rules.

## What the rules match

`redact_secrets()` in `src/app/log_safety.py` applies these rules in order.

| Rule | Example input | Output |
|---|---|---|
| `Bearer` credential | `Authorization: Bearer abc123` | `Authorization: [REDACTED]` |
| `Basic` credential | `Basic dXNlcjpwYXNz` | `Basic [REDACTED]` |
| Header value | `Cookie: sessionid=abc; csrftoken=d` | `Cookie: [REDACTED]` |
| URL credentials | `postgres://user:pw@db:5432/floppy` | `postgres://[REDACTED]:[REDACTED]@db:5432/floppy` |
| List value | `{'password': ['pw']}` | `{'password': [REDACTED]}` |
| Quoted value | `{"api_key": "two words"}` | `{"api_key": "[REDACTED]"}` |
| Unquoted value | `?X-Plex-Token=abc&size=10` | `?X-Plex-Token=[REDACTED]&size=10` |

A value is a credential when its name **ends** with one of these keywords:
`token`, `secret`, `password`, `passwd`, `apikey`, `api_key`, `api-key`,
`sessionid`.

Match the keyword, not a list of full names. The same credential reaches the
log in many spellings, and a list of full names cannot hold all of them:

| Spelling | Where it comes from |
|---|---|
| `access_token` | Trakt, AniList, Simkl |
| `authToken`, `accessToken` | Plex, Jellyfin clients |
| `X-Plex-Token`, `X-Api-Key` | provider request headers |
| `TMDB_API_KEY` | environment variable dumps |
| `webhook_secret` | integration webhooks |

The keyword must be the last part of the name, so diagnostic fields stay
readable: `status_code=200`, `error_code=RATE_LIMIT`, `token_count=512` and
`tokenizer_config=default` are not changed.

## What the rules do not cover

**OAuth `code` parameters.** `code` is too general to match. `status_code`,
`error_code` and `country_code` are common in diagnostic output, and a rule for
`code` would remove all of them. Nginx removes query strings from the request
log, and Django logs the request path without the query, so an authorization
code has no ordinary route into the log. Do not put one in a log message.

**OAuth `client_id` parameters.** A `client_id` identifies the application, not
the user, so it is not a secret and it stays readable. One case needs care.
Trakt sends Floppy's `client_id` a second time as a `trakt-api-key` header, and
Floppy loads that value from the `TRAKT_API_FILE` secret family. The header form
stays redacted, because `trakt-api-key` ends in a keyword:

```text
headers={'trakt-api-key': '[REDACTED]'}      redacted
?client_id=floppy-web&state=abc              not redacted
```

The second form is an authorize URL that Floppy builds as a redirect target.
It reaches a log by the same narrow route an authorization `code` does, and the
same instruction applies: do not put one in a log message. Use `safe_url()`.

**Values whose name gives no clue.** A rule matches a name, not a value. Write
`logger.info("plex sync failed for %s", safe_url(url))`, not the raw response
body.

**Prose after a header name.** The header rules take the rest of the line, so
`Authorization: Bearer abc sent to trakt` becomes `Authorization: [REDACTED]`
and the words `sent to trakt` are lost. This is deliberate. A header value has
no reliable end delimiter, and a shorter match leaves part of the credential.
Put diagnostic context in a separate log call.

**Other processes.** Nginx writes its own access log, so `nginx.conf` holds the
`floppy_safe` log format. A new process that writes output without the Python
logging module needs its own boundary.

**Error reporting.** When `SENTRY_DSN` is set, the Sentry SDK builds events from
the request and the stack, not from log records, so the factory does not see
them. `src/config/error_reporting.py` is that boundary: it keeps only the request
method and a `safe_url()` URL, drops local variables, source context and
`extra`, and runs `redact_secrets()` over messages, exception values and
breadcrumbs.

## Cost

The factory renders and redacts every record that passes the logger level.
Measured on a 62,668 line corpus:

| Path | Cost |
|---|---|
| One log record | about 25 us, or about 40,000 records per second on one core |
| The 5 MiB log download | about 1.5 s |

Two properties keep the cost predictable. Each rule reads the text one time.
No rule lets two parts of a pattern match the same characters, because that
makes the engine try every split and turns one long line into seconds of
processor time.

`test_redact_secrets_stays_fast_on_a_long_url_like_line` guards this.

## Adding a keyword

1. Add the keyword to `_SECRET_NAME_KEYWORDS` in `src/app/log_safety.py`.
2. Confirm that the keyword cannot be the last part of a diagnostic name.
   `code` fails this test. `token` passes it.
3. Add the spelling to
   `test_redact_secrets_strips_every_credential_name_spelling`.
4. Add any diagnostic name that is now at risk to
   `test_redact_secrets_keeps_names_that_only_end_in_a_keyword_word`.
