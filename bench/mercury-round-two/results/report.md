| Goal | Claude | Mercury |
|---|---|---|
| email-editor-01-segment-numeric | pass 68.0s | pass 31.8s |
| email-editor-02-merge-fallback | pass 66.3s | pass 28.2s |
| email-editor-03-condition-operators | pass 77.8s | pass 34.8s |
| email-editor-04-engagement-clock | pass 45.5s | pass 96.1s |
| email-editor-05-csv-edges | pass 62.2s | FAIL none |
| hud-01-notes-under-options | pass 49.6s | pass 33.2s |
| hud-02-notion-cover-roundtrip | pass 43.2s | FAIL none |
| hud-03-switch-company-errors | pass 46.7s | pass 27.6s |
| hud-04-number-and-duration | pass 76.9s | FAIL none |
| hud-05-youtube-start | pass 68.6s | pass 33.0s |

claude: 10/10 goals held-out green (100%), median time to verified 64.2s; per attempt: 20/20 green, 20/20 in one iteration, median 65.1s, mean 63.7s

mercury: 7/10 goals held-out green (70%), median time to verified 34.0s; per attempt: 14/20 green, 20/20 in one iteration, median 66.5s, mean 78.4s

Exit criterion (N >= 10, Mercury median faster, pass rate within 10 points): Mercury does not win
