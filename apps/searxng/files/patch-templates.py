#!/usr/bin/env python3
"""Copy SearXNG's templates and gate the Preferences link on an SSO cookie.

The main container reads /templates (ui.templates_path). The upstream template
tree is copied here so the only local change is the link guard; upstream
template updates are picked up on every pod start.
"""

import os
import pathlib
import re
import shutil
import sys

SOURCE = pathlib.Path("/usr/local/searxng/searx/templates")
DEST = pathlib.Path("/templates")
COOKIE = os.environ.get("AUTH_COOKIE", "authelia_session")
MARKER = "{%- block linkto_preferences -%}"
END = "{%- endblock -%}"

if not re.fullmatch(r"[A-Za-z0-9_]+", COOKIE):
    sys.exit(f"patch-templates: invalid AUTH_COOKIE {COOKIE!r}")

if DEST.exists():
    # DEST is the emptyDir mount point in Kubernetes, so it cannot be removed;
    # clear its contents and copy over the top instead.
    for child in DEST.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
shutil.copytree(SOURCE, DEST, dirs_exist_ok=True)

base = DEST / "simple" / "base.html"
text = base.read_text(encoding="utf-8")
start = text.find(MARKER)
if start < 0:
    print(
        "patch-templates: linkto_preferences block not found; leaving link visible",
        file=sys.stderr,
    )
    sys.exit(0)
end = text.find(END, start)
if end < 0:
    print(
        "patch-templates: linkto_preferences end tag not found; leaving link visible",
        file=sys.stderr,
    )
    sys.exit(0)
end += len(END)
block = text[start:end]

if COOKIE in block:
    print("patch-templates: Preferences link already guarded")
else:
    inner = block[len(MARKER) : -len(END)]
    guard = (
        MARKER
        + "\n"
        + "        {%- if request.cookies.get('"
        + COOKIE
        + "') -%}\n"
        + inner
        + "\n"
        + "        {%- endif -%}\n"
        + "      "
        + END
    )
    base.write_text(text[:start] + guard + text[end:], encoding="utf-8")
    print(f"patch-templates: Preferences link guarded by {COOKIE}")

for path in DEST.rglob("*"):
    path.chmod(0o755 if path.is_dir() else 0o644)
DEST.chmod(0o755)
