"""Render the ARQEDIA lockups as they appear in the two headers, to PNG.

Each page reproduces one header's markup and the CSS that styles it, read
from the repository: the marketing site's .mark/.wordmark (site.css:31-33)
and the app's .shell header .mark (index.css:47-55, 193-196; App.tsx:1097).
Chrome renders at 8x on a transparent ground; Pillow trims to the ink and
adds a margin.

Run from the repository root, with Chrome and Pillow installed:

    python -I brand/make-lockups.py . brand

The wordmark is set in whatever the stacks resolve to on the machine that
runs it: on Windows, Palatino Linotype for the site's serif and Segoe UI
where Inter is not installed. That is what a Windows visitor sees."""
import re, subprocess, sys, os, tempfile
from PIL import Image

repo, out = sys.argv[1], sys.argv[2]
work = tempfile.mkdtemp()
chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def svg(name):
    text = open(os.path.join(repo, "brand", name), encoding="utf-8").read()
    text = re.sub(r"<metadata>.*?</metadata>", "", text, flags=re.S)
    text = re.sub(r"<\?xml.*?\?>|<!--.*?-->", "", text, flags=re.S)
    return text.strip()


tokens = open(os.path.join(repo, "ui", "src", "tokens.css"), encoding="utf-8").read()
serif = re.search(r"--serif:\s*([^;]+);", tokens).group(1)
deep = re.search(r"--deep:\s*([^;]+);", tokens).group(1).strip()

pages = {
    # Marketing site header: 26px mark, 11px gap, serif 22px/600, .06em, deep.
    "arqedia-lockup-deep": f"""
<a class="mark"><span class="m">{svg('logo-deep.svg')}</span><span class="wordmark">ARQEDIA</span></a>
<style>
.mark{{display:flex;align-items:center;gap:11px}}
.m svg{{width:26px;height:26px;display:block}}
.wordmark{{font-family:{serif};font-size:22px;letter-spacing:.06em;font-weight:600;color:{deep}}}
</style>""",
    # App header: 22px mark, 16px gap, <strong> in the body face 15px, white.
    "arqedia-lockup-white": f"""
<a class="mark"><span class="m">{svg('logo-white.svg')}</span><strong>ARQEDIA</strong></a>
<style>
.mark{{display:flex;align-items:center;gap:16px;color:#fff;
  font:15px/1.55 "Inter",-apple-system,"Segoe UI",system-ui,sans-serif}}
.m svg{{width:22px;height:22px;display:block}}
</style>""",
}

for name, body in pages.items():
    html = os.path.join(work, name + ".html")
    open(html, "w", encoding="utf-8").write(
        "<!doctype html><meta charset=utf-8><style>html,body{margin:0;"
        "background:transparent}body{padding:20px}</style>" + body)
    raw = os.path.join(work, name + ".raw.png")
    subprocess.run([chrome, "--headless=new", "--disable-gpu",
                    "--hide-scrollbars", "--force-device-scale-factor=8",
                    "--default-background-color=00000000",
                    "--window-size=400,80", "--screenshot=" + raw,
                    "file:///" + html.replace("\\", "/")],
                   check=True, capture_output=True)
    img = Image.open(raw).convert("RGBA")
    box = img.getchannel("A").getbbox()
    pad = 48
    trimmed = img.crop(box)
    framed = Image.new("RGBA", (trimmed.width + 2 * pad,
                                trimmed.height + 2 * pad), (0, 0, 0, 0))
    framed.paste(trimmed, (pad, pad))
    final = os.path.join(out, name + ".png")
    framed.save(final, optimize=True)
    print(name, framed.size)
