"""Cattura screenshot della finestra di Clash (Google Play Games) con lo stesso codice del bot.

Uso (dalla cartella principale del progetto):
    python tools/grab.py villaggio
Premi INVIO per ogni scatto, scrivi q + INVIO per uscire.
I file finiscono in screens/<nome>_<n>.png alla risoluzione reale della finestra.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
from app.services.window import WindowService  # noqa: E402
from app.config import resolve_aspect_key  # noqa: E402


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "screen"
    out_dir = ROOT / "screens"
    out_dir.mkdir(exist_ok=True)
    ws = WindowService()
    if not ws.hwnd and not ws.find_window():
        print("Finestra di Clash non trovata. Apri il gioco (o fissa la finestra nelle Settings del bot).")
        return
    print(f"Gli screenshot vengono salvati in: {out_dir}")
    n = len(list(out_dir.glob(f"{label}_*.png")))
    while True:
        cmd = input(f"[{label}] INVIO = scatta, q = esci > ").strip().lower()
        if cmd == "q":
            break
        frame = ws.screenshot()
        if frame is None:
            print("Screenshot fallito, riprova.")
            continue
        h, w = frame.shape[:2]
        n += 1
        path = out_dir / f"{label}_{n}.png"
        cv2.imwrite(str(path), frame)
        print(f"Salvato {path}  {w}x{h}  profilo={resolve_aspect_key(w, h)}")


if __name__ == "__main__":
    main()
