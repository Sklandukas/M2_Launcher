import re
from pathlib import Path
import numpy as np
import traceback

def _save_data(self, raw_dir, pgm_dir, image, base_name, position_int: int, scalled_position: float):
    try:
        # --- 0) Tipai ir baziniai dalykai
        image = np.asarray(image)  # jei netyčia sąrašas ar pan.
        raw_dir = Path(raw_dir).expanduser().resolve()
        pgm_dir = Path(pgm_dir).expanduser().resolve()
        raw_dir.mkdir(parents=True, exist_ok=True)
        pgm_dir.mkdir(parents=True, exist_ok=True)

        base_name_str = "image" if base_name is None else str(base_name)
        safe_name = re.sub(r'[^A-Za-z0-9._-]+', '_', base_name_str).strip('_') or "image"

        raw_path = raw_dir / f"{safe_name}.raw"
        np.ascontiguousarray(image).tofile(str(raw_path))

        if image.ndim == 3 and image.shape[-1] in (3, 4):  
            img2d = (
                0.2126 * image[..., 0].astype(np.float64) +
                0.7152 * image[..., 1].astype(np.float64) +
                0.0722 * image[..., 2].astype(np.float64)
            )
        elif image.ndim == 3 and image.shape[-1] == 1:
            img2d = image[..., 0]
        elif image.ndim == 2:
            img2d = image
        else:
            raise ValueError(f"Nepalaikomas PGM formatas: shape={image.shape}")

        if np.issubdtype(img2d.dtype, np.floating):
            vmin = float(np.nanmin(img2d))
            vmax = float(np.nanmax(img2d))
            if not np.isfinite([vmin, vmax]).all() or vmax == vmin:
                data = np.zeros_like(img2d, dtype=np.uint8)
                maxval = 255
            else:
                scaled = (img2d - vmin) / (vmax - vmin)
                data = np.clip(np.round(scaled * 255.0), 0, 255).astype(np.uint8)
                maxval = 255
        elif img2d.dtype == np.uint8:
            data = img2d
            maxval = 255
        elif img2d.dtype == np.uint16:
            data = img2d
            if data.dtype.byteorder in ('<', '=', '|'):
                data = data.byteswap().newbyteorder('>')
            maxval = 65535
        else:
            vmin = int(img2d.min())
            vmax = int(img2d.max())
            if vmax == vmin:
                data = np.zeros_like(img2d, dtype=np.uint8)
            else:
                rng = vmax - vmin
                data = np.clip(np.round((img2d.astype(np.float64) - vmin) / rng * 255.0), 0, 255).astype(np.uint8)
            maxval = 255

        h, w = int(data.shape[0]), int(data.shape[1])

        pgm_path = pgm_dir / f"{safe_name}.pgm"
        with open(pgm_path, 'wb') as f:
            f.write(f"P5\n{w} {h}\n{maxval}\n".encode('ascii'))
            f.write(np.ascontiguousarray(data).tobytes())

        print(f"[OK] RAW: {raw_path} ({raw_path.stat().st_size} B)")
        print(f"[OK] PGM: {pgm_path} ({pgm_path.stat().st_size} B)")
        return str(raw_path), str(pgm_path)

    except Exception:
        print("[ERR] Failed to save data:")
        traceback.print_exc()
        return None, None
