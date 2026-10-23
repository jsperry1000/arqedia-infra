# brand

The single location for the ARQEDIA mark. Two files, one for light grounds and
one for dark. Nothing else in the repository holds a copy.

| File | Used on |
|---|---|
| `logo-deep.svg` | white and pale grounds — the sign-in card, the marketing site |
| `logo-white.svg` | the navy header and rail |

Both surfaces reference these by relative path, so a replacement here reaches
the application and the site in the same commit:

- `ui/src/App.tsx` imports them, and Vite hashes and bundles them.
- `site/index.html` and `site/pricing/index.html` reference them, and Vite
  rewrites the paths at build.

**These are placeholders and say so in their own source.** They are not a
proposed mark. The icons previously at `ui/public/icon-deep.png` and
`ui/public/icon-white.png` were eBL's and are replaced by these.

To change the mark: replace both files, keep the 64x64 viewBox, keep the deep
version in `#002561` and the reversed version in `#FFFFFF`, and commit.

## Lockups, as PNG (23 October 2026)

The mark and the wordmark together, as each header draws them, for places
that need one image rather than markup - a rendered PDF, a document, a slide.

| File | Drawn as | For |
|---|---|---|
| `arqedia-lockup-deep.png` | the marketing site's header: 26px mark, serif wordmark in `--deep` | white and pale grounds |
| `arqedia-lockup-white.png` | the app's header: 22px mark, bold sans wordmark in white | navy grounds |

Both are transparent, 8x the on-screen size, with a margin. **They are
generated, not drawn:** `make-lockups.py` renders each header's own markup
and CSS from this folder's SVGs and `ui/src/tokens.css` in headless Chrome.
Change the mark or the tokens, run it again, and commit what it writes:

    python -I brand/make-lockups.py . brand

So they are placeholders exactly as the SVGs are. The wordmark is set in
whatever the font stacks resolve to on the machine that runs the script; on
Windows that is Palatino Linotype for the serif and Segoe UI where Inter is
not installed.

The two `ui/public/icon-*.png` named above as replaced are still in the
repository, unreferenced. They are eBL's.
