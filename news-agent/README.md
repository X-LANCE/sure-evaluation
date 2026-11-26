# SURE news-agent

Generate evaluation announcements from versioned SURE pipeline facts. The
agent is an independent Python package: it reads evaluation code and metadata,
uses Kimi `k3.1-pro` for release copy, and writes only announcement artifacts.
See [ARCHITECTURE.md](ARCHITECTURE.md) for the module map and publication boundary.

## What readers see

- The repository README shows the five most recent active announcements, newest
  first, as linked 760 × 280 SVG cards with a white background and black text.
  A single `<pre>` strip provides horizontal scrolling on GitHub. Each card
  includes the date, capability summary, metrics, pipeline brief and source PR.
- `docs/news/index.html` provides one release timeline under `#updates`, with
  English/Chinese switching, task and text filters, light/dark themes, exact
  pipeline IDs and source links. There is no second latest-support rail above
  the same timeline.
- `docs/news/index.md` retains the complete announcement and revision history;
  `latest.md` contains the five most recent active announcements.

The README and release notes are generated from the same validated entries in
`docs/news/entries/`. Existing entries are immutable. A correction gets a new
ID with `revision` and `supersedes`, keeping the prior evidence available.
The date comes from the source commit. GitHub merge subjects supply PR numbers;
changes without a recognized PR use their source commit link.

## Install and validate locally

Run these commands from the repository root:

```bash
python -m venv news-agent/.venv
news-agent/.venv/bin/python -m pip install -e 'news-agent[dev]'
cp news-agent/config.yaml.example news-agent/config.yaml
news-agent/.venv/bin/python -m news_agent --config news-agent/config.yaml check
news-agent/.venv/bin/python -m pytest news-agent/tests -q
```

With PyYAML and Pydantic 2 already installed, the source package can also run
without installation:

```bash
PYTHONPATH=news-agent/src python -m news_agent --config news-agent/config.yaml.example check
PYTHONPATH=news-agent/src python -m news_agent --config news-agent/config.yaml.example render --output /tmp/sure-news-preview
```

`render` validates the entries against their frozen Git commits and writes a
preview plus `preview.diff`. Only `render --write` updates the working-tree
announcement files. `check` verifies entry facts, links, anchors and generated
file freshness without publishing. The tests also compare the checked-in JSON
schema with `Entry.model_json_schema()`.

For a local browser preview, install the optional `news-agent[preview]` extra
and run:

```bash
news-agent/.venv/bin/python -m pip install -e 'news-agent[preview]'
news-agent/.venv/bin/python news-agent/deploy/build_preview.py
```

Open `news-agent/state/visual-preview/index.html` to compare the README,
Markdown history and standalone release page. This preview approximates
GitHub styling; GitHub's own Markdown renderer determines the live README
layout. Preview files are ignored by Git.

## Configuration and credentials

Paths in the configuration resolve relative to the configuration file. Keep an
independent checkout with enough Git history to read the polling cursor and
all entry source commits. The example configuration uses `fetch: false` and
`mode: dry-run` for local inspection. For scheduled `run` polling, set `fetch:
true` and verify `repository`, `remote`, `base_branch` and `ref` match the
intended source and publication repository.

`site_repository` controls the release page's repository links and defaults to
`repository`. `pages_url` controls the README's release-history link and
defaults to `https://<owner in lowercase>.github.io/<repository name>/` for that
site repository. For example, an upstream installation can explicitly use:

```yaml
repository: PigeonDan1/sure-evaluation
site_repository: X-LANCE/sure-evaluation
pages_url: https://x-lance.github.io/sure-evaluation/
```

The canonical upstream repository and PR base are now
`X-LANCE/sure-evaluation`. GitHub resolves the historical
`PigeonDan1/sure-evaluation` name to that repository. The example preserves
the historical `repository` value because published entries bind their source
links to that alias and are immutable; its explicit display settings use the
canonical upstream name. Do not rewrite old entries to rename their evidence.

These display settings do not change Git push targets or enable Pages. The
personal-fork command described below uses its fixed personal site settings.
A fork or custom-domain deployment should set its own display URLs before
regenerating files.

Provide `NEWS_AGENT_KIMI_API_KEY` through the service environment or a private
credential file with mode `0600`. The agent does not load other agents'
credentials or shared `.env` files. Local configuration, credentials, SQLite
state, logs and previews are not publication artifacts. `doctor` checks local
configuration; `doctor --smoke` calls the real model once without publishing:

```bash
PYTHONPATH=news-agent/src python -m news_agent --config news-agent/config.yaml doctor
PYTHONPATH=news-agent/src python -m news_agent --config news-agent/config.yaml doctor --smoke
```

## Two polling commands

Both commands inspect committed changes on the selected main branch, not the
list of open PRs. An unmerged PR is not announced as supported. New usable
atomic pipelines qualify; incidental source edits do not automatically become
announcements. The model is fixed to `k3.1-pro`; invalid model output, incomplete
responses, inconsistent facts or broken links abort publication.

| Behavior | `run` | `poll-personal` |
| --- | --- | --- |
| Source | Configured repository/ref | `PigeonDan1/sure-evaluation:main` |
| Detection | Newly registered atomic pipelines | New pipelines and material revisions to published capabilities |
| Model work | English copy for pending jobs | Candidate selection, then English and Chinese copy for selected candidates |
| No candidates | Does not call Kimi | Still calls Kimi for an empty selection review |
| Persistent state | Cursor, job queue, frozen evidence, cached copy and errors | Cursor; no persistent draft-copy cache or job queue |
| Publication | `dry-run`, `pr`, or `docs-commit` | Direct documentation push to the fixed personal `main` |

### General `run` workflow

```bash
PYTHONPATH=news-agent/src python -m news_agent --config news-agent/config.yaml run
PYTHONPATH=news-agent/src python -m news_agent --config news-agent/config.yaml status
```

The first run initializes its cursor without backfilling history. Use
`run --since <base-commit>` for an explicit historical range. The queue stores
frozen evidence and successful model copy, so retries can reuse the copy.
Previewed model jobs can later be published; an offline `--copy-file` fixture
is allowed only in dry-run and cannot be promoted to remote publication.

`run --mode pr` creates a documentation commit in an isolated worktree, pushes
`news-agent/<job-key-prefix>` and opens a PR through `gh`. It does not merge the
PR. `run --mode docs-commit` pushes the same kind of branch without opening a
PR. Neither mode pushes directly to the base branch. These commands require
credentials for their explicitly configured remote repository.

`preview_from_working_tree: true` is available only for isolated dry-run
validation before announcement templates are committed. Remote publication
rejects this option. Preserve exactly one `SURE-NEWS` marker pair in README;
the agent does not insert or repair missing markers.

### Personal-fork deployment

`poll-personal` is an explicit direct-publication command. It fetches upstream
and personal `main`, reviews new capabilities and revisions, then pushes only
to `bichengzhang09-crypto/sure-evaluation:main`. Its repository URLs and branch
are fixed in `personal.py`; configuration `mode`, `site_repository` and
`pages_url` do not redirect or turn this command into a dry-run. Do not use it
as a local preview command.

This path uses deterministic entry IDs and the committed personal history to
avoid duplicates, including a retry after a successful push whose cursor write
was interrupted. A failure before publication leaves the source range for a
later retry, which may call Kimi again because draft copy is not cached here.
Both polling commands use a process lock to prevent overlapping runs and the
Kimi client's bounded network retries.

## Automatic output boundary

After an accepted source change, polling regenerates content using the
installed renderer. Only these paths are publishable:

| Output | Allowed change |
| --- | --- |
| `README.md` | Only content between `SURE-NEWS:START` and `SURE-NEWS:END` |
| `docs/news/entries/<id>.yaml` | New validated entries; published entries cannot be overwritten |
| `docs/news/cards/<id>.svg` | Generated announcement cards |
| `docs/news/index.html` | Release timeline and its generated content |
| `docs/news/index.md`, `docs/news/latest.md` | Release history and recent announcements |
| `docs/news/banner.svg` | Generated release-note banner |

IDs must match the entry slug format. Other Markdown/YAML files under
`docs/news/`, `NEWS.md`, evaluation code, route/catalog files, tests, workflow
files and renderer templates are outside this write boundary. The README's
surrounding project documentation is preserved byte for byte.

Framework, layout, template, configuration and service upgrades are maintainer
changes. Polling does not redesign the cards or update its installed source
checkout. Deploy reviewed renderer changes explicitly; fetching a newer target
branch alone does not update the code loaded by the running installation.

## Scheduling and Pages

The repository's `deploy/sure-news-agent.service` and `.timer` are generic
installation templates. They run `run` from an isolated checkout, every 30
minutes with a randomized delay. They are not installed or started by this
package. Review the checkout, environment, configuration and write paths before
installing them as user units. Keep the generic configuration in dry-run until
its publication mode is deliberately selected.

The existing personal deployment uses a separate `news-agent.timer` and a
service that invokes `poll-personal`. Its schedule is 00:00, 06:00, 12:00 and
18:00 Asia/Shanghai, with persistent scheduling and user lingering configured
on that host. That machine-specific installation is not the generic template.
Check its state with `systemctl --user status news-agent.timer` and its output
with `journalctl --user -u news-agent.service`.

`.github/workflows/announcement-pages.yml` deploys the generated `docs/news/`
site after relevant `main` pushes or a manual workflow dispatch. Repository
Pages settings and permissions must allow that workflow. The deployment copies
existing artifacts; it does not call Kimi or run the poller. Announcement CI
checks the package and generated files without publishing. Installing or
changing a remote scheduled publisher remains a separate maintainer action.
