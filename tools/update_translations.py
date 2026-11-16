#!/usr/bin/env python3
"""Update the ModelerEvo translations (Qt Linguist files).

1. Extract from the code every text passed to ``tr("...")`` (the English text).
2. Update each ``i18n/modeler_evo_<language>.ts``: existing translations are kept,
   new texts are added as "to translate" (``unfinished``), texts that no longer
   exist in the code are removed.
3. Compile the ``.ts`` files to ``.qm`` with ``lrelease`` (Qt 5 or 6), if available.

Usage:
    python3 tools/update_translations.py            # update and compile all languages
    python3 tools/update_translations.py --add de   # add a new language (German)
    python3 tools/update_translations.py --check    # fail if some texts are not translated

Translations are entered with Qt Linguist (``linguist i18n/modeler_evo_fr.ts``) or
directly in the ``.ts`` file. Only the Python standard library is required;
``lrelease`` comes with the Qt tools (Debian/Ubuntu: ``qt6-l10n-tools``).
"""

import argparse
import ast
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I18N_DIR = os.path.join(ROOT, "i18n")
CONTEXT = "ModelerEvo"  # same as i18n.CONTEXT
PREFIX = "modeler_evo_"
EXCLUDED_DIRS = {"tools", "i18n", "__pycache__", ".git", ".claude"}


def source_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRS)
        for name in sorted(filenames):
            if name.endswith(".py"):
                yield os.path.join(dirpath, name)


def extract():
    """Texts to translate: {English text: [(relative file, line), …]}, in code order."""
    messages = {}
    for path in source_files():
        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), rel)
        calls = [n for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "tr"]
        for call in sorted(calls, key=lambda c: (c.lineno, c.col_offset)):
            if not call.args:
                continue
            arg = call.args[0]
            if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
                print(f"Warning: {rel}:{call.lineno}: tr() without a literal text (ignored)", file=sys.stderr)
                continue
            messages.setdefault(arg.value, []).append((rel, call.lineno))
    return messages


def read_ts(path):
    """{English text: (translation, finished?)} from an existing .ts file."""
    result = {}
    if not os.path.exists(path):
        return result
    for msg in ET.parse(path).getroot().iter("message"):
        source = msg.findtext("source") or ""
        tr_el = msg.find("translation")
        text = (tr_el.text or "") if tr_el is not None else ""
        finished = tr_el is not None and tr_el.get("type") not in ("unfinished", "vanished", "obsolete")
        result[source] = (text, finished and bool(text))
    return result


def write_ts(path, language, messages, existing):
    root = ET.Element("TS", version="2.1", language=language)
    ctx = ET.SubElement(root, "context")
    ET.SubElement(ctx, "name").text = CONTEXT
    todo = 0
    for source, locations in messages.items():
        msg = ET.SubElement(ctx, "message")
        for rel, line in locations:
            ET.SubElement(msg, "location", filename="../" + rel, line=str(line))
        ET.SubElement(msg, "source").text = source
        text, finished = existing.get(source, ("", False))
        el = ET.SubElement(msg, "translation")
        el.text = text
        if not finished:
            el.set("type", "unfinished")
            todo += 1
    ET.indent(root, space="    ")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE TS>\n')
        fh.write(ET.tostring(root, encoding="unicode"))
        fh.write("\n")
    removed = sorted(set(existing) - set(messages))
    return todo, removed


def find_lrelease():
    candidates = [os.environ.get("LRELEASE"), "lrelease", "lrelease-qt6", "lrelease-qt5",
                  "pyside6-lrelease", "/usr/lib/qt6/bin/lrelease", "/usr/lib/qt5/bin/lrelease"]
    for c in candidates:
        if c and (shutil.which(c) or os.path.isfile(c)):
            return shutil.which(c) or c
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--add", metavar="LANGUAGE", help="add a language (two-letter code, e.g. de)")
    parser.add_argument("--check", action="store_true", help="fail if some texts are not translated")
    parser.add_argument("--no-compile", action="store_true", help="do not generate the .qm files")
    args = parser.parse_args()

    os.makedirs(I18N_DIR, exist_ok=True)
    messages = extract()
    print(f"{len(messages)} translatable texts in the code")

    languages = sorted(f[len(PREFIX):-3] for f in os.listdir(I18N_DIR)
                       if f.startswith(PREFIX) and f.endswith(".ts"))
    if args.add and args.add not in languages:
        languages.append(args.add)

    incomplete = False
    for lang in languages:
        ts = os.path.join(I18N_DIR, f"{PREFIX}{lang}.ts")
        todo, removed = write_ts(ts, lang, messages, read_ts(ts))
        print(f"  {lang}: {len(messages) - todo} translated, {todo} to translate"
              + (f", {len(removed)} removed" if removed else ""))
        for r in removed:
            print(f"      removed: {r!r}")
        incomplete |= todo > 0

    if not args.no_compile:
        lrelease = find_lrelease()
        if lrelease is None:
            print("lrelease not found: the .qm files are not regenerated (install the Qt tools).",
                  file=sys.stderr)
            return 1
        for lang in languages:
            ts = os.path.join(I18N_DIR, f"{PREFIX}{lang}.ts")
            subprocess.run([lrelease, "-silent", ts, "-qm", ts[:-3] + ".qm"], check=True)
        print(".qm files generated")

    if args.check and incomplete:
        print("Some texts still need to be translated.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
