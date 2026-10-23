import math


class Fit:
    slide = 0.3
    press = 0.1
    insert_m2 = 3.2
    insert_m3 = 4.0
    clear_m2 = 2.4
    clear_m3 = 3.4
    pilot_m2 = 1.8
    pilot_m3 = 2.6
    magnet_d = 10.2
    magnet_h = 3.1
    zip_w = 3.6
    zip_t = 1.8
    m3_head_d = 5.6
    m3_head_h = 3.0
    csk_m3_d = 6.2
    csk_m2_d = 4.0
    m2_head_d = 3.8
    m2_head_h = 2.0
    m3_washer_d = 9.0


class Print:
    petg_density = 1.27
    pla_density = 1.24
    walls = 3
    line_w = 0.42
    layer = 0.2
    top_bottom_layers = 4
    infill = 0.20


class Body:
    front_x = 100.0
    rear_x = -80.0
    width_y = 150.0
    corner_r = 38.0
    bottom_z = 10.0
    top_z = 80.0
    wall = 2.4
    top_fillet = 15.0
    len_x = front_x - rear_x
    centre_x = (front_x + rear_x) / 2.0
    half_y = width_y / 2.0
    flat_front_half = half_y - corner_r
    corner_cx_front = front_x - corner_r
    corner_cx_rear = rear_x + corner_r


class Floor:
    thick = 3.0
    z0 = Body.bottom_z
    z1 = Body.bottom_z + 3.0
    edge_gap = 0.4
    inset = Body.wall + 0.4


class Motor:
    gear_w = 12.0
    gear_h = 10.0
    gear_len = 9.0
    can_len = 15.0
    enc_len = 10.0
    enc_w = 12.0
    enc_h = 10.0
    face_y = Body.half_y
    axis_x = 0.0
    axis_z = 21.5
    shaft_d = 3.0
    shaft_flat = 2.5
    shaft_len = 10.0
    pocket_fit = 0.2
    clamp_y0 = 52.0
    clamp_y1 = 71.0
    clamp_wall = 6.5
    clamp_squeeze = 0.5
    cap_t = 3.0
    cap_screw_y = (55.5, 67.5)
    total_len = gear_len + can_len + enc_len


class Wheel:
    d = 43.0
    w = 12.0
    centre_y = 82.5
    bore_d = Motor.shaft_d
    bore_flat = Motor.shaft_flat
    hub_boss_d = 10.0
    web_t = 3.0
    holes = 6
    hole_d = 7.0
    oring_id = 37.0
    oring_cs = 3.0
    oring_count = 2
    groove_w = 3.2
    groove_pitch = 6.0
    floor_d = oring_id
    rim_d = floor_d + 1.2 * oring_cs
    bought = True
    bought_d = 43.0
    bought_w = 18.0
    bought_hub_d = 12.0
    inner_y = Body.half_y + 1.5
    bought_centre_y = inner_y + bought_w / 2.0


class Cells:
    holder_y = 77.0
    holder_x = 41.0
    holder_h = 20.0
    x1 = -11.5
    x0 = x1 - holder_x
    cell_d = 18.6
    cell_l = 65.2
    open_clear = 0.3
    ear_len = 9.0
    ear_w = 12.0
    ear_t = 2.0
    screw_y = 44.5
    holder_holes = ((0.0, -18.0), (0.0, 18.0))
    csk_d = Fit.csk_m3_d
    cx = (x0 + x1) / 2.0


class Shelf:
    x0 = -54.0
    x1 = -12.0
    hw = 46.0
    z0 = 34.5
    t = 2.5
    z1 = z0 + t
    pillar_d = 7.0
    pillars = ((-50.0, 43.0), (-50.0, -43.0), (-16.0, 43.0), (-16.0, -43.0))
    corner_r = 4.0


class Board:
    def __init__(self, name, lx, ly, cx, cy, standoff, pcb_t, comp_h, mount, holes=(), deck="floor"):
        self.deck = deck
        self.name = name
        self.lx = lx
        self.ly = ly
        self.cx = cx
        self.cy = cy
        self.standoff = standoff
        self.pcb_t = pcb_t
        self.comp_h = comp_h
        self.mount = mount
        self.holes = holes

    @property
    def x0(self):
        return self.cx - self.lx / 2.0

    @property
    def x1(self):
        return self.cx + self.lx / 2.0

    @property
    def y0(self):
        return self.cy - self.ly / 2.0

    @property
    def y1(self):
        return self.cy + self.ly / 2.0

    @property
    def base_z(self):
        return Shelf.z1 if self.deck == "shelf" else Floor.z1

    @property
    def z0(self):
        return self.base_z + self.standoff


class Esp:
    lx = 23.5
    ly = 18.0
    pcb_t = 1.2
    comp_h = 2.0
    standoff = 1.5
    usb_w = 9.0
    usb_h = 3.2
    usb_overhang = 0.6
    usb_gap_to_wall = 0.3
    cy = 23.0
    x0 = Body.rear_x + Body.wall + usb_gap_to_wall + usb_overhang
    usb_z = Floor.z1 + standoff + pcb_t + usb_h / 2.0
    slot_w = 13.0
    slot_h = 7.5


ESP = Board("esp32s3_supermini", Esp.lx, Esp.ly, Esp.x0 + Esp.lx / 2.0, Esp.cy, Esp.standoff, Esp.pcb_t, Esp.comp_h, "cradle")
DRV = Board("drv8833", 18.5, 16.0, -32.75, 36.0, 1.5, 1.6, 3.0, "cradle", deck="shelf")
UPS = Board("hw465a_ups", 26.0, 52.0, -35.0, 0.0, 4.0, 1.6, 9.0, "standoffs",
            holes=((-10.5, -23.5), (10.5, -23.5), (-10.5, 23.5), (10.5, 23.5)), deck="shelf")
BMS = Board("bms_1s", 40.0, 8.0, -33.0, -54.0, 1.5, 1.2, 2.5, "cradle")
BOARDS = (ESP, DRV, UPS, BMS)


class Cap:
    d = 10.0
    l = 17.0
    x0 = -72.0
    cy = -4.0
    lift = 0.5


class Deck:
    x0 = -76.0
    x1 = 34.0
    grid_pitch = 7.5
    grid_margin = 3.0
    edge_margin = 4.0
    standoff_d = 5.5
    cradle_lip = 1.5
    cradle_wall = 1.6


class Vl53:
    lx = 25.0
    ly = 10.7
    pcb_t = 1.6
    chip_h = 1.0
    chip_off_long = 0.0
    chip_off_short = 0.0
    fov_deg = 25.0
    aperture_sep = 2.5
    groove_fit = 0.3
    groove_depth = 1.0


class FrontSensor:
    y = 0.0
    z = 40.0
    chip_face_x = Body.front_x - Body.wall - 1.1
    base_x1 = 97.0
    post_x0 = 93.0
    post_y0 = 8.6
    post_y1 = 11.6
    rail_back = 1.0
    full_rail_z = 33.0
    stop_t = 1.0
    top_t = 2.0
    foot_x0 = 93.0
    screw_dy = 10.1
    window_w = 14.0
    window_h = 8.0


class Omni:
    d = 58.0
    width = 26.0
    bore = 6.2
    boss_d = 20.0
    face_to_face = width
    clear = 2.0
    mass = 50.0
    bolt_d = 6.0
    bolt_clear = 6.4
    nut_af = 10.0
    nylock_h = 6.0
    r = d / 2.0
    z = r
    keep_r = r + clear
    keep_hw = width / 2.0 + clear
    front_limit = FrontSensor.chip_face_x - Vl53.chip_h - Vl53.pcb_t - Vl53.groove_fit - FrontSensor.rail_back
    x = front_limit - keep_r - 0.1


class OmniFork:
    cheek_t = 5.0
    half_x = 14.0
    axle_boss_r = 9.0
    bridge_t = 3.0
    bridge_hx = 6.0
    spacer_d = 14.0
    nut_pocket = 3.0
    foot_w = 7.0
    foot_t = 5.5
    foot_hx = 12.0
    insert_proud = 1.0
    cheek_y0 = Omni.face_to_face / 2.0 + Omni.clear
    cheek_y1 = cheek_y0 + cheek_t
    screw_y = cheek_y1 + foot_w / 2.0 - 0.5
    screw_dx = 8.0
    bridge_z0 = Omni.z + Omni.keep_r
    bolt_min = 2.0 * cheek_y1 + Omni.nylock_h - nut_pocket + 1.0


OmniFork.bolt_len = min(L for L in (40.0, 45.0, 50.0, 55.0, 60.0) if L >= OmniFork.bolt_min)


class DropSensor:
    x = 92.0
    y = -31.0
    chip_z = 27.0
    pitch = 32.0
    margin = 1.0
    post_t = 2.5
    post_wall = 1.5
    slide = 15.0
    half_fov = Vl53.fov_deg / 2.0
    reading = chip_z / math.cos(math.radians(pitch))
    rear_ground_x = x + chip_z * math.tan(math.radians(pitch - Vl53.fov_deg / 2.0)) - Vl53.aperture_sep / 2.0 / math.cos(math.radians(pitch - Vl53.fov_deg / 2.0))


class AirPod:
    board_lx = 20.0
    board_lz = 27.0
    pcb_t = 1.6
    comp_front = 1.6
    comp_back = 0.5
    chip_w = 3.0
    chip_h = 0.93
    chip_dz = 0.0
    cx = 57.5
    board_y1 = 69.0
    wire_room = 1.5
    wall = 1.6
    groove_depth = 1.0
    groove_fit = 0.3
    roof_t = 2.0
    wall_gap = 0.5
    tab_y0 = 60.2
    tab_w = 5.4
    tab_h = 6.0
    notch_w = 8.0
    notch_h = 2.0
    vent_w = 1.5
    vent_pitch = 3.0
    vent_count = 6
    vent_z0 = 16.0
    vent_z1 = 38.0
    vent_reach = 20.0
    board_y0 = board_y1 - pcb_t
    board_x0 = cx - board_lx / 2.0
    board_x1 = cx + board_lx / 2.0
    board_z0 = Floor.z1
    board_z1 = board_z0 + board_lz
    chip_z = board_z0 + board_lz / 2.0 + chip_dz
    back_y1 = board_y0 - comp_back - wire_room
    back_y0 = back_y1 - wall
    x0 = board_x0 - groove_fit - wall
    x1 = board_x1 + groove_fit + wall
    roof_z0 = board_z1 + groove_fit
    roof_z1 = roof_z0 + roof_t


AirPod.vent_x = tuple(AirPod.cx + (i - (AirPod.vent_count - 1) / 2.0) * AirPod.vent_pitch for i in range(AirPod.vent_count))


class Switch:
    l = 20.0
    h = 10.3
    t = 6.4
    hole_pitch = 9.5
    hole_d = 2.2
    hole_from_back = 2.9
    lever_free = 3.0
    lever_contact_from_end = 5.0
    lever_travel_to_click = 1.0
    rest_play = 0.3
    lever_flat = 0.8


class Bumper:
    gap = 2.5
    thick = 3.0
    z0 = 14.0
    z1 = 46.0
    x_end = 70.0
    travel = 2.5
    guide_y = 50.0
    guide_z = 24.0
    boss_d = 8.0
    boss_back = 3.0
    insert_len = 4.0
    window_w = 14.0
    window_h = 8.0
    window_z = FrontSensor.z
    tower_x0 = 76.0
    tower_x1 = 90.0
    tower_hw = 4.0
    tower_z1 = 30.0
    bore_d = 3.0 + 2 * Fit.slide
    screw_len = 25.0
    spring_od = 5.0
    spring_free = 10.0
    notch_w = 9.0
    notch_top = guide_z + boss_d / 2.0 + 1.0
    pedestal_pad = 0.7


class Phone:
    w = 168.0
    h = 80.0
    t = 12.0
    corner_r = 8.0
    body_w = 163.9
    body_h = 75.9
    bar_side = -1.0
    bar_top = 17.75
    bar_bottom = 38.5
    bar_proud = 2.0
    lenses = (("wide", 28.1, 17.0), ("ultrawide", 28.1, 31.8), ("tele", 28.1, 42.3))
    rear_camera = "wide"
    rear_fov_h = 71.4
    rear_fov_v = 56.9


class Tilt:
    axis_x = 60.0
    axis_to_case = 15.0
    shell_clear = 4.0
    axis_z = Body.top_z + shell_clear + math.hypot(axis_to_case + Phone.t, Phone.h / 2.0)
    rest = 8.0
    t_min = -35.0
    t_max = 90.0
    sweep_margin = 3.0
    sweep_step = 2.5
    check_step = 5.0


class Plate:
    t = 3.0
    wy = 26.0
    hs = 50.0
    groove_w = 1.2
    groove_d = 0.6
    groove_pitch = 5.0
    tongue_root_hw = 7.0
    tongue_tip_hw = 9.0
    tongue_h = 3.0
    tongue_len = 40.0
    tongue_chamfer = 1.0
    dimple_r = 1.4
    dimple_depth = 0.8
    dimple_s = -8.0
    back_w = Tilt.axis_to_case
    front_w = Tilt.axis_to_case - t
    tip_w = front_w - tongue_h


class Servo:
    body_l = 22.8
    body_w = 12.2
    body_h = 22.5
    total_h = 28.5
    shaft_from_end = 6.0
    boss_d = 11.8
    boss_top = 26.5
    spline_d = 4.8
    tab_total = 32.2
    tab_t = 2.5
    tab_y0 = 18.5
    tab_hole_pitch = 27.8
    tab_hole_d = 2.0
    snip_front_tab = True
    stall_kgcm = 1.8
    bottom_y = 16.0
    lead_w = 3.6
    lead_h = 1.4
    front_x = Tilt.axis_x + shaft_from_end
    back_x = front_x - body_l
    centre_x = (front_x + back_x) / 2.0
    tab_len = (tab_total - body_l) / 2.0
    rear_hole_x = centre_x - tab_hole_pitch / 2.0
    spline_top_y = bottom_y + total_h


class Horn:
    d = 20.0
    t = 1.6
    hub_d = 7.0
    top_above_spline = 1.0
    hub_gap = 0.3
    screw_r = 7.0
    screw_angles = (90.0, 270.0)
    screw_pilot = 1.5
    centre_hole = 6.5
    outer_y = Servo.spline_top_y + top_above_spline
    pocket_fit = 0.2
    hub_y0 = Servo.bottom_y + Servo.boss_top + hub_gap


class Yoke:
    socket_w0 = 5.0
    socket_w1 = Plate.front_w - Fit.slide
    socket_hw = 13.0
    s_min = -30.0
    s_max = 22.0
    bar_w0 = 10.0
    bar_w1 = Plate.back_w - 1.5
    bar_neck_y = Plate.wy / 2.0 + 0.5
    pin_w0 = 8.0
    pin_ear_t = 5.0
    pin_ear_r = 7.0
    pin_gap = 1.2
    pin_ear_y1 = -23.5
    pin_ear_y0 = pin_ear_y1 - pin_ear_t
    horn_ear_t = 5.0
    horn_ear_r = 11.5
    servo_clear = 1.0
    tab_hw = 4.0
    tab_root_s = -19.0
    tab_free_s = -5.0
    tab_t = 1.6
    tab_slot = 1.0
    bump_r = 1.2
    bump_h = 0.6
    bump_s = Plate.dimple_s
    horn_ear_y0 = Horn.outer_y - Horn.t
    horn_ear_y1 = horn_ear_y0 + horn_ear_t


class Post:
    col_x0 = 26.0
    col_x1 = 43.0
    col_y0 = Yoke.pin_ear_y1 + Yoke.pin_gap
    col_y1 = Servo.bottom_y + Servo.tab_y0 - 0.2
    col_z0 = 62.0
    col_top_rel = 5.5
    wall = 2.4
    hollow_top = 112.0
    arm_y0 = Yoke.pin_ear_y1 + Yoke.pin_gap
    arm_y1 = -16.5
    boss_r = 6.5
    bearing_d = Fit.clear_m3
    shelf_t = 3.5
    shelf_x1 = 57.0
    shelf_y1 = Servo.bottom_y + Servo.body_h
    hood_gap = 0.15
    shelf_gap = 0.1
    hood_t = 1.5
    hood_len = 4.0
    leg_t = 4.0
    back_foot = (-10.5, -0.5)
    front_foot = (36.0, 44.0)
    foot_t = 5.0
    screw_xy = ((-5.5, -18.0), (-5.5, 29.0), (40.0, -19.0), (40.0, 28.0))
    insert_depth = 6.0
    clear = 1.0
    lead_hole = (4.5, 4.0)
    tab_pilot_depth = 8.0
    omni_gap = 1.0


class ShellCfg:
    boss_d = 9.0
    boss_top = 27.0
    boss_inset = 5.0
    bosses = ((-55.0, 1), (-55.0, -1), (40.0, 1), (40.0, -1))
    insert_depth = 7.0
    motor_notch_clear = 0.5
    kcd_w = 10.0
    kcd_h = 15.0
    kcd_z = 54.0
    kcd_panel = 1.5
    kcd_recess_margin = 3.0
    strip_w = 30.0
    strip_h = 4.0
    strip_t = 0.5
    strip_fit = 0.2
    strips_z = (22.0, 29.0, 36.0)
    strip_names = ("GND", "DETECT", "5V")
    wire_hole_d = 1.8
    wire_hole_y = -13.0
    magnet_y = 28.0
    magnet_z = 29.0
    magnet_boss_d = 14.0
    magnet_back = 1.0
    top_open_margin = 1.5
    top_open_r = 5.0


class Dock:
    base_w = 120.0
    base_d = 110.0
    base_t = 6.0
    rail_h = 10.0
    rail_t = 4.0
    rail_len = 60.0
    rail_gap0 = 2.0
    rail_gap1 = 20.0
    wing_margin = 3.0
    feet_d = 10.5
    feet_depth = 1.0
    feet_inset = 10.0
    weight_pocket = (44.0, 34.0, 3.5)
    pogo_d = 2.0
    pogo_len = 8.0
    pogo_tip_d = 1.0
    pogo_proud = 3.0
    pogo_compress = 1.5
    pogo_hole = pogo_d + 2 * Fit.press
    pin_y = 6.0
    pin_rows_z = ShellCfg.strips_z
    snap_to_grid = True
    grid = 2.54
    perf_t = 1.6
    perf_w = 46.0
    perf_h = 26.0
    block_hw = 36.0
    block_depth = 16.0
    block_z1 = 45.0
    block_wall = 3.0
    wall_w = 120.0
    wall_h = 150.0
    wall_t = 5.0
    wall_corner_r = 30.0
    tag = 60.0
    tag_black = 48.0
    tag_recess = 0.6
    tag_z = 120.0
    tag_fit = 0.4
    usb_board = (14.0, 11.0, 1.6)
    usb_jack = (9.0, 3.4, 7.4)
    usb_z = 22.0
    tab_t = 4.0
    tab_depth = 3.0
    face_x = Body.rear_x - (pogo_proud - pogo_compress)
    block_x0 = face_x - block_depth
    wall_x1 = block_x0
    wall_x0 = wall_x1 - wall_t
    base_x0 = wall_x0 - 4.0
    base_x1 = wall_x0 + base_d
    rail_x0 = face_x
    rail_x1 = face_x + rail_len


def dock_pins():
    rows = list(Dock.pin_rows_z)
    py = Dock.pin_y
    if Dock.snap_to_grid:
        mid = rows[1]
        step = round((rows[1] - rows[0]) / Dock.grid) * Dock.grid
        rows = [mid - step, mid, mid + step]
        py = round(Dock.pin_y / Dock.grid) * Dock.grid
    return [(-py, rows[0], "GND"), (py, rows[0], "GND"), (0.0, rows[1], "DETECT"),
            (-py, rows[2], "5V"), (py, rows[2], "5V")]


MEASURE = (
    ("Phone in case width/height/thickness", "Phone.w / Phone.h / Phone.t"),
    ("Phone camera bar: distance from the top edge, height, how far it stands out of the case back; lens centres", "Phone.bar_* / Phone.lenses"),
    ("MG90S body, tabs, shaft offset, spline height", "Servo.*"),
    ("Servo horn disc diameter, thickness, screw radius", "Horn.*"),
    ("N20 gearbox/can/encoder sizes", "Motor.*"),
    ("Bought front omni wheel: diameter, width, bore, hub boss, mass", "Omni.d / width / bore / boss_d / face_to_face / mass"),
    ("Bought drive wheels: diameter, width (or the O-ring size for the printed hub)", "Wheel.bought_* / Wheel.oring_*"),
    ("Wheel diameter/width, shaft D", "Wheel.* / Motor.shaft_*"),
    ("Cell holder outline and its screw holes", "Cells.holder_* / Cells.holder_holes"),
    ("HW-465A UPS board outline and hole positions", "UPS in params.py"),
    ("ESP32-S3 SuperMini outline, USB-C overhang and height", "Esp.*"),
    ("DRV8833 module outline", "DRV in params.py"),
    ("1S BMS outline", "BMS in params.py"),
    ("1000 uF capacitor diameter/length", "Cap.*"),
    ("GY-VL53L0XV2 board size and chip position", "Vl53.*"),
    ("BME688 board (Waveshare) outline, thickness, part heights, chip position; header must be on a 20 mm edge", "AirPod.board_* / comp_* / pcb_t / chip_dz"),
    ("Lever microswitch body, holes, lever", "Switch.*"),
    ("Brass strip thickness", "ShellCfg.strip_t"),
    ("Pogo probe barrel diameter, length, travel", "Dock.pogo_*"),
    ("USB-C power breakout board", "Dock.usb_board / Dock.usb_jack"),
    ("KCD11 cut-out", "ShellCfg.kcd_*"),
)


class Mass:
    phone = 245.0
    cells = 96.0
    holder = 12.0
    motor = 12.0
    drive_wheel = 15.0
    servo = 13.4
    ups = 20.0
    esp = 3.0
    drv = 3.0
    bms = 3.0
    cap = 3.0
    vl53 = 1.0
    kcd11 = 3.0
    magnet = 2.4
    strips = 2.0
    bolt_m6 = 12.0
    bme688 = 2.5
    wiring = 20.0
    hardware = 25.0
