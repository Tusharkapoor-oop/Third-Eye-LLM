# WebLens browser smoke test

- measured: 2026-10-27T11:58:09.979705+00:00
- status: **ok**
- python: 3.14.0
- platform: Windows-11-10.0.26300-SP0
- playwright: 1.64.0
- method: HTML shell with <div id="app"> and an inline script

| run | elapsed ms | status | browser_rendered | passages | tokens | proxy requests | rendered text |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 3413.0 | ok | True | 1 | 182 | 1 | True |
| 2 | 1761.5 | ok | True | 1 | 182 | 1 | True |
| 3 | 1702.6 | ok | True | 1 | 182 | 1 | True |

| metric | value |
| --- | --- |
| runs | 3 |
| median first extract including launch | 1761.5 ms |
| min / max | 1702.6 / 3413.0 ms |
| warnings | ['browser_rendered'] |
| same URL under default policy | error (blocked_url) |

Public HTTPS proxy check:

| metric | value |
| --- | --- |
| status | ok |
| elapsed ms | 2117.9 |
| final URL | https://example.com/ |
| proxy requests | 1 |
| Example Domain found | True |

The private-URL check uses the default policy and is expected to fail
before the browser can navigate. The browser is launched behind a local
egress proxy that resolves and validates each destination once; see
`docs/THREAT_MODEL.md` for the remaining limits.
