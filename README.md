# Quiz live URL audit

Audits the live public website https://lagale.in/ for HTTP errors, redirects, canonical tags, titles, H1s, internal links and sitemap coverage.

## Run locally
```bash
python scripts/live_audit.py --base https://lagale.in/ --max-pages 1600 --delay 0.25 --out reports
```

## Run on GitHub
Open Actions → **Quiz Live URL Audit** → **Run workflow**. The workflow also runs weekly on Monday at 02:40 UTC.

Generated files:
- `reports/LIVE-AUDIT-REPORT.md`
- `reports/live-url-audit.csv`
- `reports/internal-links.csv`
- `reports/sitemap-not-crawled.csv`

The crawler stays on lagale.in, observes robots.txt when available, and adds a delay between requests. Findings need human review; sitemap coverage does not guarantee Google indexing.
