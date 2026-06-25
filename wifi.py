import threading
import time
import tkinter as tk
from tkinter import ttk

import cv2
import numpy as np
import requests
from PIL import Image, ImageTk

ESP32_IP = "10.199.75.120"
SNAPSHOT_URL = f"http://{ESP32_IP}/snapshot"
MOTORS_URL = f"http://{ESP32_IP}/motors"

running = True
pwm_var = None
_motor_job = None

snap_session = requests.Session()
motor_session = requests.Session()

# ── Motor state ───────────────────────────────────────────────
# thrust  : 0–255  forward speed (both motors)
# yaw     : -1.0–1.0  negative = left, positive = right
# vertical: -255–255  positive = up, negative = down
motor_state = {"thrust": 0, "yaw": 0.0, "vertical": 0}


def compute_and_send():
    thrust = motor_state["thrust"]
    yaw = motor_state["yaw"]  # -1 to +1
    vertical = motor_state["vertical"]

    # Yaw mixes: one side speeds up, other slows down
    left = int(thrust * (1.0 - max(0, yaw)))
    right = int(thrust * (1.0 - max(0, -yaw)))
    left = max(0, min(255, left))
    right = max(0, min(255, right))

    try:
        motor_session.get(
            f"{MOTORS_URL}?m1={left}&m2={right}&m3={vertical}", timeout=(1, 2)
        )
    except Exception as e:
        print("Motor error:", e)


def schedule_send():
    global _motor_job
    if _motor_job:
        root.after_cancel(_motor_job)
    _motor_job = root.after(
        80, lambda: threading.Thread(target=compute_and_send, daemon=True).start()
    )


# ── Snapshot thread ───────────────────────────────────────────
frame_queue = []


def handle_frame(resp):
    buf = np.frombuffer(resp.content, dtype=np.uint8)
    # print("Bytes:", len(buf))
    gray = buf.reshape((120, 160))
    rgb = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
    rgb = cv2.resize(rgb, (640, 480), interpolation=cv2.INTER_NEAREST)
    return rgb


# def squaresin(frame):
#     img = frame.copy()
#     gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
#     edges = cv2.Canny(gray, 10, 30, apertureSize=3)
#     edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((3, 3), dtype=np.uint8), iterations=1)
#     image = img.copy()
#     contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

#     squarecount = 0 
#     for cnt in contours:
#         area = cv2.contourArea(cnt)
#         if area < 30:
#             continue

#         perimeter = cv2.arcLength(cnt, True)
#         if perimeter == 0:
#             continue

#         approx = cv2.approxPolyDP(cnt, 0.06 * perimeter, True)
#         if len(approx) != 4:
#             continue

#         if not cv2.isContourConvex(approx):
#             continue

#         rect = cv2.minAreaRect(cnt)
#         (cx, cy), (w, h), angle = rect

#         if w == 0 or h == 0:
#             continue

#         aspect_ratio = max(w, h) / min(w, h)
#         if aspect_ratio > 1.35:
#            continue

#         box_area = w * h
#         extent = area / box_area

#         if extent < 0.35:
#            continue
        
#         squarecount += 1

#         box = cv2.boxPoints(rect)
#         box = np.int32(box)
#         cv2.drawContours(image, [box], -1, (255, 0, 0), 3)

#     return image


def snapshot_thread():
    print("Snapshot thread started")
    while running:
        try:
            resp = snap_session.get(SNAPSHOT_URL, timeout=(3, 5))
            if resp.status_code == 200:
                rgb = handle_frame(resp)
                # rgb = squaresin(rgb)
                if rgb is not None:
                    # Overlay
                    t = motor_state["thrust"]
                    y = motor_state["yaw"]
                    v = motor_state["vertical"]
                    l = int(t * (1.0 - max(0, y)))
                    r = int(t * (1.0 - max(0, -y)))
                    cv2.putText(
                        rgb,
                        f"L:{l} R:{r} V:{v}",
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.8,
                        (0, 0, 0),
                        2,
                    )
                    frame_queue.append(rgb)
        except Exception as e:
            print("Snapshot error:", e)
        time.sleep(0.05)


def update_frame():
    if frame_queue:
        rgb = frame_queue.pop()
        frame_queue.clear()
        img = ImageTk.PhotoImage(Image.fromarray(rgb))
        video_label.config(image=img)
        video_label.image = img
    if running:
        root.after(30, update_frame)


# ── GUI ───────────────────────────────────────────────────────
root = tk.Tk()
root.title("Blimp Controller")
root.resizable(False, False)

video_label = tk.Label(root, bg="black", width=640, height=480)
video_label.grid(row=0, column=0, columnspan=3, padx=10, pady=(10, 6))

# ── Thrust ────────────────────────────────────────────────────
tk.Label(root, text="Thrust (M1+M2)", font=("Helvetica", 11)).grid(
    row=1, column=0, columnspan=3
)

thrust_val = tk.IntVar(value=0)
thrust_lbl = tk.Label(root, text="0", font=("Helvetica", 11, "bold"), width=4)
thrust_lbl.grid(row=2, column=2, padx=(0, 10))


def on_thrust(v):
    motor_state["thrust"] = int(float(v))
    thrust_lbl.config(text=str(motor_state["thrust"]))
    schedule_send()


ttk.Scale(
    root, from_=0, to=255, orient="horizontal", length=460, command=on_thrust
).grid(row=2, column=0, columnspan=2, padx=(10, 4), pady=2)

# ── Yaw ───────────────────────────────────────────────────────
tk.Label(root, text="Yaw  ← left / right →", font=("Helvetica", 11)).grid(
    row=3, column=0, columnspan=3
)

yaw_val = tk.DoubleVar(value=0.0)
yaw_lbl = tk.Label(root, text="0.00", font=("Helvetica", 11, "bold"), width=6)
yaw_lbl.grid(row=4, column=2, padx=(0, 10))


def on_yaw(v):
    motor_state["yaw"] = round(float(v), 2)
    yaw_lbl.config(text=f"{motor_state['yaw']:+.2f}")
    schedule_send()


yaw_slider = ttk.Scale(
    root, from_=-1.0, to=1.0, orient="horizontal", length=460, command=on_yaw
)
yaw_slider.grid(row=4, column=0, columnspan=2, padx=(10, 4), pady=2)


def reset_yaw():
    yaw_slider.set(0.0)
    on_yaw(0.0)


tk.Button(root, text="Centre yaw", command=reset_yaw, font=("Helvetica", 10)).grid(
    row=5, column=0, columnspan=3, pady=(0, 4)
)

# ── Vertical (M3) ─────────────────────────────────────────────
tk.Label(root, text="Vertical  ↓ down / up ↑  (M3)", font=("Helvetica", 11)).grid(
    row=6, column=0, columnspan=3
)

vert_lbl = tk.Label(root, text="0", font=("Helvetica", 11, "bold"), width=5)
vert_lbl.grid(row=7, column=2, padx=(0, 10))


def on_vertical(v):
    motor_state["vertical"] = int(float(v))
    vert_lbl.config(text=str(motor_state["vertical"]))
    schedule_send()


ttk.Scale(
    root, from_=-255, to=255, orient="horizontal", length=460, command=on_vertical
).grid(row=7, column=0, columnspan=2, padx=(10, 4), pady=2)


# ── Stop all ─────────────────────────────────────────────────
def stop_all():
    motor_state.update({"thrust": 0, "yaw": 0.0, "vertical": 0})
    for w in root.winfo_children():
        if isinstance(w, ttk.Scale):
            w.set(0)
    thrust_lbl.config(text="0")
    yaw_lbl.config(text="0.00")
    vert_lbl.config(text="0")
    threading.Thread(target=compute_and_send, daemon=True).start()


tk.Button(
    root,
    text="STOP ALL",
    command=stop_all,
    bg="#e74c3c",
    fg="white",
    font=("Helvetica", 12, "bold"),
    padx=20,
    pady=6,
).grid(row=8, column=0, columnspan=3, pady=(6, 12))


def on_close():
    global running
    running = False
    motor_state.update({"thrust": 0, "yaw": 0.0, "vertical": 0})
    compute_and_send()
    root.destroy()


root.protocol("WM_DELETE_WINDOW", on_close)
threading.Thread(target=snapshot_thread, daemon=True).start()
root.after(30, update_frame)
root.mainloop()
