# PIB Exam Daily

A free website that pulls the Press Information Bureau's releases several times a day and sorts them into **read first, read next, skim and skip** for UPSC and APPSC Group 1 and 2. It runs on GitHub's free servers, so nothing needs to stay switched on at home.

## What you get

- A page for each day, with the releases ranked by likely exam value and the reason for each ranking.
- Highlighted names, acronyms and figures under each title (scheme names, exercises, outlays) for Prelims revision.
- An **Andhra Pradesh** tag and an **APPSC** view that pushes AP and state-relevant items up.
- A read tracker, Save with your own one-line note, search across 30 days, and a Markdown export for revision.
- A **How to read PIB** page with a ten-minute daily routine and what to note from each type of release.
- Optional AI notes per important release: Prelims facts, a Mains angle, a practice question and a short Telugu summary. These are off until you add an API key, and the site labels them as AI-written.

## Read this before you rely on it

- **The ranking is rules, not magic.** It uses ministry weights and keyword signals from `config.json`. It will sometimes bury something you wanted. Open the skip list weekly, and change the weights when it gets something wrong.
- **The PIB fetch has not been tested against the live site.** The environment this was built in cannot reach pib.gov.in, so the parser was tested on sample pages and checked against the layout of one real PIB page (the `Posted On: 14 DEC 2018 12:38PM by PIB Delhi` line matches). Treat the first scheduled run as the real test: see "First run" below.
- **PIB's feed only lists about the latest 20 releases.** That is why the workflow runs every hour. If you turn that off you will lose releases.
- **AI notes can be wrong.** They are generated from the release text only, but still check them against the PIB page.
- Release titles link to the original PIB page. Do not republish PIB text elsewhere as your own.

## Put it online (about 15 minutes, no coding)

1. Create a free account at github.com and make a **new repository** (public is simplest). Name it anything, for example `pib-daily`.
2. Upload everything in this folder to it. On the repository page choose **Add file, Upload files** and drag the folder contents in, including the hidden `.github` folder. (If your browser will not upload hidden folders, use GitHub Desktop or the commands below.)
3. In the repository, open **Settings, Pages**. Under **Build and deployment**, set **Source** to **GitHub Actions**.
4. Open the **Actions** tab, choose **Update PIB and deploy site**, then **Run workflow**.
5. When the run finishes (a few minutes), your site is at `https://YOUR-USERNAME.github.io/REPO-NAME/`. The address also shows on the finished deploy job.

From then on it updates itself every hour. You do nothing.

### First run: how to tell it worked

- Open the finished run and read the **Fetch and tag new releases** step. You want a line like `saved 14 new, 0 failed`.
- Open your site. The yellow "demo data" banner disappears once real releases arrive.
- If the step fails with `every new release failed to fetch or parse; PIB may have changed its page layout`, the run stops on purpose and the site keeps its last good data. Send me the log and the address of one failing PIB release and I will fix the parser.

### Command-line version

```bash
git init -b main && git add -A && git commit -m "PIB Exam Daily"
git remote add origin https://github.com/YOUR-USERNAME/REPO-NAME.git
git push -u origin main
```

## Turn on the AI notes (optional)

1. Create an API key in the Anthropic Console.
2. In your repository open **Settings, Secrets and variables, Actions, New repository secret**. Name it `ANTHROPIC_API_KEY` and paste the key.
3. The next run adds notes to releases ranked "good" or above, at most 30 a day (change `max_items_per_day` in `config.json`). Usage is billed to your Anthropic account, so check the Console for what it costs you.

To switch it off, delete the secret. To get notes in English only, set `"telugu": false` in `config.json`.

## Tune what the site flags

Everything lives in `config.json`:

| Setting | What it does |
| --- | --- |
| `thresholds` | Score needed for read first, read next and skim |
| `ministry_weights` | Starting score by ministry. Raise or lower any of them |
| `high_signal` / `low_signal` | Phrases that add or subtract points, such as "Cabinet approves" or "courtesy call" |
| `subjects` | Keywords that decide the subject tags |
| `ap_keywords` | Place and product names that earn the Andhra Pradesh tag. Add your own |
| `extra_feeds` | More PIB feeds to read |

After a change, run the workflow again or wait for the next hourly run. The new rules apply to new releases; releases already saved keep their old tags.

### Add the PIB Vijayawada regional feed

Open `https://www.pib.gov.in/ViewRss.aspx?reg=3` in your browser (the page lists PIB's feeds), copy the address of the feed you want, and add it:

```json
"extra_feeds": [
  { "name": "PIB Vijayawada", "url": "PASTE-THE-FEED-ADDRESS-HERE" }
]
```

## Run it on your own computer

```bash
pip install -r requirements.txt
python scripts/fetch_pib.py          # fetch and tag; writes site/data/
cd site && python -m http.server 8000   # then open http://localhost:8000
python -m unittest discover tests -v    # run the checks
```

To try the site without touching PIB, run `python tests/make_fixtures.py` then `python scripts/fetch_pib.py --fixtures tests/fixtures --sample`. This writes clearly labelled demo releases; the first real run deletes them.

## How it works

1. `scripts/fetch_pib.py` reads PIB's RSS feed, which has only a title and a link, so it opens each new release page for the ministry, posted time and text.
2. `scripts/classify.py` scores each release and pulls out names, acronyms and figures.
3. `scripts/enrich.py` (optional) asks Claude for exam notes on the important ones.
4. Results are written to `site/data/YYYY-MM-DD.json` and `site/data/index.json`, and the static site in `site/` reads them.
5. `.github/workflows/daily.yml` repeats this every hour and publishes the site.

## Files

```
config.json                  rules you can edit
scripts/                     fetch, tag and AI-note code
site/                        the website (index.html, guide.html, app.js, style.css, data/)
tests/                       offline checks and sample-page generator
.github/workflows/daily.yml  the hourly schedule and deploy
```

If the Actions tab ever shows the schedule as disabled, open the workflow and re-enable it, or click Run workflow once.
