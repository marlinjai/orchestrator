| Goal | Claude | Mercury |
|---|---|---|
| 01-word-count | pass 23.6s | pass 33.7s |
| 02-slugify-dashes | pass 24.8s | pass 13.9s |
| 03-truncate-width | pass 27.7s | pass 14.9s |
| 04-roman | pass 30.2s | pass 18.9s |
| 05-csv-quotes | pass 31.5s | pass 41.6s |
| 06-cli-count | pass 31.3s | pass 13.4s |
| 07-case-convert | pass 29.0s | pass 14.9s |
| 08-duration-units | pass 28.3s | pass 15.1s |
| 09-lru-cache | pass 29.3s | pass 14.6s |
| 10-wrap | pass 27.0s | pass 19.7s |

claude: 10/10 held-out green (100%), median time to verified 28.6s

mercury: 10/10 held-out green (100%), median time to verified 15.0s

Exit criterion (N >= 10, Mercury median faster, pass rate within 10 points): MERCURY WINS
