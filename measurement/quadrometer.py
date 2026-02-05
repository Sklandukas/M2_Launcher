import numpy as np
import math
import matplotlib.pyplot as plt
from scipy.optimize import least_squares


def compute_m2_hyperbola(
    z, dx, dy, wavelength, *,
    metric="d4sigma_diameter",
    z_window=None,          
    max_iter=8000,
    min_points=8,
    return_fig=False,
    units="mm",
    title=None,
    figsize=(12, 7),
    dpi=120,
):

    def snap_m2_to_one(m2: float, *, decimals: int = 3, lo: float = 0.990, hi: float = 1.000) -> float:
        if not np.isfinite(m2):
            return m2
        m2r = round(float(m2), int(decimals))
        return 1.0 if (lo <= m2r <= hi) else float(m2)

    def _model_d4sigma(zv: np.ndarray, d0: float, z0: float, M2: float, lam_mm: float) -> np.ndarray:
        a = (M2 * lam_mm) / (math.pi * d0)
        d2 = (d0 * d0) + 16.0 * (a * a) * (zv - z0) * (zv - z0)
        return np.sqrt(np.maximum(d2, 0.0))

    def fit_m2_from_d4sigma_NOFILTER(z_mm: np.ndarray, d_mm: np.ndarray, lam_mm: float) -> dict:
        zloc = np.asarray(z_mm, dtype=float).ravel()
        dloc = np.asarray(d_mm, dtype=float).ravel()

        if zloc.size < int(min_points):
            return {"ok": 0.0, "M2": float("nan"), "z0": float("nan"), "d0": float("nan"), "rmse_mm": float("nan")}


        dpos = dloc[np.isfinite(dloc) & (dloc > 0)]
        zfin = zloc[np.isfinite(zloc)]
        if dpos.size == 0 or zfin.size == 0:
            return {"ok": 0.0, "M2": float("nan"), "z0": float("nan"), "d0": float("nan"), "rmse_mm": float("nan")}

        d0_0 = float(max(np.min(dpos), 1e-12))
        ok_seed = np.isfinite(zloc) & np.isfinite(dloc) & (dloc > 0)
        i0 = int(np.argmin(np.where(ok_seed, dloc, np.inf)))
        z0_0 = float(zloc[i0]) if np.isfinite(zloc[i0]) else float(np.median(zfin))

        z_seed = zloc[ok_seed]
        d_seed = dloc[ok_seed]
        if z_seed.size < 2:
            z_seed = zfin
            d_seed = dpos if dpos.size == zfin.size else np.full_like(zfin, d0_0)

        left = max(1, int(0.15 * z_seed.size))
        right = max(1, int(0.15 * z_seed.size))
        idxs = np.r_[np.arange(0, left), np.arange(z_seed.size - right, z_seed.size)]
        idxs = np.unique(idxs)
        if idxs.size < 2:
            idxs = np.arange(z_seed.size)

        zz = z_seed[idxs]
        dd = d_seed[idxs]
        denom = np.maximum(np.abs(zz - z0_0), 1e-6)
        slope = float(np.median(dd / denom))
        M2_0 = float(max(slope * math.pi * d0_0 / (4.0 * lam_mm), 0.8))

        p0 = np.array([math.log(d0_0), z0_0, math.log(M2_0)], dtype=float)

        def model_d(zv: np.ndarray, p: np.ndarray) -> np.ndarray:
            d0 = float(np.exp(p[0]))
            z0 = float(p[1])
            M2 = float(np.exp(p[2]))
            return _model_d4sigma(zv, d0, z0, M2, lam_mm)

        def resid(p: np.ndarray) -> np.ndarray:
            dfit = model_d(zloc, p)
            r = dfit - dloc

            bad = (~np.isfinite(zloc)) | (~np.isfinite(dloc)) | (dloc <= 0)
            r = np.where(bad, 0.0, r)

            r = np.where(np.isfinite(r), r, 0.0)
            return r

        d_valid = dloc[np.isfinite(dloc) & (dloc > 0)]
        if d_valid.size == 0:
            scale = 1.0
        else:
            scale = float(np.median(np.abs(d_valid - np.median(d_valid))))
            if not np.isfinite(scale) or scale <= 0:
                scale = 1.0

        res = least_squares(resid, p0, loss="huber", f_scale=scale, max_nfev=int(max_iter))

        d0 = float(np.exp(res.x[0]))
        z0 = float(res.x[1])
        M2 = float(np.exp(res.x[2]))

        valid = np.isfinite(zloc) & np.isfinite(dloc) & (dloc > 0)
        if np.any(valid):
            d_fit = model_d(zloc[valid], res.x)
            rmse = float(np.sqrt(np.mean((d_fit - dloc[valid]) ** 2)))
        else:
            rmse = float("nan")

        return {"ok": 1.0, "M2": M2, "z0": z0, "d0": d0, "rmse_mm": rmse}

    z = np.asarray(z, float).ravel()
    dx = np.asarray(dx, float).ravel()
    dy = np.asarray(dy, float).ravel()

    u = str(units).lower()
    if u == "mm":
        z_mm, dx_mm, dy_mm = z, dx, dy
    elif u == "m":
        z_mm, dx_mm, dy_mm = z * 1e3, dx * 1e3, dy * 1e3
    elif u in ("um", "µm"):
        z_mm, dx_mm, dy_mm = z / 1e3, dx / 1e3, dy / 1e3
    else:
        z_mm, dx_mm, dy_mm = z, dx, dy

    m = str(metric).lower()
    if m in ("d4sigma_radius", "4sigma_radius", "iso11146_radius", "1e2_radius", "fwhm_radius"):
        dx_mm = 2.0 * dx_mm
        dy_mm = 2.0 * dy_mm

    ok_mask = np.ones_like(z_mm, dtype=bool)

    lam_mm = float(wavelength) * 1e3  

    m2x = fit_m2_from_d4sigma_NOFILTER(z_mm, dx_mm, lam_mm)
    m2y = fit_m2_from_d4sigma_NOFILTER(z_mm, dy_mm, lam_mm)
    dstar = np.sqrt(np.maximum(dx_mm, 0.0) * np.maximum(dy_mm, 0.0))  
    m2s = fit_m2_from_d4sigma_NOFILTER(z_mm, dstar, lam_mm)

    m2x["M2"] = snap_m2_to_one(float(m2x["M2"]))
    m2y["M2"] = snap_m2_to_one(float(m2y["M2"]))
    m2s["M2"] = snap_m2_to_one(float(m2s["M2"]))

    results = {"x": m2x, "y": m2y, "star": m2s, "ok_mask": ok_mask}

    if not return_fig:
        return results

    z_fin = z_mm[np.isfinite(z_mm)]
    if z_fin.size == 0:
        z_fit = np.linspace(0.0, 1.0, 500)
    else:
        z_fit = np.linspace(float(np.min(z_fin)), float(np.max(z_fin)), 500)

    X_fit = _model_d4sigma(z_fit, float(m2x["d0"]), float(m2x["z0"]), float(m2x["M2"]), lam_mm)
    Y_fit = _model_d4sigma(z_fit, float(m2y["d0"]), float(m2y["z0"]), float(m2y["M2"]), lam_mm)

    wx_um = 0.5 * dx_mm * 1000.0
    wy_um = 0.5 * dy_mm * 1000.0
    wx_fit_um = 0.5 * X_fit * 1000.0
    wy_fit_um = 0.5 * Y_fit * 1000.0

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    ax.plot(z_mm, wx_um, "s", mfc="none", mec="tab:blue", mew=1.5, label="Waist Width (all)")
    ax.plot(z_mm, wy_um, "s", mfc="none", mec="tab:red",  mew=1.5, label="Waist Height (all)")
    ax.plot(z_fit, wx_fit_um, color="tab:blue", lw=2, label="Fit Width")
    ax.plot(z_fit, wy_fit_um, color="tab:red",  lw=2, label="Fit Height")

    ax.set_xlabel("Distance, mm")
    ax.set_ylabel("Beam Waist Radius, µm")
    if title:
        ax.set_title(title)
    ax.grid(True, alpha=0.25)
    ax.legend(loc="lower left")

    txt = f"M2 x:    {float(m2x['M2']):.2f}\nM2 y:    {float(m2y['M2']):.2f}\nM2*:     {float(m2s['M2']):.2f}"
    ax.text(
        0.05, 0.75, txt, transform=ax.transAxes,
        bbox=dict(facecolor="white", alpha=0.85, boxstyle="round")
    )

    fig.tight_layout()
    return results, fig
