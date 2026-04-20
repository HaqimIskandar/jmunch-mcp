# jmunch-mcp benchmark

## direct (no proxy)

| call | response bytes | ~tokens |
|---|---:|---:|
| scrape(en.wikipedia.org/wiki/Artificial_intelligence) | 634,333 | 158,583 |
| scrape(en.wikipedia.org/wiki/Machine_learning) | 301,187 | 75,296 |
| map(docs.python.org) | 98,983 | 24,745 |
| search(large language models, limit=10) | 3,796 | 949 |
| **total** | **1,038,299** | **259,574** |

## through jmunch-mcp

| call | response bytes | ~tokens |
|---|---:|---:|
| scrape(en.wikipedia.org/wiki/Artificial_intelligence) | 1,007 | 251 |
| scrape(en.wikipedia.org/wiki/Machine_learning) | 1,005 | 251 |
| map(docs.python.org) | 2,043 | 510 |
| search(large language models, limit=10) | 3,796 | 949 |
| jmunch.describe($LAST_HANDLE) | 953 | 238 |
| jmunch.peek($LAST_HANDLE, n=5) | 2,278 | 569 |
| jmunch.search($LAST_HANDLE, 'neural') | 631 | 157 |
| **total** | **11,713** | **2,928** |

## delta

- bytes saved: **1,026,586** (98.9%)
- tokens saved: **~256,646** (bytes / 4)

_timings: direct=16.4s, proxied=9.2s_
