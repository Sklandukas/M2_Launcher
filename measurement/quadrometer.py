import numpy as np
import math
import matplotlib.ticker as ticker
import matplotlib.pyplot as plt

def compute_m2_hyperbola(
    z, dx, dy, wavelength, *,
    metric="1e2_diameter",      
    z_window=None,              
    use_huber=True,             
    max_iter=50,                
    reject_outliers=False,      
    reject_k=3.0,               
    max_passes=3,               
    min_points=6,               
    return_fig=False, units="mm", title=None, figsize=(12,7), dpi=120
):

    def _to_1e2_diameter(d, metric):
        d = np.asarray(d, float)
        m = str(metric).lower()
        if m == "1e2_diameter": return d
        if m == "1e2_radius":   return 2.0*d
        k = 2.0/np.sqrt(2.0*np.log(2.0))
        if m == "fwhm_diameter": return k*d
        if m == "fwhm_radius":   return k*(2.0*d)
        raise ValueError("metric must be: 1e2_diameter | 1e2_radius | fwhm_diameter | fwhm_radius")

    def _huber_weights(r, delta):
        w = np.ones_like(r)
        big = np.abs(r) > delta
        w[big] = delta / (np.abs(r[big]) + 1e-12)
        return w

    def _mad(x):
        med = np.median(x)
        return np.median(np.abs(x - med)) + 1e-12

    def _init_from_parabola(zz, ww):
        i0 = int(np.argmin(ww))
        z0 = float(zz[i0])
        w0_min = float(ww[i0])

        t = (zz - z0)**2
        y = ww*ww
        A = np.column_stack([t, np.ones_like(t)])
        coef, *_ = np.linalg.lstsq(A, y, rcond=None)   
        a_lin = float(coef[0])     
        b_lin = float(coef[1])     

        a_lin = max(a_lin, 1e-18)
        b_lin = max(b_lin, max(1e-18, 0.5*w0_min*w0_min))

        theta = float(np.sqrt(a_lin))
        w0    = float(np.sqrt(b_lin))
        return w0, theta, z0

    def _fit_gn(zz, ww):
        w0, theta, z0 = _init_from_parabola(zz, ww)
        if not (np.isfinite(w0) and np.isfinite(theta) and np.isfinite(z0)):
            return (np.nan, np.nan, np.nan, None)

        for _ in range(max_iter):
            t = zz - z0
            model = np.sqrt(np.maximum(w0*w0 + (theta*theta)*(t*t), 1e-24))
            r = ww - model

            if use_huber:
                delta = 1.345 * _mad(r)
                wgt = _huber_weights(r, delta)
            else:
                wgt = np.ones_like(r)

            J = np.column_stack([
                w0 / model,                 
                (theta * t*t) / model,      
                -(theta*theta * t) / model  
            ])
            W = np.sqrt(wgt)[:, None]
            JW = J * W
            rW = (r[:, None]) * W

            A = JW.T @ JW
            bvec = JW.T @ rW

            lam_reg = 1e-12 * (np.trace(A) + 1e-24)
            A = A + lam_reg * np.eye(3)

            try:
                dp = np.linalg.solve(A, bvec).ravel()
            except np.linalg.LinAlgError:
                break

            w0   += dp[0]
            theta += dp[1]
            z0   += dp[2]
            w0    = float(max(w0, 1e-12))
            theta = float(max(theta, 1e-12))

            if np.linalg.norm(dp) < 1e-12:
                break

        t = zz - z0
        model = np.sqrt(np.maximum(w0*w0 + (theta*theta)*(t*t), 1e-24))
        r = ww - model
        return (float(w0), float(theta), float(z0), r)

    def _fit_one_axis(z_full, d_full, wavelength, z_window):
        d_1e2 = _to_1e2_diameter(d_full, metric)
        w_full = 0.5 * d_1e2

        z_full = np.asarray(z_full, float).ravel()
        w_full = np.asarray(w_full, float).ravel()
        m = np.isfinite(z_full) & np.isfinite(w_full)
        z_full = z_full[m]; w_full = w_full[m]
        idx = np.argsort(z_full)
        z_full = z_full[idx]; w_full = w_full[idx]

        if z_window is not None:
            zlo, zhi = map(float, z_window)
            base_mask = (z_full >= zlo) & (z_full <= zhi)
            if base_mask.sum() >= 5:
                z_use = z_full[base_mask]; w_use = w_full[base_mask]
            else:
                z_use = z_full; w_use = w_full
                base_mask = np.ones_like(z_full, dtype=bool)
        else:
            z_use = z_full; w_use = w_full
            base_mask = np.ones_like(z_full, dtype=bool)

        if z_use.size < 3:
            return dict(M2=np.nan, w0=np.nan, z0=np.nan, theta=np.nan,
                        z_used=z_use, w_used=w_use, z_all=z_full, w_all=w_full,
                        mask_used=np.zeros_like(z_full, bool),
                        mask_outliers=np.zeros_like(z_full, bool),
                        coeffs=(np.nan,)*3)

        keep = np.ones_like(z_use, dtype=bool)
        passes = 1 if not reject_outliers else max_passes
        for _ in range(passes):
            if keep.sum() < 3:
                break
            w0, theta, z0, r = _fit_gn(z_use[keep], w_use[keep])
            if not np.isfinite(w0):
                break
            if not reject_outliers:
                break
            mad = _mad(r)
            bad_local = np.abs(r) > (reject_k * mad)
            if not np.any(bad_local):
                break
            pos = np.where(keep)[0]
            keep[pos[bad_local]] = False
            if keep.sum() < max(min_points, 3):
                break

        if keep.sum() >= 3:
            w0, theta, z0, r = _fit_gn(z_use[keep], w_use[keep])
            M2 = (np.pi * w0 / float(wavelength)) * theta
            a = theta*theta
            b = -2.0*a*z0
            c = w0*w0 + a*z0*z0
        else:
            w0 = theta = z0 = M2 = a = b = c = np.nan

        mask_used_all = np.zeros_like(z_full, dtype=bool)
        mask_out_all  = np.zeros_like(z_full, dtype=bool)
        mask_used_all[np.where(base_mask)[0]] = False
        mask_out_all[np.where(base_mask)[0]]  = False
        if z_use.size > 0:
            mask_used_all[np.where(base_mask)[0]] = keep
            mask_out_all[np.where(base_mask)[0]]  = ~keep

        return dict(M2=float(M2), w0=float(w0), z0=float(z0), theta=float(theta),
                    z_used=z_use[keep] if np.any(keep) else z_use,
                    w_used=w_use[keep] if np.any(keep) else w_use,
                    z_all=z_full, w_all=w_full,
                    mask_used=mask_used_all, mask_outliers=mask_out_all,
                    coeffs=(float(a), float(b), float(c)))

    z = np.asarray(z, float).ravel()
    dx = np.asarray(dx, float).ravel()
    dy = np.asarray(dy, float).ravel()
    wavelength = float(wavelength)

    res_x = _fit_one_axis(z, dx, wavelength, z_window)
    res_y = _fit_one_axis(z, dy, wavelength, z_window)
    results = {"x": res_x, "y": res_y}

    if not return_fig:
        return results

    def _to_mm(v):
        u = str(units).lower()
        if u == "m":  return v
        if u == "mm": return v
        if u in ("um","µm"): return v
        return v

    def _to_um(v):
        u = str(units).lower()
        if u == "m":  return v*1e6
        if u == "mm": return v*1e3
        if u in ("um","µm"): return v
        return v*1e3

    wx_all = 0.5 * _to_1e2_diameter(dx, metric)
    wy_all = 0.5 * _to_1e2_diameter(dy, metric)

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)

    zx_all = results["x"]["z_all"]; use_x = results["x"]["mask_used"]; out_x = results["x"]["mask_outliers"]
    zy_all = results["y"]["z_all"]; use_y = results["y"]["mask_used"]; out_y = results["y"]["mask_outliers"]

    ax.plot(_to_mm(zx_all) * 1000, _to_um(wx_all),
            's', mfc='none', mec='tab:blue', label='Width')
    ax.plot(_to_mm(zy_all) * 1000, _to_um(wy_all),
            's', mfc='none', mec='tab:red', label='Height')
        
    aX, bX, cX = results["x"]["coeffs"]
    aY, bY, cY = results["y"]["coeffs"]

    if np.isfinite(aX):
        z_fit = np.linspace(zx_all.min(), zx_all.max(), 500)
        wx_fit = np.sqrt(np.maximum(aX*z_fit**2 + bX*z_fit + cX, 0.0))
        ax.plot(_to_mm(z_fit) * 1000, _to_um(wx_fit),
                color='tab:blue', lw=2, label='Fit Width')
    if np.isfinite(aY):
        z_fit = np.linspace(zy_all.min(), zy_all.max(), 500)
        wy_fit = np.sqrt(np.maximum(aY*z_fit**2 + bY*z_fit + cY, 0.0))
        ax.plot(_to_mm(z_fit) * 1000, _to_um(wy_fit),
                color='tab:red', lw=2, label='Fit Height')
        
    ax.set_xlabel(f"Distance, {units}")
    ax.set_ylabel("Beam Waist Radius, µm")
    if title:
        ax.set_title(title)
    ax.grid(True, alpha=0.3)
    ax.legend(loc='best')

    ax.xaxis.set_major_locator(ticker.MultipleLocator(10))  
    ax.set_xlim(left=0)

    u = str(units).lower()
    if u == "mm":
        ax.yaxis.set_major_locator(ticker.MultipleLocator(0.05))
        ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: f"{y*1000:.0f}"))
    elif u == "m":
        ax.yaxis.set_major_locator(ticker.MultipleLocator(5e-5))
        ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: f"{y*1e6:.0f}"))
    elif u in ("um", "µm"):
        ax.yaxis.set_major_locator(ticker.MultipleLocator(50))
        ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: f"{y:.0f}"))

    if title: ax.set_title(title)
    ax.grid(True, alpha=0.3)
    ax.legend(loc='lower right', framealpha=0.9)

    M2x, M2y = results["x"]["M2"], results["y"]["M2"]
    M2star = np.sqrt(M2x*M2y) if np.isfinite(M2x) and np.isfinite(M2y) else np.nan
    txt = (f"M2 x:    {M2x:.2f}\n"
           f"M2 y:    {M2y:.2f}\n"
           f"M2*:     {M2star:.2f}")
    ax.text(0.02, 0.98, txt, transform=ax.transAxes, va='top',
            bbox=dict(facecolor='white', alpha=0.85, boxstyle='round'), fontsize=12)

    fig.tight_layout()
    return results, fig
