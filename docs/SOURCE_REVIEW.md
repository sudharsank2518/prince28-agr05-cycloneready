
# CycloneReady — Source Review

## Purpose

Track official cyclone and urban-flood preparedness sources before downloading or storing their content.

## Source review

| Source | Website | Robots status | Licence / terms status | Decision |
|---|---|---|---|---|
| NDMA | https://ndma.gov.in/ | 403 — unverified | Permission request sent on 23 Nov 2026; awaiting response | Hold automated download |
| TNSDMA | https://tnsdma.tn.gov.in/ | SSL error — unverified | Permission request sent on 23 Nov 2026; awaiting response | Hold automated download |
| IMD / RSMC | https://rsmcnewdelhi.imd.gov.in/ | 404 — no robots file found | Permission request sent on 23 Nov 2026; awaiting response | Hold reproduction pending permission |

## Permission requests

| Organisation | Contact email | Request date | Status |
|---|---|---|---|
| NDMA | controlroom@ndma.gov.in | 23 Nov 2026 | Awaiting response |
| TNSDMA | tnsdma@tn.gov.in | 23 Nov 2026 | Awaiting response |
| IMD / RSMC | cwdhq2008@gmail.com | 23 Nov 2026 | Awaiting response |

## Rules

- Do not bypass robots.txt restrictions.
- Do not disable SSL certificate verification.
- Do not assume government documents are copyright-free.
- Record the licence or permission for every source.
- Do not download sources with unclear permissions.
- Prefer official sources and direct document links.

## Known gaps

- NDMA automated access rules need clarification.
- TNSDMA SSL trust issue needs investigation.
- IMD/RSMC reproduction permission needs confirmation.
- No source has yet been approved for automated downloading or reproduction.

## HTML extraction benchmark

### Purpose

Compare the existing Trafilatura HTML parser with a basic Python
HTMLParser-based text extraction baseline using three official pages.

Benchmark downloads were stored in the operating system temporary
directory, outside the production corpus.

### Results

| Page | Trafilatura words | Basic parser words | Observation |
|---|---:|---:|---|
| NDMA SACHET About | 42 | 125 | Page largely contains a loading shell and limited extractable content. |
| IMD Cyclone Information | 63 | 536 | Important bulletins and warning resources are referenced through JavaScript link mappings to separate PDFs and images, rather than embedded article text. |
| MHA Disaster Management Division | 1,333 | 2,121 | Trafilatura retained useful division information and document titles while reducing page boilerplate. |

### Findings

- Trafilatura is useful for extracting article-like content from static HTML.
- A larger word count does not indicate better extraction quality; basic extraction can retain navigation and boilerplate.
- JavaScript-driven pages may expose little useful content in downloaded HTML.
- Pages that act as directories of PDF or image resources require separate link discovery and document ingestion.
- HTML tables may lose their row and column relationships during text extraction.

### Decision

Keep Trafilatura as the primary HTML text extractor.

Treat linked PDF/image discovery, dynamically loaded content, and structured
table extraction as separate ingestion challenges. Do not replace
Trafilatura with basic tag stripping based on this benchmark.

### Limitations

- Only three official pages were tested.
- Word and keyword counts are descriptive metrics, not extraction-quality scores.
- The benchmark does not establish source reuse or reproduction permission.
- Results describe the downloaded pages at the time of testing and may change
  when the websites are updated.
- Benchmark files and results remain in the OS temporary directory and are
  not part of the production corpus.
