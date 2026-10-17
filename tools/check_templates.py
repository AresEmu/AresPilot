"""Verifica tutti i template contro una cartella di screenshot, con lo stesso matching del bot.

Uso:
    python tools/check_templates.py               # usa la cartella screens/
    python tools/check_templates.py screens --annotate
Per ogni template stampa il punteggio migliore trovato (TM_CCOEFF_NORMED, come il bot),
lo screenshot dove l'ha trovato e la posizione. Sotto 0.80 = quasi certamente da rifare.
--annotate salva in screens/_check/ copie degli screenshot con i match disegnati.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
from app.config import ASPECT_BASELINE, resolve_aspect_key  # noqa: E402

THRESHOLD = 0.80


def referenced_templates():
    names = set()
    for py in (ROOT / "app").rglob("*.py"):
        names.update(re.findall(r"'([A-Za-z0-9_]+\.png)'", py.read_text(encoding="utf-8", errors="ignore")))
    return names


def score(shot, tmpl, ref_w, ref_h):
    h, w = shot.shape[:2]
    sx, sy = w / ref_w, h / ref_h
    th, tw = tmpl.shape[:2]
    nw, nh = max(1, round(tw * sx)), max(1, round(th * sy))
    if (nw, nh) != (tw, th):
        tmpl = cv2.resize(tmpl, (nw, nh), interpolation=cv2.INTER_AREA if min(sx, sy) < 1 else cv2.INTER_CUBIC)
    if nw > w or nh > h:
        return 0.0, None, (nw, nh)
    res = cv2.matchTemplate(shot, tmpl, cv2.TM_CCOEFF_NORMED)
    _, mx, _, loc = cv2.minMaxLoc(res)
    return float(mx), loc, (nw, nh)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    annotate = "--annotate" in sys.argv
    shots_dir = Path(args[0]) if args else ROOT / "screens"
    shots = {}
    for p in sorted(shots_dir.glob("*.png")):
        img = cv2.imread(str(p))
        if img is not None:
            shots[p.name] = img
    if not shots:
        print(f"Nessuno screenshot in {shots_dir}")
        return
    keys = {resolve_aspect_key(i.shape[1], i.shape[0]) for i in shots.values()} - {None}
    if len(keys) != 1:
        print(f"Gli screenshot devono avere tutti lo stesso profilo (trovati: {keys or 'nessuno valido'})")
        return
    key = keys.pop()
    ref_w, ref_h = ASPECT_BASELINE[key]
    tdir = ROOT / "templates" / key
    used = referenced_templates()
    print(f"Profilo {key} (riferimento {ref_w}x{ref_h}), {len(shots)} screenshot\n")

    rows, marks = [], {n: [] for n in shots}
    for tp in sorted(tdir.glob("*.png")):
        tmpl = cv2.imread(str(tp))
        if tmpl is None:
            continue
        best = (0.0, None, None, None)
        for sname, simg in shots.items():
            s, loc, size = score(simg, tmpl, ref_w, ref_h)
            if s > best[0]:
                best = (s, sname, loc, size)
        rows.append((best[0], tp.name, best[1], best[2]))
        if best[1] and best[2] is not None:
            marks[best[1]].append((tp.name, best[0], best[2], best[3]))

    print(f"{'esito':7} {'score':>6}  {'template':26} {'screenshot':24} posizione")
    for s, name, sname, loc in sorted(rows):
        flag = "OK" if s >= THRESHOLD else "RIFARE"
        if name not in used:
            flag += "*"
        print(f"{flag:7} {s:6.3f}  {name:26} {str(sname):24} {loc}")
    missing = sorted(n for n in used if not (tdir / n).exists())
    print("\n* = non referenziato con nome fisso nel codice (eroi/truppe sono caricati per nome dinamico)")
    if missing:
        print("Referenziati nel codice ma assenti in questa cartella:", ", ".join(missing))

    if annotate:
        out = shots_dir / "_check"
        out.mkdir(exist_ok=True)
        for sname, items in marks.items():
            img = shots[sname].copy()
            for name, s, (x, y), (w, h) in items:
                color = (0, 200, 0) if s >= THRESHOLD else (0, 0, 255)
                cv2.rectangle(img, (x, y), (x + w, y + h), color, 2)
                cv2.putText(img, f"{name} {s:.2f}", (x, max(12, y - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            cv2.imwrite(str(out / sname), img)
        print(f"\nImmagini annotate in {out}")


if __name__ == "__main__":
    main()
