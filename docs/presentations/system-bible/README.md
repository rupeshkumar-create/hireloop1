# Hireschema System Bible

Leadership presentation: **full pack** merging Business (01), Candidate/Aarya (02), and Recruiter/Nitya (03) details — product, stack, ingest, match math, agents, status, roadmap.

## Files

| File | Purpose |
|------|---------|
| `index.html` | Visual slide deck (diagram-first) |
| `styles.css` / `deck.js` | Deck shell |
| `Hireschema-System-Bible.md` | Markdown + Mermaid twin (Pandoc) |
| `Hireschema-System-Bible.pdf` | Generated PDF (if present) |
| `Hireschema-System-Bible.pptx` | PowerPoint — rebuild with `python3 build_pptx.py` |

## Open the deck

From this folder:

```bash
# any static server, e.g.
npx --yes serve -l 5188 .
# then open http://localhost:5188
```

Or open `index.html` directly in a browser (fonts need network).

**Keys:** `←` `→` · `F` fullscreen · swipe on mobile

## Export PDF (recommended)

1. Open `index.html` in Chrome/Edge  
2. **File → Print** (or Cmd/Ctrl+P)  
3. Destination: **Save as PDF**  
4. Layout: **Landscape**, margins **default/minimum**, enable **Background graphics**  
5. Save as `Hireschema-System-Bible.pdf`

## Pandoc (Markdown twin)

```bash
# Requires pandoc + a Mermaid renderer if you want diagrams in PDF
pandoc Hireschema-System-Bible.md -o Hireschema-System-Bible-from-md.pdf
```

## Spec

`docs/superpowers/specs/2026-07-15-system-bible-presentation-design.md`
