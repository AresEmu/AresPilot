"""Ritaglia un nuovo template da uno screenshot e lo salva alla scala di riferimento del bot.

I template del bot sono "authored" a 2560x1440 (16:9) o 2560x1600 (16:10) e vengono
ridimensionati a runtime. Questo script ritaglia dallo screenshot alla risoluzione che hai
e riporta il ritaglio alla scala di riferimento, così il bot lo usa senza modifiche al codice.

Uso:
    python tools/crop_template.py screens/villaggio_1.png attack.png
Trascina un rettangolo, INVIO/SPAZIO per confermare, c per annullare.
Il vecchio template viene spostato in templates/<profilo>/_old/.
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
from app.config import ASPECT_BASELINE, resolve_aspect_key  # noqa: E402

MAX_VIEW_W, MAX_VIEW_H = 1600, 900  # dimensione massima della finestra di selezione


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return
    shot_path, name = Path(sys.argv[1]), sys.argv[2]
    if not name.endswith(".png"):
        name += ".png"
    img = cv2.imread(str(shot_path))
    if img is None:
        print(f"Impossibile leggere {shot_path}")
        return
    h, w = img.shape[:2]
    key = resolve_aspect_key(w, h)
    if key is None:
        print(f"Screenshot {w}x{h} non è 16:9 né 16:10: il bot non lo supporta.")
        return
    ref_w, ref_h = ASPECT_BASELINE[key]
    sx, sy = ref_w / w, ref_h / h

    view_scale = min(1.0, MAX_VIEW_W / w, MAX_VIEW_H / h)
    view = cv2.resize(img, (int(w * view_scale), int(h * view_scale))) if view_scale < 1 else img
    x, y, rw, rh = cv2.selectROI(f"Seleziona {name}", view, showCrosshair=True)
    cv2.destroyAllWindows()
    if rw == 0 or rh == 0:
        print("Annullato.")
        return
    x, y, rw, rh = (int(round(v / view_scale)) for v in (x, y, rw, rh))
    crop = img[y:y + rh, x:x + rw]

    out_w, out_h = max(1, round(rw * sx)), max(1, round(rh * sy))
    interp = cv2.INTER_CUBIC if sx > 1 else cv2.INTER_AREA
    crop_ref = cv2.resize(crop, (out_w, out_h), interpolation=interp) if (out_w, out_h) != (rw, rh) else crop

    tdir = ROOT / "templates" / key
    dest = tdir / name
    if dest.exists():
        old = cv2.imread(str(dest))
        (tdir / "_old").mkdir(exist_ok=True)
        shutil.move(str(dest), str(tdir / "_old" / name))
        if old is not None:
            print(f"Vecchio {name}: {old.shape[1]}x{old.shape[0]} (spostato in _old/)")
    cv2.imwrite(str(dest), crop_ref)
    print(f"Nuovo {name}: {out_w}x{out_h} @ riferimento {ref_w}x{ref_h} -> {dest}")
    print(f"Coordinate nello screenshot: x={x} y={y} w={rw} h={rh}; "
          f"centro alla scala di riferimento: [{round((x + rw / 2) * sx)}, {round((y + rh / 2) * sy)}]")


if __name__ == "__main__":
    main()
