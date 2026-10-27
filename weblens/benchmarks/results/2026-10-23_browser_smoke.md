# WebLens browser smoke test

- measured: 2026-10-23T07:48:06.650014+00:00
- python: 3.14.0
- platform: Windows-11-10.0.26300-SP0
- playwright: 1.64.0
- method: HTML shell with <div id="app"> and an inline script

| metric | value |
| --- | --- |
| first extract including browser launch | 3231.8 ms |
| extract status | ok |
| warnings | ['browser_rendered'] |
| browser_rendered | True |
| passages / tokens | 1 / 182 |
| rendered text found | True |
| private URL | error (blocked_url) |

The private-URL check uses the default policy and is expected to fail
before the browser can navigate. The browser path itself still does not
pin DNS; see `docs/THREAT_MODEL.md`.
