#!/usr/bin/env python3
"""Met à jour les traductions de ModelerEvo (fichiers Qt Linguist).

1. Extrait du code tous les textes passés à ``tr("...")`` (le texte anglais).
2. Met à jour chaque ``i18n/modeler_evo_<langue>.ts`` : les traductions existantes sont
   conservées, les nouveaux textes sont ajoutés « à traduire » (``unfinished``), les textes
   qui n'existent plus dans le code sont retirés.
3. Compile les ``.ts`` en ``.qm`` avec ``lrelease`` (Qt 5 ou 6), s'il est disponible.

Usage :
    python3 tools/update_translations.py            # met à jour et compile toutes les langues
    python3 tools/update_translations.py --add de   # ajoute une nouvelle langue (allemand)
    python3 tools/update_translations.py --check    # échoue s'il reste des textes à traduire

Les traductions se saisissent avec Qt Linguist (``linguist i18n/modeler_evo_fr.ts``) ou
directement dans le fichier ``.ts``. Seul le module Python standard est nécessaire ;
``lrelease`` s'installe avec les outils Qt (Debian/Ubuntu : ``qt6-l10n-tools``).
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
CONTEXT = "ModelerEvo"  # identique à i18n.CONTEXT
PREFIX = "modeler_evo_"
EXCLUDED_DIRS = {"tools", "i18n", "__pycache__", ".git", ".claude"}


def source_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRS)
        for name in sorted(filenames):
            if name.endswith(".py"):
                yield os.path.join(dirpath, name)


def extract():
    """Textes à traduire : {texte anglais: [(fichier relatif, ligne), …]}, dans l'ordre du code."""
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
                print(f"Attention : {rel}:{call.lineno} : tr() sans texte littéral (ignoré)", file=sys.stderr)
                continue
            messages.setdefault(arg.value, []).append((rel, call.lineno))
    return messages


def read_ts(path):
    """{texte anglais: (traduction, terminée ?)} d'un fichier .ts existant."""
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
    parser.add_argument("--add", metavar="LANGUE", help="ajoute une langue (code à deux lettres, ex. de)")
    parser.add_argument("--check", action="store_true", help="échoue s'il reste des textes à traduire")
    parser.add_argument("--no-compile", action="store_true", help="ne pas générer les .qm")
    args = parser.parse_args()

    os.makedirs(I18N_DIR, exist_ok=True)
    messages = extract()
    print(f"{len(messages)} textes à traduire dans le code")

    languages = sorted(f[len(PREFIX):-3] for f in os.listdir(I18N_DIR)
                       if f.startswith(PREFIX) and f.endswith(".ts"))
    if args.add and args.add not in languages:
        languages.append(args.add)

    incomplete = False
    for lang in languages:
        ts = os.path.join(I18N_DIR, f"{PREFIX}{lang}.ts")
        todo, removed = write_ts(ts, lang, messages, read_ts(ts))
        print(f"  {lang} : {len(messages) - todo} traduits, {todo} à traduire"
              + (f", {len(removed)} retirés" if removed else ""))
        for r in removed:
            print(f"      retiré : {r!r}")
        incomplete |= todo > 0

    if not args.no_compile:
        lrelease = find_lrelease()
        if lrelease is None:
            print("lrelease introuvable : les .qm ne sont pas régénérés (installer les outils Qt).",
                  file=sys.stderr)
            return 1
        for lang in languages:
            ts = os.path.join(I18N_DIR, f"{PREFIX}{lang}.ts")
            subprocess.run([lrelease, "-silent", ts, "-qm", ts[:-3] + ".qm"], check=True)
        print("Fichiers .qm générés")

    if args.check and incomplete:
        print("Des textes restent à traduire.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
