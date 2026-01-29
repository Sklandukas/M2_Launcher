def find_focus(axis_service, capture_fn, beam_fn, axis_no, max_position, step_size, stop_event):
    current = 0
    inc_count = 0
    prev_area = None
    inc_start = None

    while current <= max_position and not stop_event.is_set():
        axis_service.go_to(axis_no, current)

        img = capture_fn(current)
        if img is None:
            current += step_size
            continue

        res = beam_fn(img)
        area = res.Dx_mm * res.Dy_mm

        if prev_area is not None and area > prev_area:
            inc_count += 1
            inc_start = inc_start or current
        else:
            inc_count = 0
            inc_start = None

        prev_area = area

        if inc_count >= 5:
            axis_service.home(axis_no)
            return inc_start

        current += step_size

    return None

# def generate_track_by_focus(focus_position, total_length, step_per_mm,
#                             fine_step_mm=1, coarse_step_mm=6):

#     half_points = 40                   
#     window_span_mm = 2 * half_points * fine_step_mm 

#     start_focus = focus_position - half_points * fine_step_mm
#     end_focus = start_focus + window_span_mm

#     if start_focus < 0:
#         end_focus -= start_focus          
#         start_focus = 0
#     if end_focus > total_length:
#         shift = end_focus - total_length
#         start_focus -= shift
#         end_focus = total_length
#         if start_focus < 0:               
#             start_focus = 0

#     start_focus_i = int(round(start_focus))
#     end_focus_i = int(round(end_focus))

#     first_segment = list(range(0, max(0, start_focus_i), int(coarse_step_mm))) if start_focus_i > 0 else []

#     focus_segment = list(range(start_focus_i, end_focus_i + 1, int(fine_step_mm)))

#     third_start = end_focus_i + int(coarse_step_mm)
#     third_segment = list(range(third_start, int(total_length) + 1, int(coarse_step_mm))) if third_start <= total_length else []

#     full_track_mm = []
#     seen = set()
#     for x in first_segment + focus_segment + third_segment:
#         if x not in seen:
#             seen.add(x)
#             full_track_mm.append(x)

#     track = [int(round(x * step_per_mm)) for x in full_track_mm]
#     return track


def generate_track_by_focus (
    focus_position,
    total_length,
    step_per_mm,
    n_points=20,
    focus_window_mm=80,     # ~ kaip anksčiau: 80 mm langas apie fokusą
    n_focus=12              # kiek taškų skirti fokusui (likę dalinami prieš/po)
):
    # apsauga
    total_length = float(total_length)
    if total_length <= 0:
        return [0] * n_points

    # paskirstymas: prieš / fokusas / po
    n_focus = max(2, min(n_focus, n_points))          # bent 2, ne daugiau nei n_points
    n_side_total = n_points - n_focus
    n_pre = n_side_total // 2
    n_post = n_side_total - n_pre

    half_win = focus_window_mm / 2.0
    start_focus = max(0.0, focus_position - half_win)
    end_focus = min(total_length, focus_position + half_win)

    if end_focus - start_focus < 1e-9:
        start_focus = max(0.0, min(total_length, focus_position))
        end_focus = start_focus

    def linspace(a, b, n):
        if n <= 0:
            return []
        if n == 1:
            return [a]
        step = (b - a) / (n - 1)
        return [a + i * step for i in range(n)]

    pre = linspace(0.0, start_focus, n_pre + 1)[:-1] if n_pre > 0 and start_focus > 0 else []
    focus = linspace(start_focus, end_focus, n_focus)
    post = linspace(end_focus, total_length, n_post + 1)[1:] if n_post > 0 and end_focus < total_length else []

    full_mm = pre + focus + post

    mm_int = []
    seen = set()
    for x in full_mm:
        xi = int(round(x))
        xi = max(0, min(int(round(total_length)), xi))
        if xi not in seen:
            seen.add(xi)
            mm_int.append(xi)

    if len(mm_int) < n_points:
        candidates = [int(round(i * total_length / (n_points - 1))) for i in range(n_points)]
        for c in candidates:
            c = max(0, min(int(round(total_length)), c))
            if c not in seen:
                seen.add(c)
                mm_int.append(c)
            if len(mm_int) == n_points:
                break

    if len(mm_int) > n_points:
        idxs = [int(round(i * (len(mm_int) - 1) / (n_points - 1))) for i in range(n_points)]
        mm_int = [mm_int[i] for i in idxs]

    while len(mm_int) < n_points:
        mm_int.append(mm_int[-1])
    mm_int = mm_int[:n_points]

    track = [int(round(x * step_per_mm)) for x in mm_int]
    return track