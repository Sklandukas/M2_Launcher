# # exp_diameters/calc.py

# import numpy as np
# from scipy import ndimage as ndi
# from dataclasses import dataclass
# from typing import Dict, Optional, Tuple

# @dataclass
# class BeamAxesResult:
#     Dx_mm: float
#     Dy_mm: float
#     info: Dict[str, float]

# _COORD_CACHE: Dict[Tuple[int, int], Dict[str, np.ndarray]] = {}
# _BORDER_CACHE: Dict[Tuple[int, int, int], np.ndarray] = {}

# def _get_coord_cache(shape: Tuple[int, int]):
#     if shape in _COORD_CACHE:
#         return _COORD_CACHE[shape]
#     h, w = shape
#     y = np.arange(h, dtype=np.float64)
#     x = np.arange(w, dtype=np.float64)
#     Y, X = np.mgrid[0:h, 0:w]
#     Y = Y.astype(np.float64, copy=False)
#     X = X.astype(np.float64, copy=False)
#     _COORD_CACHE[shape] = dict(x=x, y=y, X=X, Y=Y)
#     return _COORD_CACHE[shape]

# def _get_border_mask(shape: Tuple[int, int], border: int) -> np.ndarray:
#     key = (shape[0], shape[1], border)
#     if key in _BORDER_CACHE:
#         return _BORDER_CACHE[key]
#     h, w = shape
#     rim = np.zeros(shape, dtype=bool)
#     rim[:border, :] = True
#     rim[-border:, :] = True
#     rim[:, :border] = True
#     rim[:, -border:] = True
#     _BORDER_CACHE[key] = rim
#     return rim

# def _fast_bg_from_border(img: np.ndarray, border: int = 30) -> float:
#     rim = _get_border_mask(img.shape, border)
#     vals = img[rim].astype(np.float64, copy=False)
#     if vals.size == 0:
#         return float(np.median(img))
#     hi = np.percentile(vals, 90)
#     vals = vals[vals <= hi]
#     return float(np.median(vals))

# def _moments_xy_fast(w_img: np.ndarray,
#                      mask: Optional[np.ndarray],
#                      x: np.ndarray, y: np.ndarray) -> Optional[Dict[str, float]]:
#     if mask is not None:
#         w = np.where(mask, w_img, 0.0)
#     else:
#         w = w_img

#     S0 = float(np.sum(w, dtype=np.float64))
#     if S0 <= 0.0:
#         return None

#     col_sum = np.sum(w, axis=0, dtype=np.float64)
#     row_sum = np.sum(w, axis=1, dtype=np.float64)

#     Sx = float(col_sum @ x)
#     Sy = float(row_sum @ y)

#     x0 = Sx / S0
#     y0 = Sy / S0

#     Sx2 = float(col_sum @ (x * x))
#     Sy2 = float(row_sum @ (y * y))

#     sum_xy = float((w.T @ y) @ x)

#     Ex2 = Sx2 / S0
#     Ey2 = Sy2 / S0
#     Exy = sum_xy / S0

#     Mxx = Ex2 - x0 * x0
#     Myy = Ey2 - y0 * y0
#     Mxy = Exy - x0 * y0

#     return dict(x0=x0, y0=y0, Mxx=Mxx, Myy=Myy, Mxy=Mxy)

# def _ellipse_mask_invC(shape: Tuple[int, int],
#                        x0: float, y0: float,
#                        Mxx: float, Myy: float, Mxy: float,
#                        k: float = 4.0) -> np.ndarray:
#     det = Mxx * Myy - Mxy * Mxy
#     if det <= 1e-16:
#         return np.ones(shape, bool)

#     invC00 =  Myy / det
#     invC01 = -Mxy / det
#     invC11 =  Mxx / det

#     coords = _get_coord_cache(shape)
#     X = coords["X"] - x0
#     Y = coords["Y"] - y0

#     q = invC00 * (X * X) + 2.0 * invC01 * (X * Y) + invC11 * (Y * Y)
#     return q <= (k * k)

# def beam_size_k4_fixed_axes(image_array: np.ndarray,
#                             pixel_size_um: float = 3.75,
#                             k: float = 4.0) -> BeamAxesResult:
#     assert image_array.ndim == 2, "img must be 2D"
#     arr = image_array.astype(np.float64, copy=False)
#     h, w = arr.shape

#     coords = _get_coord_cache((h, w))
#     x = coords["x"]; y = coords["y"]

#     bg = _fast_bg_from_border(arr, border=30)
#     res = arr - bg
#     np.maximum(res, 0, out=res)

#     rim = _get_border_mask((h, w), 30)
#     noise_std = float(np.std(res[rim])) if rim.any() else 0.0
#     thr = max(3.0 * noise_std, 0.01 * float(res.max()))
#     mask = res > thr

#     if not mask.any():
#         return BeamAxesResult(np.nan, np.nan, {"status": "no_signal"})

#     labeled, _ = ndi.label(mask)
#     peak = np.unravel_index(np.argmax(res), res.shape)
#     mask = (labeled == labeled[peak])

#     last_Mxx = last_Myy = None
#     max_iters = 4

#     for _ in range(max_iters):
#         m = _moments_xy_fast(res, mask, x, y)
#         if m is None:
#             return BeamAxesResult(np.nan, np.nan, {"status": "fail_moments"})

#         x0, y0 = m["x0"], m["y0"]
#         Mxx, Myy, Mxy = m["Mxx"], m["Myy"], m["Mxy"]

#         new_mask = _ellipse_mask_invC((h, w), x0, y0, Mxx, Myy, Mxy, k=k)

#         if not new_mask[peak]:
#             new_mask[peak] = True

#         if last_Mxx is not None and abs(Mxx - last_Mxx) < 1e-6 and abs(Myy - last_Myy) < 1e-6:
#             mask = new_mask
#             break

#         last_Mxx, last_Myy = Mxx, Myy
#         mask = new_mask

#     m = _moments_xy_fast(res, mask, x, y)
#     if m is None:
#         return BeamAxesResult(np.nan, np.nan, {"status": "fail_final"})

#     sigma_x = float(np.sqrt(max(m["Mxx"], 0.0)))
#     sigma_y = float(np.sqrt(max(m["Myy"], 0.0)))
#     Dx_mm = 4.0 * sigma_x * (pixel_size_um / 1000.0)
#     Dy_mm = 4.0 * sigma_y * (pixel_size_um / 1000.0)

#     info = dict(
#         status="ok",
#         bg=bg,
#         centroid_x_px=float(m["x0"]),
#         centroid_y_px=float(m["y0"]),
#         sigma_x_px=sigma_x,
#         sigma_y_px=sigma_y,
#         Mxx=float(m["Mxx"]),
#         Myy=float(m["Myy"]),
#         Mxy=float(m["Mxy"]),
#         k=float(k),
#         pixel_um=float(pixel_size_um),
#     )
#     return BeamAxesResult(Dx_mm, Dy_mm, info)


from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np
from scipy import ndimage as ndi


@dataclass
class BeamAxesResult:
    Dx_mm: float
    Dy_mm: float
    info: Dict[str, float]


# --------- caches (greičiau) ----------
_COORD_CACHE: Dict[Tuple[int, int, bool], Dict[str, np.ndarray]] = {}
_BORDER_CACHE: Dict[Tuple[int, int, int], np.ndarray] = {}


def _get_coord_cache(shape: Tuple[int, int], *, pixel_center: bool) -> Dict[str, np.ndarray]:
    key = (shape[0], shape[1], bool(pixel_center))
    if key in _COORD_CACHE:
        return _COORD_CACHE[key]

    h, w = shape
    off = 0.5 if pixel_center else 0.0

    x = np.arange(w, dtype=np.float64) + off
    y = np.arange(h, dtype=np.float64) + off

    Y, X = np.mgrid[0:h, 0:w]
    X = X.astype(np.float64) + off
    Y = Y.astype(np.float64) + off

    out = {"x": x, "y": y, "X": X, "Y": Y}
    _COORD_CACHE[key] = out
    return out


def _get_border_mask(shape: Tuple[int, int], border: int) -> np.ndarray:
    key = (shape[0], shape[1], int(border))
    if key in _BORDER_CACHE:
        return _BORDER_CACHE[key]

    h, w = shape
    rim = np.zeros((h, w), dtype=bool)
    b = max(int(border), 0)
    if b > 0:
        rim[:b, :] = True
        rim[-b:, :] = True
        rim[:, :b] = True
        rim[:, -b:] = True

    _BORDER_CACHE[key] = rim
    return rim


# --------- robust bg plane (kaip tavo gerame kode) ----------
def _huber_weights(r: np.ndarray, delta: float) -> np.ndarray:
    w = np.ones_like(r, dtype=np.float64)
    a = np.abs(r)
    big = a > delta
    w[big] = delta / (a[big] + 1e-12)
    return w


def _robust_plane_from_border(
    img: np.ndarray,
    *,
    border_px: int,
    max_iter: int = 40,
    huber_delta: float = 4.0,
    tol: float = 1e-6,
    pixel_center: bool = True,
) -> Tuple[np.ndarray, Dict[str, float]]:
    h, w = img.shape
    rim = _get_border_mask((h, w), border_px)
    yy, xx = np.nonzero(rim)

    if xx.size < 3:
        med = float(np.median(img))
        plane = np.full((h, w), med, dtype=np.float64)
        return plane, {"bg_mode": 0.0, "bg_a": 0.0, "bg_b": 0.0, "bg_c": med, "bg_slope": 0.0}

    z = img[rim].astype(np.float64, copy=False)

    off = 0.5 if pixel_center else 0.0
    A = np.c_[xx.astype(np.float64) + off, yy.astype(np.float64) + off, np.ones_like(xx, dtype=np.float64)]

    wts = np.ones_like(z, dtype=np.float64)
    coeff = np.array([0.0, 0.0, float(np.median(z))], dtype=np.float64)

    for _ in range(int(max_iter)):
        Aw = A * wts[:, None]
        zw = z * wts
        coeff_new, *_ = np.linalg.lstsq(Aw, zw, rcond=None)

        resid = z - (A @ coeff_new)
        wts_new = _huber_weights(resid, float(huber_delta))

        if np.max(np.abs(wts_new - wts)) < tol and np.max(np.abs(coeff_new - coeff)) < tol:
            coeff = coeff_new
            wts = wts_new
            break

        coeff = coeff_new
        wts = wts_new

    a, b, c = float(coeff[0]), float(coeff[1]), float(coeff[2])
    coords = _get_coord_cache((h, w), pixel_center=pixel_center)
    plane = a * coords["X"] + b * coords["Y"] + c
    slope = float(np.hypot(a, b))
    return plane, {"bg_mode": 1.0, "bg_a": a, "bg_b": b, "bg_c": c, "bg_slope": slope}


# --------- moments + ellipse mask (kaip vendorlike) ----------
# def _moments_xy(
#     img_pos: np.ndarray,
#     mask: Optional[np.ndarray],
#     x: np.ndarray,
#     y: np.ndarray,
# ) -> Optional[Dict[str, float]]:
#     w = img_pos if mask is None else np.where(mask, img_pos, 0.0)

#     S0 = float(np.sum(w, dtype=np.float64))
#     if not np.isfinite(S0) or S0 <= 0.0:
#         return None

#     col_sum = np.sum(w, axis=0, dtype=np.float64)
#     row_sum = np.sum(w, axis=1, dtype=np.float64)

#     x0 = float((col_sum @ x) / S0)
#     y0 = float((row_sum @ y) / S0)

#     Ex2 = float((col_sum @ (x * x)) / S0)
#     Ey2 = float((row_sum @ (y * y)) / S0)
#     Exy = float(np.sum(w * (y[:, None] * x[None, :]), dtype=np.float64) / S0)

#     Mxx = Ex2 - x0 * x0
#     Myy = Ey2 - y0 * y0
#     Mxy = Exy - x0 * y0

#     if not (np.isfinite(Mxx) and np.isfinite(Myy) and np.isfinite(Mxy)):
#         return None

#     if Mxx < 0 and Mxx > -1e-9:
#         Mxx = 0.0
#     if Myy < 0 and Myy > -1e-9:
#         Myy = 0.0

#     return {"S0": S0, "x0": x0, "y0": y0, "Mxx": float(Mxx), "Myy": float(Myy), "Mxy": float(Mxy)}

def _moments_xy(img_pos: np.ndarray, mask: Optional[np.ndarray], x: np.ndarray, y: np.ndarray) -> Optional[Dict[str, float]]:
    w = img_pos if mask is None else np.where(mask, img_pos, 0.0)

    S0 = float(np.sum(w, dtype=np.float64))
    if not np.isfinite(S0) or S0 <= 0.0:
        return None

    col_sum = np.sum(w, axis=0, dtype=np.float64)
    row_sum = np.sum(w, axis=1, dtype=np.float64)

    x0 = float((col_sum @ x) / S0)
    y0 = float((row_sum @ y) / S0)

    Ex2 = float((col_sum @ (x * x)) / S0)
    Ey2 = float((row_sum @ (y * y)) / S0)
    Exy = float(np.sum(w * (y[:, None] * x[None, :]), dtype=np.float64) / S0)

    Mxx = Ex2 - x0 * x0
    Myy = Ey2 - y0 * y0
    Mxy = Exy - x0 * y0

    if not (np.isfinite(Mxx) and np.isfinite(Myy) and np.isfinite(Mxy)):
        return None

    if Mxx < 0 and Mxx > -1e-9:
        Mxx = 0.0
    if Myy < 0 and Myy > -1e-9:
        Myy = 0.0

    return {"S0": S0, "x0": x0, "y0": y0, "Mxx": float(Mxx), "Myy": float(Myy), "Mxy": float(Mxy)}


def _ellipse_mask_from_cov_inv(
    shape: Tuple[int, int],
    x0: float,
    y0: float,
    Mxx: float,
    Myy: float,
    Mxy: float,
    k: float,
    *,
    pixel_center: bool,
) -> Optional[np.ndarray]:
    det = Mxx * Myy - Mxy * Mxy
    if (not np.isfinite(det)) or det <= 1e-16:
        return None

    invC00 = Myy / det
    invC01 = -Mxy / det
    invC11 = Mxx / det

    coords = _get_coord_cache(shape, pixel_center=pixel_center)
    X = coords["X"] - float(x0)
    Y = coords["Y"] - float(y0)

    q = invC00 * (X * X) + 2.0 * invC01 * (X * Y) + invC11 * (Y * Y)
    return q <= float(k * k)


def _main_component_mask(img: np.ndarray, mask: np.ndarray) -> np.ndarray:
    labeled, n = ndi.label(mask)
    if n == 0:
        return mask
    peak = np.unravel_index(int(np.argmax(img)), img.shape)
    lab = int(labeled[peak])
    if lab == 0:
        out = np.zeros_like(mask, dtype=bool)
        out[peak] = True
        return out
    return labeled == lab

def beam_size_k4_fixed_axes(
    image_array: np.ndarray,
    pixel_size_um: float = 3.75,
    k: float = 4.0
) -> BeamAxesResult:

    assert image_array.ndim == 2, "img must be 2D"
    arr = np.asarray(image_array, dtype=np.float64)
    h, w = arr.shape

    border_px = 30
    border_frac_min = 0.08
    max_iters = 40
    rel_tol = 1e-7
    pixel_center = True
    ignore_saturated = False   

    border_px = max(int(border_px), int(border_frac_min * min(h, w)))

    coords = _get_coord_cache((h, w), pixel_center=pixel_center)
    x = coords["x"]
    y = coords["y"]

    rim = _get_border_mask((h, w), border_px)

    # BG plane (identika "geram" kodui)
    plane, bg_info = _robust_plane_from_border(arr, border_px=border_px, pixel_center=pixel_center)
    res0 = arr - plane

    # weights
    wts = np.maximum(res0, 0.0)

    # ignore saturated (jei reiks)
    if ignore_saturated:
        maxv = float(np.nanmax(arr))
        sat = arr >= maxv
        if sat.any():
            wts = np.where(sat, 0.0, wts)

    peak = np.unravel_index(int(np.argmax(wts)), wts.shape)
    peak_val = float(wts[peak])
    if not np.isfinite(peak_val) or peak_val <= 0.0:
        return BeamAxesResult(
            np.nan, np.nan,
            {"status": 0.0, "reason": 1.0, "peak_val": peak_val, "border_px": float(border_px), **bg_info}
        )

    init = wts > 0.0
    init = _main_component_mask(wts, init)
    init = ndi.binary_closing(init, structure=np.ones((3, 3), dtype=bool))
    init[peak] = True

    mask = init
    last = None
    iters = 0

    for it in range(int(max_iters)):
        iters = it + 1
        m = _moments_xy(wts, mask, x, y)
        if m is None:
            return BeamAxesResult(np.nan, np.nan, {"status": 0.0, "reason": 2.0, "border_px": float(border_px), **bg_info})

        x0, y0, Mxx, Myy, Mxy = m["x0"], m["y0"], m["Mxx"], m["Myy"], m["Mxy"]
        new_mask = _ellipse_mask_from_cov_inv((h, w), x0, y0, Mxx, Myy, Mxy, float(k), pixel_center=pixel_center)
        if new_mask is None:
            new_mask = np.zeros((h, w), dtype=bool)
        new_mask[peak] = True

        cur = np.array([Mxx, Myy, Mxy, x0, y0], dtype=np.float64)
        if last is not None:
            denom = np.maximum(np.abs(last), 1e-12)
            rel = float(np.max(np.abs(cur - last) / denom))
            if rel < float(rel_tol):
                mask = new_mask
                break
        last = cur
        mask = new_mask

    m = _moments_xy(wts, mask, x, y)
    if m is None:
        return BeamAxesResult(np.nan, np.nan, {"status": 0.0, "reason": 3.0, "border_px": float(border_px), **bg_info})

    px_mm = float(pixel_size_um) / 1000.0
    Dx_mm = 4.0 * np.sqrt(max(float(m["Mxx"]), 0.0)) * px_mm
    Dy_mm = 4.0 * np.sqrt(max(float(m["Myy"]), 0.0)) * px_mm

    print(f"Dx_mm: {Dx_mm} Dy_mm: {Dy_mm}")

    C_px = np.array([[float(m["Mxx"]), float(m["Mxy"])],
                     [float(m["Mxy"]), float(m["Myy"])]], dtype=np.float64)
    S = np.diag([px_mm, px_mm])
    C_mm = S @ C_px @ S

    info = {
        "status": 1.0,
        "iterations": float(iters),
        "k": float(k),
        "border_px": float(border_px),
        "roi_fraction": float(np.mean(mask)),
        "total_power": float(m["S0"]),
        "C00": float(C_mm[0, 0]),
        "C01": float(C_mm[0, 1]),
        "C11": float(C_mm[1, 1]),
        "peak_val": float(peak_val),
        **bg_info,
    }
    return BeamAxesResult(float(Dx_mm), float(Dy_mm), info)

@dataclass
class BeamISO11146Result:
    Dx_mm: float
    Dy_mm: float
    D_major_mm: float
    D_minor_mm: float
    theta_rad: float
    theta_deg: float
    info: Dict[str, float]


_COORD_CACHE: Dict[Tuple[int, int, bool], Dict[str, np.ndarray]] = {}
_BORDER_CACHE: Dict[Tuple[int, int, int], np.ndarray] = {}

def _get_coord_cache(shape: Tuple[int, int], pixel_center: bool) -> Dict[str, np.ndarray]:
    key = (shape[0], shape[1], bool(pixel_center))
    if key in _COORD_CACHE:
        return _COORD_CACHE[key]

    h, w = shape
    off = 0.5 if pixel_center else 0.0
    x = np.arange(w, dtype=np.float64) + off
    y = np.arange(h, dtype=np.float64) + off

    Y, X = np.mgrid[0:h, 0:w]
    X = X.astype(np.float64) + off
    Y = Y.astype(np.float64) + off

    out = {"x": x, "y": y, "X": X, "Y": Y}
    _COORD_CACHE[key] = out
    return out



def _estimate_noise_floor_from_border(res0: np.ndarray, rim: np.ndarray, *, nsigma: float) -> Tuple[float, float, float]:
    b = res0[rim].astype(np.float64, copy=False) if rim.any() else res0.ravel().astype(np.float64, copy=False)
    med = float(np.median(b))
    mad = float(np.median(np.abs(b - med)))
    sigma = 1.4826 * mad if mad > 0 else float(np.std(b))
    floor = med + float(nsigma) * sigma
    return med, sigma, float(floor)

def _bg_constant_from_border(img: np.ndarray, *, border_px: int, bg_stat: str = "median") -> Tuple[float, Dict[str, float]]:
    rim = _get_border_mask(img.shape, border_px)
    border = img[rim] if rim.any() else img.ravel()
    bg = float(np.median(border)) if bg_stat == "median" else float(np.mean(border))
    return bg, {"bg_mode": 2.0, "bg_const": bg}

def _principal_axes_from_cov(C: np.ndarray) -> Tuple[float, float, float]:
    vals, vecs = np.linalg.eigh(C)
    if not np.isfinite(vals).all() or not np.isfinite(vecs).all():
        return (np.nan, np.nan, np.nan)

    vmin = max(float(vals[0]), 0.0)
    vmax = max(float(vals[1]), 0.0)

    s_minor = float(np.sqrt(vmin))
    s_major = float(np.sqrt(vmax))

    vx, vy = float(vecs[0, 1]), float(vecs[1, 1])
    theta = float(np.arctan2(vy, vx))
    if theta > np.pi / 2:
        theta -= np.pi
    if theta < -np.pi / 2:
        theta += np.pi

    return s_major, s_minor, theta


def beam_size_iso11146_vendorlike(
    image_array: np.ndarray,
    *,
    pixel_size_x_um: float,
    pixel_size_y_um: float,
    k: float,
    border_px: int,
    border_frac_min: float,
    max_iters: int,
    rel_tol: float,
    pixel_center: bool,
    bg_mode: str,
    bg_stat: str,
    noise_nsigma: Optional[float],
    ignore_saturated: bool,
    file_path: Optional[str] = None,
) -> BeamISO11146Result:


    arr = np.asarray(image_array, dtype=np.float64)
    h, w = arr.shape

    border_px = max(int(border_px), int(border_frac_min * min(h, w)))
    coords = _get_coord_cache((h, w), pixel_center=pixel_center)
    x = coords["x"]
    y = coords["y"]
    rim = _get_border_mask((h, w), border_px)

    # BG
    bg_info: Dict[str, float]
    if bg_mode == "plane":
        plane, bg_info = _robust_plane_from_border(arr, border_px=border_px, pixel_center=pixel_center)
        res0 = arr - plane
    elif bg_mode == "const":
        bg, bg_info = _bg_constant_from_border(arr, border_px=border_px, bg_stat=bg_stat)
        bg_info["border_px"] = float(border_px)
        res0 = arr - bg
    else:
        raise ValueError("bg_mode must be 'plane' or 'const'")

    # Weights (kaip sweep'e)
    if noise_nsigma is None:
        wts = np.maximum(res0, 0.0)
        b_med, b_sig, floor = float("nan"), float("nan"), 0.0
    else:
        b_med, b_sig, floor = _estimate_noise_floor_from_border(res0, rim, nsigma=float(noise_nsigma))
        wts = np.maximum(res0 - floor, 0.0)

    # Ignore saturated (kaip sweep'e)
    if ignore_saturated:
        maxv = float(np.nanmax(arr))
        sat = arr >= maxv
        if sat.any():
            wts = np.where(sat, 0.0, wts)

    peak = np.unravel_index(int(np.argmax(wts)), wts.shape)
    peak_val = float(wts[peak])
    if not np.isfinite(peak_val) or peak_val <= 0.0:
        return BeamISO11146Result(
            np.nan, np.nan, np.nan, np.nan, np.nan, np.nan,
            {"status": 0.0, "reason": 1.0, "peak_val": peak_val, "border_px": float(border_px),
             "noise_floor": float(floor), "noise_nsigma": float(noise_nsigma) if noise_nsigma is not None else float("nan"),
             **bg_info},
        )

    init = wts > 0.0
    init = _main_component_mask(wts, init)
    init = ndi.binary_closing(init, structure=np.ones((3, 3), dtype=bool))
    init[peak] = True

    mask = init
    last = None
    iters = 0

    for it in range(int(max_iters)):
        iters = it + 1
        m = _moments_xy(wts, mask, x, y)
        if m is None:
            return BeamISO11146Result(np.nan, np.nan, np.nan, np.nan, np.nan, np.nan,
                                      {"status": 0.0, "reason": 2.0, "noise_floor": float(floor), **bg_info})

        x0, y0, Mxx, Myy, Mxy = m["x0"], m["y0"], m["Mxx"], m["Myy"], m["Mxy"]
        new_mask = _ellipse_mask_from_cov_inv((h, w), x0, y0, Mxx, Myy, Mxy, float(k), pixel_center=pixel_center)
        if new_mask is None:
            new_mask = np.zeros((h, w), dtype=bool)
        new_mask[peak] = True

        cur = np.array([Mxx, Myy, Mxy, x0, y0], dtype=np.float64)
        if last is not None:
            denom = np.maximum(np.abs(last), 1e-12)
            rel = float(np.max(np.abs(cur - last) / denom))
            if rel < float(rel_tol):
                mask = new_mask
                break
        last = cur
        mask = new_mask

    m = _moments_xy(wts, mask, x, y)
    if m is None:
        return BeamISO11146Result(np.nan, np.nan, np.nan, np.nan, np.nan, np.nan,
                                  {"status": 0.0, "reason": 3.0, "noise_floor": float(floor), **bg_info})

    px_x_mm = float(pixel_size_x_um) / 1000.0
    px_y_mm = float(pixel_size_y_um) / 1000.0

    Dx_mm = 4.0 * np.sqrt(max(m["Mxx"], 0.0)) * px_x_mm
    Dy_mm = 4.0 * np.sqrt(max(m["Myy"], 0.0)) * px_y_mm

    C_px = np.array([[m["Mxx"], m["Mxy"]], [m["Mxy"], m["Myy"]]], dtype=np.float64)
    S = np.diag([px_x_mm, px_y_mm])
    C_mm = S @ C_px @ S

    s_major_mm, s_minor_mm, theta = _principal_axes_from_cov(C_mm)
    D_major_mm = 4.0 * s_major_mm
    D_minor_mm = 4.0 * s_minor_mm
    fname = os.path.basename(file_path) if file_path else ""
    print(f"{fname}  Dx_mm: {Dx_mm}  Dy_mm: {Dy_mm}  D_minor_mm: {D_minor_mm}  D_major_mm: {D_major_mm}")


    info: Dict[str, float] = {
        "status": 1.0,
        "iterations": float(iters),
        "k": float(k),
        "border_px": float(border_px),
        "roi_fraction": float(np.mean(mask)),
        "total_power": float(m["S0"]),
        "C00": float(C_mm[0, 0]),
        "C01": float(C_mm[0, 1]),
        "C11": float(C_mm[1, 1]),
        "noise_floor": float(floor),
        "noise_nsigma": float(noise_nsigma) if noise_nsigma is not None else float("nan"),
        "ignore_saturated": 1.0 if ignore_saturated else 0.0,
        "peak_val": float(peak_val),
        **bg_info,
    }

    return BeamISO11146Result(
        Dx_mm=float(Dx_mm),
        Dy_mm=float(Dy_mm),
        D_major_mm=float(D_major_mm),
        D_minor_mm=float(D_minor_mm),
        theta_rad=float(theta),
        theta_deg=float(np.degrees(theta)) if np.isfinite(theta) else float("nan"),
        info=info,
    )
