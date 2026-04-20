# jmunch-mcp benchmark

## direct (no proxy)

| call | response bytes | ~tokens |
|---|---:|---:|
| list_issues(facebook/react, state=all, per_page=100) | 172,496 | 43,124 |
| list_pull_requests(facebook/react, state=all, per_page=100) | 222,958 | 55,739 |
| list_commits(facebook/react, per_page=100) | 769,047 | 192,261 |
| search_issues(language:python label:bug, per_page=100) | 355,013 | 88,753 |
| **total** | **1,519,514** | **379,878** |

## through jmunch-mcp

| call | response bytes | ~tokens |
|---|---:|---:|
| list_issues(facebook/react, state=all, per_page=100) | 17,150 | 4,287 |
| list_pull_requests(facebook/react, state=all, per_page=100) | 20,697 | 5,174 |
| list_commits(facebook/react, per_page=100) | 19,295 | 4,823 |
| search_issues(language:python label:bug, per_page=100) | 19,764 | 4,941 |
| jmunch.describe($LAST_HANDLE) | 3,425 | 856 |
| jmunch.peek($LAST_HANDLE, n=5) | 32,023 | 8,005 |
| jmunch.slice($LAST_HANDLE, state='open', max_rows=10) | 64,959 | 16,239 |
| **total** | **177,313** | **44,328** |

## delta

- bytes saved: **1,342,201** (88.3%)
- tokens saved: **~335,550** (bytes / 4)

_timings: direct=8.4s, proxied=6.8s_
