"""Zeichnet icon-192.png und icon-512.png passend zu frontend/public/favicon.svg.

Es ist absichtlich kein SVG-Renderer im Spiel: cairosvg, Inkscape oder
ImageMagick waeren eine zusaetzliche Abhaengigkeit nur fuer zwei Dateien, die
sich selten aendern. Pillow liegt ohnehin im Backend, also wird die Geometrie
des Favicons hier noch einmal in Pillow nachgezogen.

Achtung: aendert sich das Favicon, muessen die Werte unten mitwandern. Die
Koordinaten stehen im 32er-Raster der viewBox, GROESSE skaliert sie.

Aufruf:  python scripts/dev/icons_rendern.py
"""

from pathlib import Path
import math

from PIL import Image, ImageDraw

BLAU = (29, 78, 216, 255)        # #1d4ed8, gleich der theme-color der App
WEISS = (255, 255, 255, 255)

# Geometrie im 32er-Raster, 1:1 aus favicon.svg
ECKRADIUS = 7.0
BOGEN_MITTE = (17.3715, 16.0)    # Mittelpunkt des Euro-Bogens
BOGEN_RADIUS = 7.8
BOGEN_STRICH = 2.5
BOGEN_LUECKE = 43.813            # halbe Oeffnung nach rechts, in Grad
BALKEN_STRICH = 2.2
BALKEN = ((8.0, 14.3, 19.2), (8.0, 18.7, 19.2))  # x1, y, x2

# Vierfach und mehr zeichnen und herunterrechnen gibt die Kantenglaettung, die
# Pillow selbst nicht mitbringt.
UEBERABTASTUNG = 8

ZIELE = {192: "icon-192.png", 512: "icon-512.png"}


def _bogen_punkte(mx, my, radius, von, bis, schritte=360):
    """Punkte auf einem Kreisbogen, Winkel in Grad, y zeigt nach unten."""
    punkte = []
    for i in range(schritte + 1):
        grad = von + (bis - von) * i / schritte
        bog = math.radians(grad)
        punkte.append((mx + radius * math.cos(bog), my + radius * math.sin(bog)))
    return punkte


def zeichne(groesse: int) -> Image.Image:
    n = groesse * UEBERABTASTUNG
    s = n / 32.0
    bild = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(bild)

    d.rounded_rectangle([0, 0, n - 1, n - 1], radius=ECKRADIUS * s, fill=BLAU)

    # Der Bogen als gefuelltes Ringsegment. Pillow's line() mit joint="curve"
    # setzt die Verbindungsstuecke zwischen den Segmenten schlecht und hinterlaesst
    # eine Saegezahn-Kante; ein Polygon aus aeusserem und innerem Bogen nicht.
    mx, my = BOGEN_MITTE[0] * s, BOGEN_MITTE[1] * s
    halb = BOGEN_STRICH * s / 2
    von, bis = BOGEN_LUECKE, 360 - BOGEN_LUECKE
    aussen = _bogen_punkte(mx, my, BOGEN_RADIUS * s + halb, von, bis)
    innen = _bogen_punkte(mx, my, BOGEN_RADIUS * s - halb, bis, von)
    d.polygon(aussen + innen, fill=WEISS)
    # Runde Enden, die das Polygon nicht mitbringt
    for grad in (von, bis):
        bog = math.radians(grad)
        px = mx + BOGEN_RADIUS * s * math.cos(bog)
        py = my + BOGEN_RADIUS * s * math.sin(bog)
        d.ellipse([px - halb, py - halb, px + halb, py + halb], fill=WEISS)

    halb = BALKEN_STRICH * s / 2
    for x1, y, x2 in BALKEN:
        d.rounded_rectangle(
            [x1 * s - halb, y * s - halb, x2 * s + halb, y * s + halb],
            radius=halb, fill=WEISS,
        )

    return bild.resize((groesse, groesse), Image.LANCZOS)


def main() -> None:
    ziel = Path(__file__).resolve().parents[2] / "frontend" / "public"
    for groesse, name in ZIELE.items():
        pfad = ziel / name
        zeichne(groesse).save(pfad)
        print(f"{pfad} geschrieben ({groesse}x{groesse})")


if __name__ == "__main__":
    main()
