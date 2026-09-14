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
