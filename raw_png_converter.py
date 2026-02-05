import argparse
import os
from pathlib import Path

import numpy as np
import cv2

BAYER_MAP = {
    "bayerRG8": cv2.COLOR_BayerRG2BGR,
    "bayerBG8": cv2.COLOR_BayerBG2BGR,
    "bayerGR8": cv2.COLOR_BayerGR2BGR,
    "bayerGB8": cv2.COLOR_BayerGB2BGR,
}

def read_raw(path: Path, width: int, height: int, fmt: str) -> np.ndarray:
    data = path.read_bytes()

    if fmt == "mono8":
        expected = width * height
        if len(data) < expected:
            raise ValueError(f"{path.name}: per mažas failas ({len(data)} B), reikia {expected} B")
        return np.frombuffer(data[:expected], dtype=np.uint8).reshape((height, width))

    if fmt == "mono16":
        expected = width * height * 2
        if len(data) < expected:
            raise ValueError(f"{path.name}: per mažas failas ({len(data)} B), reikia {expected} B")
        return np.frombuffer(data[:expected], dtype=np.uint16).reshape((height, width))

    if fmt in BAYER_MAP:
        expected = width * height
        if len(data) < expected:
            raise ValueError(f"{path.name}: per mažas failas ({len(data)} B), reikia {expected} B")
        raw = np.frombuffer(data[:expected], dtype=np.uint8).reshape((height, width))
        return cv2.cvtColor(raw, BAYER_MAP[fmt])

    raise ValueError(f"Nežinomas fmt: {fmt}. Naudok: mono8, mono16, bayerRG8, bayerBG8, bayerGR8, bayerGB8")

def convert_folder(input_dir: Path, output_dir: Path, width: int, height: int, fmt: str, ext: str = ".raw"):
    output_dir.mkdir(parents=True, exist_ok=True)

    files = sorted([p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() == ext.lower()])
    if not files:
        print(f"Nerasta '{ext}' failų: {input_dir}")
        return

    ok_count = 0
    fail_count = 0

    for p in files:
        out_path = output_dir / (p.stem + ".png")
        try:
            img = read_raw(p, width, height, fmt)

            # Jei nori 16-bitą "paversti" į 8-bit (kad peržiūra būtų šviesesnė), atkomentuok:
            # if img.dtype == np.uint16:
            #     img = (img / 256).astype(np.uint8)

            saved = cv2.imwrite(str(out_path), img)
            if not saved:
                raise RuntimeError("cv2.imwrite grąžino False")

            ok_count += 1
            print(f"OK  {p.name} -> {out_path.name}")

        except Exception as e:
            fail_count += 1
            print(f"FAIL {p.name}: {e}")

    print(f"\nBaigta. Sėkminga: {ok_count}, Nepavyko: {fail_count}, Iš viso: {len(files)}")
    print(f"Output folderis: {output_dir}")

def main():
    ap = argparse.ArgumentParser(description="Konvertuoja visus RAW failus iš folderio į PNG ir sudeda į naują folderį.")
    ap.add_argument("--in", dest="input_dir", required=True, help="Input folderis su .raw failais")
    ap.add_argument("--out", dest="output_dir", required=True, help="Output folderis PNG failams")
    ap.add_argument("--width", type=int, required=True, help="Plotis pikseliais")
    ap.add_argument("--height", type=int, required=True, help="Aukštis pikseliais")
    ap.add_argument("--fmt", required=True, help="mono8 | mono16 | bayerRG8 | bayerBG8 | bayerGR8 | bayerGB8")
    ap.add_argument("--ext", default=".raw", help="Kokia įvesties failų galūnė (default: .raw)")
    args = ap.parse_args()

    convert_folder(
        input_dir=Path(args.input_dir),
        output_dir=Path(args.output_dir),
        width=args.width,
        height=args.height,
        fmt=args.fmt,
        ext=args.ext,
    )

if __name__ == "__main__":
    main()
