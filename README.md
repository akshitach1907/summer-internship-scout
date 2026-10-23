# Summer 2027 Internship Scout

A daily GitHub Actions monitor preloaded with **your 57 target-company/role rows**. It checks public job listings, filters for marketing/creative internships, deduplicates roles, and opens a **GitHub issue only when new possible matches appear**.

## Setup (about 15 minutes)

1. Create a **private GitHub repository**, e.g. `summer-internship-scout`.
2. Upload **all files including `.github/workflows/daily.yml`** from this ZIP to the root of the repository.
3. In GitHub **Settings → Actions → General → Workflow permissions**, select **Read and write permissions**. Enable GitHub Issues in repository settings if needed.
4. Go to **Actions → Daily internship scout → Run workflow** to test.
5. In **Settings → Notifications**, enable email notifications for your repository's Issues, or use the GitHub mobile app.
6. Optional AI: In **Settings → Secrets and variables → Actions**, add `OPENAI_API_KEY` to get a model-based relevance review. Without it, keyword filters still work. API use may incur charges.

**Schedule:** 12:00 UTC daily, approximately 8 AM EDT / 7 AM EST. GitHub's scheduled runs may be delayed. Change the `cron` value to choose a different UTC hour. GitHub scheduled workflows run from the default branch.

## Coverage — important

- `companies.csv` contains all your companies and target regions, but **a careers URL is not necessarily a job feed**.
- The starter scans linked internship listings on public HTML pages. **It cannot see jobs loaded only by JavaScript, login-only listings, or pages blocking automation.**
- For robust coverage, add an official supported ATS in `companies.csv`:
  - `ats=greenhouse`, `board_token=the-public-board-name`
  - `ats=lever`, `board_token=company-slug`
  - `ats=ashby`, `board_token=company-slug`
- Leave `ats` and `board_token` blank if not verified. **Do not guess tokens.** Different brands can use different recruiting systems.
- The initial run treats all currently detected matches as new. Future runs alert only on newly discovered URLs.
- Roles with unknown dates or visa status remain **unverified**, not eligible by default.
- No automatic job applications are submitted.
- The tool does not guarantee daily comprehensive coverage of all 57 companies. Verify job details on official sites.
- If the GitHub issue fails, inspect the Actions run log. The scan saves deduplication state to `seen.json`.

## Customizing

Edit `companies.csv` to add/remove companies, links, or ATS settings. `monitor=no` disables a row. Edit role keywords and filters in `scout.py`. Review the `seen.json` file if you want to reset alerts.

## Privacy and security

Use a **private repo**, keep API keys in GitHub Secrets, and do not put personal information or credentials into the CSV. The program accesses public career listings only and uses modest request rates.
