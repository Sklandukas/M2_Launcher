def ui_call(widget, fn):
    try:
        widget.after(0, fn)
    except Exception:
        pass
