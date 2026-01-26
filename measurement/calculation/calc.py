# exp_diameters/calc.py

import numpy as np
from scipy import ndimage as ndi
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

@dataclass
class BeamAxesResult:
    Dx_mm: float
    Dy_mm: float
    info: Dict[str, float]

_COORD_CACHE: Dict[Tuple[int, int], Dict[str, np.ndarray]] = {}
_BORDER_CACHE: Dict[Tuple[int, int, int], np.ndarray] = {}

def _get_coord_cache(shape: Tuple[int, int]):
    if shape in _COORD_CACHE:
        return _COORD_CACHE[shape]
    h, w = shape
    y = np.arange(h, dtype=np.float64)
    x = np.arange(w, dtype=np.float64)
    Y, X = np.mgrid[0:h, 0:w]
    Y = Y.astype(np.float64, copy=False)
    X = X.astype(np.float64, copy=False)
    _COORD_CACHE[shape] = dict(x=x, y=y, X=X, Y=Y)
    return _COORD_CACHE[shape]

def _get_border_mask(shape: Tuple[int, int], border: int) -> np.ndarray:
    key = (shape[0], shape[1], border)
    if key in _BORDER_CACHE:
        return _BORDER_CACHE[key]
    h, w = shape
    rim = np.zeros(shape, dtype=bool)
    rim[:border, :] = True
    rim[-border:, :] = True
    rim[:, :border] = True
    rim[:, -border:] = True
    _BORDER_CACHE[key] = rim
    return rim

def _fast_bg_from_border(img: np.ndarray, border: int = 30) -> float:
    rim = _get_border_mask(img.shape, border)
    vals = img[rim].astype(np.float64, copy=False)
    if vals.size == 0:
        return float(np.median(img))
    hi = np.percentile(vals, 90)
    vals = vals[vals <= hi]
    return float(np.median(vals))

def _moments_xy_fast(w_img: np.ndarray,
                     mask: Optional[np.ndarray],
                     x: np.ndarray, y: np.ndarray) -> Optional[Dict[str, float]]:
    if mask is not None:
        w = np.where(mask, w_img, 0.0)
    else:
        w = w_img

    S0 = float(np.sum(w, dtype=np.float64))
    if S0 <= 0.0:
        return None

    col_sum = np.sum(w, axis=0, dtype=np.float64)
    row_sum = np.sum(w, axis=1, dtype=np.float64)

    Sx = float(col_sum @ x)
    Sy = float(row_sum @ y)

    x0 = Sx / S0
    y0 = Sy / S0

    Sx2 = float(col_sum @ (x * x))
    Sy2 = float(row_sum @ (y * y))

    sum_xy = float((w.T @ y) @ x)

    Ex2 = Sx2 / S0
    Ey2 = Sy2 / S0
    Exy = sum_xy / S0

    Mxx = Ex2 - x0 * x0
    Myy = Ey2 - y0 * y0
    Mxy = Exy - x0 * y0

    return dict(x0=x0, y0=y0, Mxx=Mxx, Myy=Myy, Mxy=Mxy)

def _ellipse_mask_invC(shape: Tuple[int, int],
                       x0: float, y0: float,
                       Mxx: float, Myy: float, Mxy: float,
                       k: float = 4.0) -> np.ndarray:
    det = Mxx * Myy - Mxy * Mxy
    if det <= 1e-16:
        return np.ones(shape, bool)

    invC00 =  Myy / det
    invC01 = -Mxy / det
    invC11 =  Mxx / det

    coords = _get_coord_cache(shape)
    X = coords["X"] - x0
    Y = coords["Y"] - y0

    q = invC00 * (X * X) + 2.0 * invC01 * (X * Y) + invC11 * (Y * Y)
    return q <= (k * k)

def beam_size_k4_fixed_axes(image_array: np.ndarray,
                            pixel_size_um: float = 3.75,
                            k: float = 4.0) -> BeamAxesResult:
    assert image_array.ndim == 2, "img must be 2D"
    arr = image_array.astype(np.float64, copy=False)
    h, w = arr.shape

    coords = _get_coord_cache((h, w))
    x = coords["x"]; y = coords["y"]

    bg = _fast_bg_from_border(arr, border=30)
    res = arr - bg
    np.maximum(res, 0, out=res)

    rim = _get_border_mask((h, w), 30)
    noise_std = float(np.std(res[rim])) if rim.any() else 0.0
    thr = max(3.0 * noise_std, 0.01 * float(res.max()))
    mask = res > thr

    if not mask.any():
        return BeamAxesResult(np.nan, np.nan, {"status": "no_signal"})

    labeled, _ = ndi.label(mask)
    peak = np.unravel_index(np.argmax(res), res.shape)
    mask = (labeled == labeled[peak])

    last_Mxx = last_Myy = None
    max_iters = 4

    for _ in range(max_iters):
        m = _moments_xy_fast(res, mask, x, y)
        if m is None:
            return BeamAxesResult(np.nan, np.nan, {"status": "fail_moments"})

        x0, y0 = m["x0"], m["y0"]
        Mxx, Myy, Mxy = m["Mxx"], m["Myy"], m["Mxy"]

        new_mask = _ellipse_mask_invC((h, w), x0, y0, Mxx, Myy, Mxy, k=k)

        if not new_mask[peak]:
            new_mask[peak] = True

        if last_Mxx is not None and abs(Mxx - last_Mxx) < 1e-6 and abs(Myy - last_Myy) < 1e-6:
            mask = new_mask
            break

        last_Mxx, last_Myy = Mxx, Myy
        mask = new_mask

    m = _moments_xy_fast(res, mask, x, y)
    if m is None:
        return BeamAxesResult(np.nan, np.nan, {"status": "fail_final"})

    sigma_x = float(np.sqrt(max(m["Mxx"], 0.0)))
    sigma_y = float(np.sqrt(max(m["Myy"], 0.0)))
    Dx_mm = 4.0 * sigma_x * (pixel_size_um / 1000.0)
    Dy_mm = 4.0 * sigma_y * (pixel_size_um / 1000.0)

    info = dict(
        status="ok",
        bg=bg,
        centroid_x_px=float(m["x0"]),
        centroid_y_px=float(m["y0"]),
        sigma_x_px=sigma_x,
        sigma_y_px=sigma_y,
        Mxx=float(m["Mxx"]),
        Myy=float(m["Myy"]),
        Mxy=float(m["Mxy"]),
        k=float(k),
        pixel_um=float(pixel_size_um),
    )
    return BeamAxesResult(Dx_mm, Dy_mm, info)
