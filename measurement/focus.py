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

def generate_track_by_focus(focus_position, total_length, step_per_mm,
                            fine_step_mm=1, coarse_step_mm=6):

    half_points = 40                   
    window_span_mm = 2 * half_points * fine_step_mm 

    start_focus = focus_position - half_points * fine_step_mm
    end_focus = start_focus + window_span_mm

    if start_focus < 0:
        end_focus -= start_focus          
        start_focus = 0
    if end_focus > total_length:
        shift = end_focus - total_length
        start_focus -= shift
        end_focus = total_length
        if start_focus < 0:               
            start_focus = 0

    start_focus_i = int(round(start_focus))
    end_focus_i = int(round(end_focus))

    first_segment = list(range(0, max(0, start_focus_i), int(coarse_step_mm))) if start_focus_i > 0 else []

    focus_segment = list(range(start_focus_i, end_focus_i + 1, int(fine_step_mm)))

    third_start = end_focus_i + int(coarse_step_mm)
    third_segment = list(range(third_start, int(total_length) + 1, int(coarse_step_mm))) if third_start <= total_length else []

    full_track_mm = []
    seen = set()
    for x in first_segment + focus_segment + third_segment:
        if x not in seen:
            seen.add(x)
            full_track_mm.append(x)

    track = [int(round(x * step_per_mm)) for x in full_track_mm]
    return track
