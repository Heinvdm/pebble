# Gimbal-class BLDC motors, gear reductions, magnetic encoders and small integrated joint actuators for a 12-motor mini hexapod

Research date: 17 October 2026. Notes on method and source quality, which apply to every section:
- The page-fetch tool could not reach most vendor sites in this session (DNS failures for iflight.com, cubemars.com, tmotor.com, robotshop.com, simplefoc.com, infineon.com, openelab, aifitlab and others). Only github.com could be fetched. Nearly all vendor numbers below therefore come from search-engine summaries of the listed pages, not from reading the pages directly. Every number should be checked on the page before parts are ordered.
- Labels used: **[maker]** = the maker's own store or product page (iFlight for iPower, CubeMars, T-Motor, DFRobot); **[seller]** = a reseller or marketplace listing; **[datasheet]** = an IC or product datasheet; **[forum]** = a community post; **[est]** = my own estimate or arithmetic, not from a source.
- Prices are as shown in search results on 17 Oct 2026, in USD. They may be cached or out of date. No NZD prices were found.
- The session's web search limit was reached before every gap could be closed. The Gaps sections list what remains.

## Q1. Which small gimbal/outrunner BLDC motors fit a 35–40 mm hip, and what are their exact numbers?

### Takeaway
Gimbal motors 35 mm across or less, with listed specs, run from about 26 g (a generic 2204 260KV) to 39–51 g (2804 class) and 64 g (GM3506, which is right at the 40 mm limit). No motor that can reach 0.35 Nm through a gearbox of 10:1 or less weighs under about 39 g, except the generic 2204, whose resistance is unknown. The CubeMars GL30 (34.5 × 15.7 mm, 41 g, phase-to-phase resistance 1.53 Ω, Kt 0.032–0.038 Nm/A) is the strongest electrical fit for a 9 V bus. The iPower GBM2804H-100T (35 × 15 mm, 39 g, about 10 Ω, $18.99) is the cheapest, but its high resistance limits it at 9 V.

### Cited Findings

**iFlight iPower GBM2804H-100T (2804 class, no encoder)**
- Outer diameter 35 mm, height 15 mm, 12N/14P (7 pole pairs), internal resistance 10 Ω ±5% (changes with temperature), weight 39 ±0.2 g, no-load speed 1468–1622 rpm at 10 V, load torque 250–350 g·cm (0.025–0.034 Nm), max power 25 W, price $18.99 **[maker]** — [iFlight store](https://shop.iflight.com/ipower-gimbal-brushless-motor-gbm2804h-100t-pro218); Basecam also lists 10 Ω **[seller]** — [Basecam Electronics](https://shop.basecamelectronics.com/product/gbm2804h-100t)
- Same motor listed at $28.46 **[seller]** — [rcdrone.top](https://rcdrone.top/collections/gimbal-motor)
- Hollow shaft, OD about 7 mm. Mounting holes are shown only as "see drawing" **[seller]** — [ATGroup](https://atgroup.store/product/gbm2804h-100t/); [iFlight store](https://shop.iflight.com/ipower-gimbal-brushless-motor-gbm2804h-100t-pro218)
- RCTimer's own GBM2804 100T is sold as **145 KV**, with bottom holes 16 mm and 19 mm centre-to-centre and top (rotor) holes 12 mm centre-to-centre. This is a different maker's motor with the same winding name, so it is a lead, not a confirmed spec for the iPower part **[seller/maker of a sibling motor]** — [RCTimer](https://www.rctimer.com/rctimer-gbm2804-hollow-shaft-brushless-gimbal-motor-p0445.html)
- A SimpleFOC user measured 6.3 Ω on a GBM2804-100T (method not confirmed) **[forum]** — [SimpleFOC forum](https://community.simplefoc.com/t/inductance-request-for-help-with-wiring/7824)

**iFlight iPower GM2804 (2804 class, sold with an AS5048A encoder)**
- Motor only: 9 Ω ±5%, 42.3 ±0.2 g, PH3P connector on a 60 mm lead **[maker]** — [iFlight store GM2804](https://shop.iflight.com/ipower-gm2804-gimbal-motor-pro1153)
- With encoder: 12N/14P, hollow shaft ID 6.5 (+0.05/0) mm, 10 V nominal, no-load 1602–1771 rpm, load torque 250–350 g·cm, 9 Ω ±5%, height 25 mm including the aluminium encoder housing, 51 g **[maker]** — [iFlight store GM2804 w/ encoder](https://shop.iflight.com/ipower-gm2804-gimbal-motor-with-as5048a-encoder-pro288); the EU store lists the GM2804H-100T as 15 mm tall and 42.3 g (motor without encoder housing) — [iFlight-rc.eu](https://iflight-rc.eu/en/products/ipower-gm2804-gimbal-motor)
- Price with encoder: about $39 **[maker]**; $40.99 **[seller]** — [offthegridsun](https://offthegridsun.com/BGC-Gimbal-Brushless-Motor/IFlight-IPower-GM2804-Brushless-Gimbal-Motor-With-AS5048A-Encode); also at [RobotShop](https://www.robotshop.com/products/ipower-gm2804-gimbal-motor-w-as5048a-encoder)
- Some product copy gives the torque as 0.35 kg·cm and other copy as 0.5–1 kg·cm. The 250–350 g·cm load-torque figure is the one that repeats **[maker/seller]** — [iFlight store](https://shop.iflight.com/ipower-gm2804-gimbal-motor-with-as5048a-encoder-pro288); [Amazon listing](https://www.amazon.com/clp/B09P44K2DR)

**iFlight iPower GM3506 (3506 class, AS5048A encoder version exists)**
- OD 40 ±0.05 mm, height 17.8 ±0.2 mm, 64 ±0.2 g, hollow shaft OD 12 (−0.008/−0.012) mm and ID 8.6 mm, rotor runout ≤0.1 mm **[maker]** — [iFlight store GM3506](https://shop.iflight.com/ipower-motor-gm3506-brushless-gimbal-motor-pro967)
- Resistance 5.6 Ω ±5% **[maker]**, 5.57 Ω **[seller]**; rated load point 12 V at 1 A; no-load current 0.17 A at 16 V; no-load 2149–2375 rpm; torque 600–1000 g·cm (0.059–0.098 Nm). No KV is published — [iFlight store](https://shop.iflight.com/ipower-motor-gm3506-brushless-gimbal-motor-pro967); [RobotShop](https://www.robotshop.com/products/ipower-motor-gm3506-brushless-gimbal-motor-w-as5048a-encoder)
- A RobotShop reviewer warns that the encoder ships with a 3-pin connector that should not be used **[seller review]** — [RobotShop](https://www.robotshop.com/products/ipower-motor-gm3506-brushless-gimbal-motor-w-as5048a-encoder)
- A SimpleFOC user says the GM3506 screw holes are M2.5, not M3 **[forum]** — [SimpleFOC forum](https://community.simplefoc.com/t/gimbal-motor-external-shaft/8162)
- A forum user questioned what the 600–1000 g·cm range means, and noted that a hardware guide says gimbal motors are usually above 10 Ω **[forum]** — [SimpleFOC forum](https://community.simplefoc.com/t/magnetic-encoder-speed-limit/176/5)

**iFlight iPower GM4108H-120T (too large; listed for scale)**
- 11.1 Ω ±5%, 124 ±0.5 g (137 g with encoder), 24N/22P, height 32.3 mm, hollow shaft OD 10 mm / ID 8 mm, 265 mm 24 AWG leads, load torque 1200–1800 g·cm at 20 V and 1.5 A. No-load speed is listed as 513–567 rpm by iFlight but 1025–1089 rpm by some sellers **[maker/seller]** — [iFlight store](https://shop.iflight.com/ipower-motor-gm4108h-120t-brushless-gimbal-motor-pro217); [RobotShop](https://www.robotshop.com/products/ipower-gbm4108h-120t-gimbal-motor); [OpenELAB](https://openelab.io/sv/products/iflight-gm4108h-encoder-gimbal-motor)

**T-Motor GB2208 KV128 (2208 class)**
- KV 128, 3–4S rated, internal resistance 14.4 Ω, torque 0.6 kg·cm per volt at 3S, Φ27.5 × 23 mm, 39.5 g including cable, 20 cm cable, 6 mm hole, 12N14P, servo-style connector, made for 100–300 g cameras. These figures come from sellers, not a T-Motor datasheet **[seller]** — [RobotShop](https://www.robotshop.com/products/tmotor-gimbal-motor-gb2208); [Zbotic](https://zbotic.in/product/t-motor-gb2208-kv128-gimbal-motor/); [T-Motor store](https://store.tmotor.com/goods-447-GB2208.html)
- A LIGPOWER-branded GB2208 KV128 is listed at 39.5 g with cable, 12N14P, 6 mm hole **[seller]** — [RobotShop CA](https://ca.robotshop.com/products/ligpower-gb2208-gimbal-motor-type-3-4s-uav-drone-kv128)
- An iPower GBM2208-80T is listed at 14.6 Ω, 12N14P, 28 × 22 mm, for 100–200 g cameras; no weight or KV given **[seller]** — [Unmanned Tech](https://www.unmannedtechshop.co.uk/de/products/gbm2208-80-brushless-gimbal-motor-gopro-size-camera)

**CubeMars GL30 KV290 (newer robotics-oriented gimbal motor)**
- Φ34.5 × 15.7 mm, 41 g, 6 mm through-hole, peak torque 0.28 Nm, no-load speed 3060 rpm **[maker]** — [CubeMars GL30](https://www.cubemars.com/product/gl30-kv290-gimbal-motor.html)
- T-Motor store copy of the datasheet: rated voltage 12 V, **KV 255 rpm/V** (despite the "KV290" name), rated torque 0.08 Nm, 7 pole pairs, 41 g **[maker]** — [T-Motor store GL30](https://store.tmotor.com/goods-1123-GL30.html)
- Phase-to-phase resistance 1530 mΩ, 7 pole pairs, Kt 0.038 Nm/A, KV 255 **[seller]** — [RobotShop GL30](https://www.robotshop.com/products/cubemars-gl30-kv290-brushless-dc-motor); [CubeMars store](https://store.cubemars.com/products/gl30)
- Mounting pattern 4×M3 on the front and 3×M2.5 on the rear, from one retailer listing (the search tool did not say which of these it was). Not found on CubeMars's own pages **[seller]** — [FlyVisionPro](https://www.flyvisionpro.com/product/cubemars-gl30-kv290-brushless-gimbal-motor-6mm-hollow-shaft-41g-low-cogging-ip45/); [3DXR](https://www.3dxr.co.uk/products/cubemars-gl30-kv290)
- Rated current is listed as 2.13 A in some places and 2.3 A in another; rated speed as 1990 rpm or 2200 rpm **[seller]** — [RobotShop](https://www.robotshop.com/products/cubemars-gl30-kv290-brushless-dc-motor); [MyBotShop](https://www.mybotshop.de/CubeMars-Robot-Dynamics-GL30-KV290-w-Encoder_1)
- Listed as IP45 and "low cogging" **[seller]** — [rcdrone.top](https://rcdrone.top/products/cubemars-gl30-kv290-brushless-gimbal-motor-6mm-hollow-shaft-41g-low-cogging-ip45)
- A German seller lists the encoder version at 83 g, not 41 g **[seller]** — [MyBotShop](https://www.mybotshop.de/CubeMars-Robot-Dynamics-GL30-KV290-w-Encoder_1)
- Prices: $50.99 on the official store, sold out, encoder not clearly included **[maker]** — [CubeMars store](https://store.cubemars.com/products/gl30); with encoder $101.99 (960 in stock) or $88.34 incl. US tariffs **[seller]** — [RobotShop w/ encoder](https://www.robotshop.com/products/cubemars-gl30-kv290-w-encoder); $79.00 **[seller]** — [rcdrone.top](https://rcdrone.top/products/cubemars-gl30-kv290-brushless-gimbal-motor-6mm-hollow-shaft-41g-low-cogging-ip45); $75.99 for the encoder version, backordered **[seller]** — [AIFitLab](https://aifitlab.com/products/cubemars-gl30-motor)
- STEP and PDF drawings, with and without encoder, are listed as official downloads **[seller]** — [Pendulum Robotics](https://pendulumrobotics.com/products/gl30)

**CubeMars GL35 KV100 and GL40 KV70**
- GL35 KV100: 6 mm through-hole, encoder option, $54.99–79.99. No weight, KV or torque found **[maker]** — [CubeMars GL category](https://www.cubemars.com/categorys/gl-gimbal-motor)
- GL40 KV70 (too large): Φ46.5 × 21.5 mm, about 107 g, 8 mm through-hole, 16 V rated, no-load 1015 rpm, Ke 15.00 V/krpm, 14 pole pairs, Kt 0.14 Nm/A, rated 0.25 Nm; peak 0.5 Nm (product page) or 0.73 Nm (store and T-Motor listing); IP45 **[maker]** — [CubeMars GL40](https://www.cubemars.com/product/gl40-kv70-gimbal-motor.html); [T-Motor store GL40](https://store.tmotor.com/goods.php?id=1125)

**DFRobot 2804 three-phase BLDC with AS5600 encoder (FIT1034 / product 3005)**
- 7 pole pairs, 220 KV, phase resistance 2.3 Ω and winding resistance 5.1 Ω (both listed, not explained), delta winding, 2.8 mH winding inductance **[maker]** — [DFRobot wiki](https://wiki.dfrobot.com/fit1034/); same figures at [Grobotronics](https://grobotronics.com/brushless-motor-3-phase-2804-12v-2600rpm-300gcm.html?sl=en)
- 12 V, 2600 rpm, 300 g·cm, Φ34.5 × 19.5 mm aluminium frame, 12-bit AS5600 encoder with 0.087° accuracy, works with SimpleFOC **[maker/seller]** — [DFRobot](https://www.dfrobot.com/product-3005.html); [Mouser](https://www.mouser.it/dfrobot-2804-3-phase-brushless-dc-motor)

**Generic 2204 260KV gimbal motor**
- 26 g, load capacity 100–200 g **[seller]** — [Robu](https://robu.in/?p=57801); 28 × 28 × 13 mm, 12–24 V, 260 KV, max operating current 600 mA **[seller]** — [Zbotic](https://zbotic.in/?p=463615)
- Another 260KV listing gives max continuous current 1.3 A **[seller]** — [VXB](https://vxb.com/ja/products/260kv-brushless-motor-for-drone-camera-gimbals-and)
- A listing titled 260KV actually describes a hollow-shaft motor with a 22 mm stator, about 100 KV and about 50 g. "2204" listings vary a lot **[seller]** — [MakerStore](https://www.makerstore.com.au/product/mb-elc-motor-bldc-gim2204/)

**Newer encoder-equipped 2804 kits (2025–2026 listings)**
- 2804 hollow-shaft motor with AS5600 kit: 6.5 mm motor bore, 5.5 mm magnet-ring bore, about 300 g·cm at 12 V, rated 0.5 A, max 2 A **[seller]** — [Amazon B0FSZ7XWG2](https://www.amazon.com/Hollow-Outrunner-Brushless-Encoder-Support/dp/B0FSZ7XWG2); kit with AS5600 and a SimpleFOC Mini driver — [Amazon B0FXKN9YMJ](https://www.amazon.com/Brushless-Outrunner-Magnetic-Encoder-SimpleFOCmini/dp/B0FXKN9YMJ)
- An AliExpress 2804 kit is offered with either an AS5600 or an MT6701 encoder plus a FOC driver board **[seller]** — [AliExpress](https://www.aliexpress.us/item/3256811495361668.html)

### Inferences
- **Summary table** (all numbers from the findings above; KV values marked [est] come from no-load rpm ÷ test voltage):

| Motor | OD × H (mm) | Mass (g) | KV (rpm/V) | R listed (Ω) | Pole pairs | Hollow | Encoder magnet included | Price (USD) |
|---|---|---|---|---|---|---|---|---|
| iPower GBM2804H-100T | 35 × 15 | 39 | ~155 [est from 1468–1622 rpm @10 V]; RCTimer 100T sibling 145 | 10 (likely phase-to-phase) | 7 | yes, ~7 mm OD | no | 18.99 |
| iPower GM2804 (+AS5048A) | 35 × 15 (25 with encoder) | 42.3 / 51 | ~169 [est from 1602–1771 @10 V] | 9 | 7 | yes, 6.5 mm ID | yes (AS5048A in housing) | ~39–41 |
| iPower GM3506 | 40 × 17.8 | 64 | ~141 [est, if rpm is at 16 V] | 5.6 | not found | yes, 12 OD/8.6 ID | encoder version exists | not found |
| T-Motor GB2208 | 27.5 × 23 | 39.5 with cable | 128 | 14.4 | 7 (12N14P) | 6 mm hole | no | not found |
| CubeMars GL30 | 34.5 × 15.7 | 41 (83 listed for one encoder version) | 255 (listed) / 290 (name) | 1.53 phase-to-phase | 7 | 6 mm | encoder version | 50.99 bare; 88–102 with encoder |
| DFRobot 2804 + AS5600 | 34.5 × 19.5 | not found | 220 | 2.3 phase / 5.1 winding | 7 | not found | yes (AS5600) | not found |
| Generic 2204 260KV | 28 × 13 | 26 | 260 | not found | not found | varies | no | not found |

- The "internal resistance" iFlight lists is almost certainly phase-to-phase (it is what a meter reads across two leads). In a wye winding the per-phase value is half. I use R_phase = R_listed ÷ 2 below, except for the DFRobot 2804, where I use 5.1 ÷ 2 = 2.55 Ω to be cautious.
- GM4108 (about 46–47 mm) and GL40 (46.5 mm) are too wide for a 35–40 mm hip. GM3506 is exactly 40 mm across and 64 g, so it only fits if the hip allows the full 40 mm, and it breaks the weight budget.
- The "100T"/"80T" names are turns per tooth. More turns means higher resistance and lower KV. At a 9 V bus that is a handicap (see Q2).

### Gaps
- No official dimensioned drawings were readable for any iPower motor, so the base and rotor bolt patterns of the GBM2804H, GM2804 and GM3506 are not confirmed. Only the RCTimer sibling (16/19 mm base, 12 mm rotor) and the GL30 (4×M3 front, 3×M2.5 rear, seller-only) have numbers. Shaft lengths were not found for any motor.
- KV is not published by iFlight for the GBM2804H, GM2804 or GM3506. The KV values in the table are estimates. For the GM3506 it is not clear whether the 2149–2375 rpm was measured at 16 V or 12 V. At 12 V the KV would be about 179–198.
- No 2206 or 2806 gimbal motor with complete specs was found. EMAX, Tarot and BGM gimbal motors were not covered before the search limit was reached.
- GL30 mass with encoder (41 g vs 83 g) and rated current (2.13 vs 2.3 A) conflict between sources.
- DFRobot 2804 mass and price were not found.
- No NZD prices were found.

## Q2. What gear ratio does each motor need for 0.35 Nm peak and 0.13 Nm continuous at the joint, at ≤1.5 A from 9 V, while still reaching about 10 rad/s?

### Takeaway
At 9 V, the high-resistance gimbal windings (GBM2804H, GM2804, GB2208) cannot even draw 1.5 A at stall. They reach 0.35 Nm only at near-zero speed with about 7.5–9:1 gearing, and give only about 0.1–0.2 Nm at a 10 rad/s hop push. Low-resistance motors (CubeMars GL30, and on paper the DFRobot 2804 and GM3506) can hold the full 1.5 A at speed. The GL30 needs about 7–8.5:1 and loses only about 0.35 W per joint while standing, against about 1.1–1.3 W for the 2804 and 3506 types.

### Cited Findings
- Kt ≈ 8.27/KV, with Kt in Nm/A and KV in rpm/V. The constant is 15√3/π ≈ 8.27. ODrive developers warn that makers "fudge their kv/kt", so Kt should be measured **[forum]** — [ODrive forum: torque calculation](https://discourse.odriverobotics.com/t/question-about-torque-calculation/4295); [ODrive forum: hub motor torque](https://discourse.odriverobotics.com/t/hover-board-hub-motor-less-torque-than-expected/6426)
- The GL30's listed Kt is 0.038 Nm/A at a listed KV of 255. 8.27/255 gives 0.032 Nm/A, so the listing is about 17% higher than the formula **[seller]** — [RobotShop GL30](https://www.robotshop.com/products/cubemars-gl30-kv290-brushless-dc-motor)
- A printed planetary drive was measured at about 84% efficiency **[maker test]** — [How To Mechatronics](https://howtomechatronics.com/how-it-works/what-is-the-best-3d-printed-drive-for-your-next-robotic-project/)
- A SimpleFOC forum builder estimated that a gimbal-motor option gives only about 0.092 Nm, so a 2 Nm, 120 rpm quadruped joint target could not be met **[forum]** — [SimpleFOC forum thread 5061](https://community.simplefoc.com/t/selecting-gimbal-motors-to-build-an-actuator-for-a-small-quadruped/5061)

### Inferences
**Conventions and method [est]:**
- KV is the listed or estimated rpm/V. Kt = 8.27/KV in Nm/A. Current I is the FOC q-axis current, as a phase-current amplitude, which is what the 8.27 constant assumes. "1.5 A per motor" is taken to mean this phase current, not bus current.
- At a 9 V bus with space-vector PWM, the largest phase-voltage amplitude is 9/√3 = 5.20 V. Stall current is therefore capped at I_stall = 5.20 / R_phase. Unloaded motor speed is about ω0 = KV × 9 × 2π/60 rad/s.
- Current still available at motor speed ω is roughly I_stall × (1 − ω/ω0), a straight-line model that ignores inductance.
- Gearbox efficiency is taken as η = 0.85, from the 84% printed-drive figure. Ratio for the peak: N = 0.35 / (η × Kt × I_avail), with I_avail = min(1.5 A, I_stall).
- Joint torque at the 10 rad/s hop push: τ = I(ω_m) × Kt × N × η, where ω_m = 10 × N.
- Standing copper loss at 0.13 Nm on the joint: τ_m = 0.13 / (η N), I = τ_m / Kt, P = 1.5 × I² × R_phase.

**Worked numbers [est]:**

| Motor | KV used | Kt (Nm/A) | R_phase (Ω) | I_stall at 9 V (A) | I usable (A) | Motor τ at that I (Nm) | N for 0.35 Nm | ω0 at 9 V (rad/s) | Motor ω at joint 10 rad/s | Joint τ available at 10 rad/s (Nm) | Standing loss at 0.13 Nm (W) | Copper heat at peak (W) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| GBM2804H-100T | 155 | 0.0534 | 5.0 | 1.04 | 1.04 | 0.0555 | **7.4** | 146 | 74 | **0.17** | 1.12 | 8.1 |
| GM2804 | 169 | 0.0489 | 4.5 | 1.16 | 1.16 | 0.0565 | **7.3** | 159 | 73 | **0.19** | 1.24 | 9.0 |
| GM3506 | 141 | 0.0587 | 2.8 | 1.86 | 1.5 | 0.088 | **4.7** | 133 | 47 | **0.28** | 1.30 | 9.5 |
| GB2208 KV128 | 128 | 0.0646 | 7.2 | 0.72 | 0.72 | 0.0466 | **8.8** | 121 | 88 | **0.09** | 0.78 | 5.6 |
| GL30 (Kt from 8.27/255) | 255 | 0.0324 | 0.765 | 6.8 | 1.5 | 0.0486 | **8.5** | 240 | 85 | **0.35 (full 1.5 A still available)** | 0.35 | 2.6 |
| GL30 (listed Kt) | — | 0.038 | 0.765 | 6.8 | 1.5 | 0.057 | **7.2** | 240 | 72 | **0.35** | 0.34 | 2.6 |
| DFRobot 2804 | 220 | 0.0376 | 2.55 | 2.04 | 1.5 | 0.0564 | **7.3** | 207 | 73 | **0.31** | 1.19 | 8.6 |
| Generic 2204 260KV | 260 | 0.0318 | unknown | ? | 1.5 if R_phase ≤ 3.4 Ω | 0.0477 | **8.6** | 245 | 86 | ~0.35 if R is low | ? | ? |

Example arithmetic, GBM2804H-100T:
- Kt = 8.27/155 = 0.0534 Nm/A. R_phase = 10/2 = 5 Ω. I_stall = 5.20/5 = 1.04 A, so 1.5 A is out of reach.
- Motor torque at stall = 0.0534 × 1.04 = 0.0555 Nm. N = 0.35 / (0.85 × 0.0555) = 7.4.
- ω0 = 155 × 9 × 0.1047 = 146 rad/s. At a 10 rad/s joint, the motor turns at 74 rad/s, which is 51% of ω0. That leaves 1.04 × 0.49 = 0.51 A.
- Joint torque = 0.51 × 0.0534 × 7.4 × 0.85 = 0.17 Nm.
- Standing: τ_m = 0.13 / (0.85 × 7.4) = 0.0207 Nm, I = 0.39 A, P = 1.5 × 0.39² × 5 = 1.1 W.

Example arithmetic, GL30:
- Kt = 8.27/255 = 0.0324 Nm/A. R_phase = 1.53/2 = 0.765 Ω, so I_stall at 9 V = 6.8 A and the 1.5 A cap is what binds.
- Motor torque = 0.0486 Nm. N = 0.35 / (0.85 × 0.0486) = 8.5.
- At a 10 rad/s joint, the motor turns at 85 rad/s, 35% of 240. 6.8 × 0.65 = 4.4 A would still be available, more than 1.5 A, so the full 0.35 Nm holds at 10 rad/s.
- Standing: τ_m = 0.018 Nm, I = 0.555 A, P = 1.5 × 0.308 × 0.765 = 0.35 W.

**Reading the table [est]:**
- **Speed limit on ratio.** Keeping the motor at no more than about 70% of ω0 at a 10 rad/s joint caps N at roughly 0.07 × ω0. That gives about 10:1 for the 100T 2804s, 9:1 for the GM3506, 8.5:1 for the GB2208, 14:1 for the DFRobot 2804, and 17:1 for the GL30 and 2204 260KV. The 100T and 80T windings are squeezed from both sides at 9 V. They need about 7.5:1 or more for torque and about 10:1 or less for speed, and their current is limited by voltage across the whole range.
- **Walking at 6 rad/s instead of 10.** At 7.4:1 the GBM2804H turns at 44 rad/s, 30% of ω0, so about 0.73 A and 0.25 Nm are available. That is enough for walking with 0.13 Nm continuous, but not for a hop.
- **Where the burst energy goes.** At peak, a high-resistance motor turns most of its electrical power into heat. Six GBM2804H lift motors at 1.04 A make about 6 × 8.1 = 49 W of copper heat, which would use up the whole 40–60 W supercapacitor burst. Six GL30s at 1.5 A make about 6 × 2.6 = 15.5 W of heat, plus about 6 × 3.5 = 21 W of mechanical power (0.35 Nm × 10 rad/s), for about 37 W before driver losses. That fits the burst.
- **Standing load on the 22.5 W budget.** Six lift joints holding 0.13 Nm cost about 2.1 W with GL30s and about 6.7–7.4 W with 2804-100T types, before driver and logic losses.
- **Swing joints** need only 0.10–0.15 Nm. At the same ratios they would draw roughly 30–45% of the peak current. Any of the 2804-class motors at about 7:1 covers them.
- **Raising the bus voltage** helps high-resistance motors almost linearly. At 12 V, I_stall for the GBM2804H would be about 6.93/5 = 1.39 A. The bus is fixed at 9 V here, so this is only noted, not proposed.
- **The 1.5 A cap is what holds back low-resistance motors.** If the drivers could briefly allow 3 A from the supercapacitors, a GL30 could reach 0.35 Nm at about 4.3:1, which would be much more backdrivable. This is a choice about the current limit, not about the motor.

### Gaps
- Measured Kt, KV, phase resistance and inductance are needed for each candidate. The resistance convention (per phase or phase-to-phase) is not stated for any iFlight motor, and the DFRobot listing gives two values.
- Rotor inertia was not found for any motor, so reflected inertia (rotor inertia × N²) and impact loads at landing could not be estimated.
- Cogging torque was not found in numbers for any candidate (GL30 is only described as "low cogging").
- Thermal resistance and allowed continuous current are not given for any gimbal motor except the GL30's rated current.

## Q3. Which gear reductions fit a 35–40 mm hip: printed planetary, printed cycloidal, metal planetary heads, capstan or cable, and published small-robot designs?

### Takeaway
A single-stage printed planetary of about 5:1 to 9:1 on a gimbal motor is the most proven pattern at this size. The CM6 arm uses 5:1–9:1 stages, and TipTapMotor (MIT licence) uses 8:1 on a GBM3506 in a 47 mm cube. Printed cycloidal drives give more reduction per volume but show about 1–2° of backlash unless preloaded. Capstan drives near 6–8:1 have zero backlash but need drum diameters far above 40 mm. No small metal planetary gearhead made for gimbal outrunners was found.

### Cited Findings
**Printed planetary**
- **TipTapMotor** (DarrenLevine, **MIT licence**): modular 3D-printed, torque-controllable BLDC actuator with an iPower GBM3506H-130T motor and an 8:1, three-planet printed planetary. Size 47 × 47 × 47 mm, about $74 per actuator. Includes a small diametric encoder magnet and a "DirectServo" PCB. A tuned Cura profile is used for tight gear tolerance. Mass, torque and backlash are not stated **[GitHub]** — [TipTapMotor](https://github.com/DarrenLevine/TipTapMotor)
- **CM6 compliant arm**: uses BLDC gimbal motors with single-stage 3D-printed planetary gearboxes of 5:1 to 9:1, chosen so the arm stays passively compliant. Each joint has an "S-Drive" (L6234 driver, AS5040 10-bit encoder, STM32F103C). The first version cost about $1000 in materials **[project page]** — [Hackaday.io CM6](https://hackaday.io/project/180588-cm6-compliant-3d-printed-robotic-arm); [PCBWay CM6](https://www.pcbway.ru/project/shareproject/CM6___Compliant_3D_printed_robotic_arm.html)
- A budget quasi-direct-drive build uses a printed planetary with cycloidal tooth profiles to reduce backlash and tooth stress **[news]** — [Hackaday, July 2025](https://hackaday.com/2025/07/14/a-budget-quasi-direct-drive-motor-inpired-by-mits-mini-cheetah/)
- A 2023 IEEE SII paper evaluated a QDD actuator with a 3D-printed 8:1 planetary. It notes that numbers on printed reduction gears had been scarce **[paper]** — [SII 2023](https://t2r2.star.titech.ac.jp/rrws/file/CTT100885960/ATD100000413/SII2023.pdf); [ResearchGate](https://www.researchgate.net/publication/368580845_Experimental_Evaluation_of_a_Quasi-direct-drive_Actuator_with_a_3D-printed_Planetary_Gear_Reducer)
- QDD systems usually use 3:1 to 10:1. One project chose cycloidal over printed planetary because small printed teeth concentrate stress and can fail suddenly under shock **[GitHub]** — [JeongSeoJin quasi-direct-drive-actuator](https://github.com/JeongSeoJin/quasi-direct-drive-actuator)
- Printed gear clearance: about 0.1 mm of added clearance worked for one builder. A printed planetary showed less than 0.01 mm of play at 10 cm under light load, but visible movement under force **[maker test]** — [How To Mechatronics planetary](https://howtomechatronics.com/how-it-works/how-planetary-gears-work-3d-printed-planetary-gearbox-design-and-test/)
- Printed drive efficiency about 84% **[maker test]** — [How To Mechatronics](https://howtomechatronics.com/how-it-works/what-is-the-best-3d-printed-drive-for-your-next-robotic-project/)
- Reference for metal gears (not printed): single-stage planetary backlash 0.010 rad (0.57°), compound planetary 0.046 rad (2.6°); predicted efficiency 96% single-stage and 93.8% compound **[paper]** — [COMPAct, arXiv 2510.07197](https://arxiv.org/pdf/2510.07197)
- Materials: in one test of an 80:1 printed compound planetary, the PLA version showed very little wear while the resin one failed early **[news]** — [Hackaday 2022](https://hackaday.com/2022/02/10/resin-printed-gears-versus-pla-which-is-tougher/). A robotics team found PLA gears wore badly after one match, while nylon held up **[forum]** — [Chief Delphi](https://www.chiefdelphi.com/t/printing-a-404-1-planetary/358482)

**Printed cycloidal**
- A printed cycloidal gearbox ran smoothly with about 1–2° of backlash. The outer pin holder was the part most sensitive to print errors **[project log]** — [Hackaday.io 165592](https://hackaday.io/project/165592)
- University of Twente MSc work, later in IEEE RA-L: two anti-backlash designs for printed cycloidal drives (a conical disc, and a split non-pinwheel). They cut backlash about 2–3× and raised friction by less than 2×, with adjustable preload **[thesis/paper]** — [Twente essay 103595](https://essay.utwente.nl/essays/103595); [Twente research page](https://research.utwente.nl/en/publications/anti-backlash-mechanisms-for-cycloidal-drive-robotic-actuators-de/)
- Rollers wear quickly through printed plastic unless they run on bearings. An inverted "three ring" design uses steel dowel pins as rollers instead **[news]** — [Hackster](https://www.hackster.io/news/this-inverted-cycloidal-drive-is-perfect-for-3d-printed-robots-9ff7c3636e8f)
- OpenMutt (Embry-Riddle, 2023): open-source printed quadruped with 12 brushless motors, each driving a cycloidal gearbox **[university page]** — [ERAU OpenMutt](https://commons.erau.edu/exhibit/the-student-research-symposium-virtual-exhibit/the-student-research-symposium-2023/openmutt-3d-printed-robotic-quadruped/)

**Capstan / cable**
- Aaed Musa's CARA robot dog: printed capstan joints at close to 8:1, Eaglepower 90KV motors. Steel cable fatigued and snapped after a few hours, so it was replaced with Dyneema DM-20 rope (very low creep) **[news]** — [Hackster CARA](https://www.hackster.io/news/aaed-musa-s-capstan-drive-equipped-robot-dog-amazes-us-9ae9cea22714); [Gigazine](https://gigazine.net/gsc_news/en/20250725-robot-dog-using-rope/)
- A student quadruped leg used a 1:6 capstan with an 18 mm small drum and a 108 mm big drum, on 8308 outrunners **[student report]** — [PWr report 2022](https://kcir.pwr.edu.pl/~witold/ip/2022_reports/Jakub_Tomaszewski.pdf); [PWr report 2021](https://kcir.pwr.edu.pl/~witold/ip/2021_reports/Lickindorf.pdf)
- An 8:1 capstan needs about eight wraps of cable for 360° of output, with about 2 mm between windings **[paper]** — [arXiv 2507.15693](https://arxiv.org/pdf/2507.15693)
- A misalignment of a fraction of a millimetre caused binding, motor overheating and loss of tension in one build **[blog]** — [Aaron Newman, Substack](https://aaronnewmanb.substack.com/p/capstan-drives-affordable-precision)
- A thesis on capstan drives for legged jumping links the best capstan radius to rotor inertia. In its simulation, jump height peaked at a 2 mm radius **[thesis]** — [Ridgway MASc 2023](https://www.dynsyslab.org/wp-content/papercite-data/theses/MASc-Ridgway-2023.pdf)

**Belt (open small-legged-robot reference)**
- ODRI Solo actuator module v1 (**BSD 3-Clause**, © Max Planck Gesellschaft and New York University 2019–2021):
  - Motor: T-Motor Antigravity 4004 300KV, 53 g, 12 pole pairs, 18 slots, 45 mm rotor.
  - Drive: two stages of 3:1 AT3 timing belt (4 mm and 6 mm wide), 9:1 total. Pulleys must be SLA, Polyjet or Multijet printed for accurate teeth.
  - Output: 2.5 Nm at 12 A. Module weighs 150 g.
  - Encoder: Broadcom AEDT-9810 optical, 5000 CPR (20000 counts per revolution), about 26 mm code wheel.
  - **[GitHub]** — [open_robot_actuator_hardware](https://github.com/open-dynamic-robot-initiative/open_robot_actuator_hardware); [actuator module v1 README](https://github.com/open-dynamic-robot-initiative/open_robot_actuator_hardware/blob/master/mechanics/actuator_module_v1/README.md)
- A review of quadruped actuators notes that Solo's belt transmission slips under high loads **[paper]** — [arXiv 2503.14255](https://arxiv.org/pdf/2503.14255)

**Metal planetary gearheads**
- No 2804 gimbal motor sold with a planetary gearbox, and no gearhead kit for one, was found **[search result]** — [search summary covering iFlight, DFRobot and RobotShop listings](https://shop.iflight.com/ipower-gm2804-gimbal-motor-with-as5048a-encoder-pro288)
- The only gimbal-class unit found with a metal planetary built in is the Steadywin GIM3505 (8:1, 9:1 or 36:1; 15 arcmin backlash; Ø43 mm). See Q5 **[seller]** — [OpenELAB GIM3505-8](https://openelab.com/products/steadywin-gim3505-8-robot-gear)

### Inferences
- **Size fit [est].** A single-stage planetary sized to a 35 mm motor (ring about 35–38 mm across, under 15 mm deep) can reach 5:1–8:1 with a sun of 9–12 teeth and a ring of 45–72 teeth at module 0.5–0.6. That fits the 35–40 mm hip and matches what CM6 and TipTapMotor did. The 8:1 point that most candidates in Q2 need is at the top of that range. 9:1 or more points to a two-stage, compound or cycloidal stage.
- **Cycloidal** suits 8:1–15:1 in a thin disc stage, but the 1–2° backlash of an unpreloaded printed design is large next to the ±25° swing. The Twente preload approach (2–3× less backlash) is the published fix. Shock loads at hop landings favour cycloidal over small printed planetary teeth, according to the JeongSeoJin rationale.
- **Capstan** at 6–8:1 with an 18 mm motor drum needs a 108–144 mm output drum. That cannot sit at a 35–40 mm hip. It only works if the output drum is the thigh itself, and the CARA and PWr results show alignment and rope creep are real costs.
- **Belts** (the Solo pattern) move the motor off the joint axis. That could free hip space, but they slip under shock, and the 3 mm pitch pulleys need resin printing.
- **Licences.** TipTapMotor (MIT) and ODRI (BSD-3) are permissive and safe to build on. CM6's licence was not confirmed in this session, and its repo URL tried here returned 404. No non-commercial or copyleft licence was found on the designs above, but CM6, OpenMutt and the cycloidal projects have not been checked.
- **Mass of a printed stage [est, no source]:** about 6–12 g of PETG or nylon gears and carrier for a 35 mm stage, plus an output bearing and screws. Measure this on a test print.

### Gaps
- No measured backlash or efficiency was found for a printed planetary of 5:1–8:1 at this size. Test it.
- No small metal planetary gearhead (22–36 mm) made to take a gimbal outrunner was found, and no prices.
- Licences for CM6, the cycloidal Hackaday projects and OpenMutt were not confirmed.
- The Quad Bai Tiny actuator design (see Q6) was not retrieved, and it may be the closest published match in size.

## Q4. Which magnetic encoder ICs and breakout boards suit this, and what magnets and air gaps do they need?

### Takeaway
The MT6701 (14-bit; SSI, I2C, ABZ, UVW, PWM and analog; 3.3–5 V; about $7 for a module with magnet) is the cheapest good fit, read over SSI. The MT6835 (21-bit, 16 MHz SPI, self-calibration to ±0.07°) and AS5047P (14-bit SPI with ABI, 28 krpm) are better grades. The AS5600 is cheap but its I2C interface limits FOC loop rate and adds noise. All of them read a diametric magnet, typically 6 × 2.5 mm NdFeB.

### Cited Findings
**MagnTek MT6701**
- 14-bit absolute angle over I2C or SSI. Incremental ABZ programmable from 1 to 1024 pulses per revolution. UVW output programmable from 1 to 16 pole pairs. Max rotation speed 30,000 rpm in the Rev 0.1 datasheet **[datasheet]** — [MT6701 datasheet Rev 0.1](https://voltiq.ru/datasheets/MT6701.pdf)
- A later revision, quoted by a distributor, gives 55,000 rpm and an output delay under 5 µs **[distributor]** — [Compel MT6701QT-ACD](https://www.compel.ru/infosheet/MAGNTEK/MT6701QT-ACD)
- Has built-in EEPROM; packages SOP-8 and QFN 3×3-16L (Chinese datasheet v1.8) **[datasheet]** — [MagnTek datasheet v1.8 via LCSC](https://atta.szlcsc.com/upload/public/pdf/source/20240409/995E18415A669787D9A549675AADF1FD.pdf); SOP-8 body about 5 × 3.9 × 1.75 mm — [JLCPCB part C3003196](https://jlcpcb.com/partdetail/MT6701CT-STD-R/C3003196)
- The Arduino library's SSI clock defaults to 1 MHz with a maximum of 8 MHz. This is a library limit, not a datasheet limit **[GitHub]** — [MT6701-arduino](https://github.com/I-AM-ENGINEER/MT6701-arduino)
- Module: 3.3–5.0 V, 14-bit, Z-axis air-gap detection output, ships with a diametric NdFeB magnet, ₹299 **[seller]** — [iFuturetech](https://ifuturetech.org/product/mt6701-high-speed-and-high-precision-magnetic-encoder-module/); module with ABZ 1–1024 ppr at $7.10 **[seller]** — [Walmart](https://www.walmart.com/c/kp/angle-encoder)
- An open MT6701 SSI board is 14 × 14 mm, 2 layers **[project]** — [PCBWay, Saulius Stasys](https://www.pcbway.com/project/shareproject/MT6701_SSI_9591f04a.html)
- A SimpleFOC maintainer recommends SSI or ABZ over I2C for precise control **[forum]** — [SimpleFOC MT6701 support thread](https://community.simplefoc.com/t/mt6701-magnetic-position-encoder-support/2618); ESP-SimpleFOC supports the MT6701 over I2C and SPI **[docs]** — [Espressif ESP-SimpleFOC](https://docs.espressif.com/projects/esp-iot-solution/en/latest/motor/foc/esp_simplefoc.html)

**MagnTek MT6835**
- 21-bit. 4-wire SPI up to 16 MHz. 3.3–5.0 V (programmable in EEPROM). 120,000 rpm max. −40 to 125 °C **[distributor/seller]** — [Compel MT6835GT-STD](https://www.compel.ru/infosheet/MAGNTEK/MT6835GT-STD); [Fruugo NZ module listing](https://www.fruugo.co.nz/21-bit-magnetic-encoder-module-with-pwmspi-interface-for-brushless-motor-applications-high-precision-position-sensing-solution/p-505457310)
- Modules are sold with PWM and SPI outputs and marketed as AS5048 replacements **[seller]** — [Fruugo module listing](https://www.fruugosaudiarabia.com/mt6835-magnetic-encoder-module-21-bit-high-precision-pwmspi-interface-compatible-with-brushless-motor-replace-compatible-with-as5048-a/p-513706072-1048807342)
- Self-calibration at constant speed brings INL to ±0.07°, or ±0.02° with non-linearity compensation (NLC) **[distributor]** — [Ineltek MT6835](https://www.ineltek.com/en/magntek-novosense-mt6835-encoder/)
- SimpleFOC user report: about ±0.2° jitter in angle mode before calibration. The chip's own calibration (pull the CAL pin high, rotate 64 turns, check the PWM duty for success) beat SimpleFOC's software lookup table. A maintainer says software calibration only helps with large magnet misalignment and needs MCU memory **[forum]** — [SimpleFOC MT6835 performances](https://community.simplefoc.com/t/mt6835-performances/8103); [SimpleFOC "Is calibration necessary"](https://community.simplefoc.com/t/is-calibration-necessary/4962)
- MagnTek now appears under Novosense branding in distributor material **[distributor]** — [Ineltek](https://www.ineltek.com/en/magntek-novosense-mt6835-encoder/); [Avnet Novosense NPI](https://www.avnet.com/apac/products/new-products/npi/aac-202509-novosense/)

**ams OSRAM (now listed under Infineon) AS5047P**
- 14-bit core. Up to 28 krpm. 4-wire SPI for the 14-bit absolute angle and for programming non-volatile settings. ABI incremental up to 1000 ppr (decimal) or 1024 ppr (binary), programmable down to 25 ppr. DAEC gives a maximum of 0.34° at a constant 28,000 rpm (excluding INL) **[datasheet/distributor]** — [AS5047P datasheet (Infineon-hosted)](https://www.infineon.com/row/public/documents/24/49/infineon-as5047p-datasheet-en.pdf); [ams product page](https://ams-osram.com/as5047p); [DigiKey](https://www.digikey.com/en/product-highlight/a/ams/as5047p-magnetic-position-sensor)
- The AS5047P-TS_EK_AB adapter board is fully assembled, uses a dual-row 2.54 mm header, and ships with an AS5000-MD6H-2 diametric magnet (D6 × 2.5 mm NdFeB, Bomatec). The motor-board kit has magnet holders for 10, 8, 6 and 5 mm magnets **[distributor]** — [Farnell AS5047P-TS_EK_AB](https://jp.farnell.com/en-JP/ams-osram-group/as5047p-ts-ek-ab/adapter-board-kit-position-sensor/dp/3976974); [Farnell kit datasheet](https://www.farnell.com/datasheets/3723591.pdf)

**ams AS5600 / AS5600L**
- 12-bit analog or PWM output. I2C for programming (and reading). Diametric on-axis magnet. Programmable start and stop angles **[datasheet]** — [AS5600 datasheet](https://www.infineon.com/assets/row/public/documents/24/49/infineon-as5600-datasheet-en.pdf); [AS5600L datasheet](https://www.infineon.com/assets/row/public/documents/24/49/infineon-as5600l-datasheet-en.pdf)
- Typical magnet: 6 mm diameter × 2.5 mm, air gap about 0.5–3 mm. Use the MD/ML/MH status bits and the AGC value to check the gap. This is from a third-party site, not ams **[third-party]** — [tinkered.ai AS5600](https://tinkered.ai/components/as5600)
- The AS5600L adapter board has 4 × 2.6 mm mounting holes **[distributor]** — [Farnell AS5600L adapter datasheet](https://www.farnell.com/datasheets/3723584.pdf); [RS AS5600L-WL_EK_AB](https://uk.rs-online.com/web/p/sensor-development-tools/2329697)
- Module prices: about $6.68 single with magnet, about $12.55 for 8, $7.56 elsewhere **[seller]** — [Walmart AS5600 module](https://www.walmart.com/ip/AS5600-Magnetic-Encoder-Module-Magnetic-Induction-Angle-Measurement-Sensor-Module-FOC-12Bit-High-Precision-Sensor/17695511953)
- SimpleFOC problems with the AS5600:
  - The blocking I2C read pauses the rotating field and causes audible noise.
  - I2C with default Arduino usage limits the loop to about 1–2 kHz.
  - Users struggle to get above about 100 rad/s.
  - Fixes are Wire.setClock(1000000) or a filter setting outside the library.
  - **[forum]** — [SimpleFOC: sensor update too long](https://community.simplefoc.com/t/sensor-update-taking-too-long-with-as5600-causing-vibration/3116); [SimpleFOC: noisy output](https://community.simplefoc.com/t/as5600-noisy-output-unstable-velocity/1325); [SimpleFOC: >100 rad/s](https://community.simplefoc.com/t/cannot-get-system-over-100rad-s-with-as5600-sensor/4290?page=2)

**Infineon TLE5012B / TLI5012B**
- GMR-based. 15-bit absolute (0.01°). Max angle error 1.0° over life and temperature with auto-calibration (TLE5012B Rev 2.1, 2018) **[datasheet]** — [TLE5012B datasheet (RS)](https://docs.rs-online.com/1fce/A700000014359312.pdf)
- TLI5012B E1000: 42.7 µs angle update, IIF incremental at 12-bit (0.088° per count), 1.9° max error with auto-calibration, SPI/IIF **[maker]** — [Infineon TLI5012B E1000](https://www.infineon.com/cms/en/product/sensor/magnetic-sensors/magnetic-position-sensors/angle-sensors/tli5012b-e1000/); [Mouser](https://www.mouser.in/new/infineon/infineon-tli5012b-angle-sensor)

**AS5048A (bundled with iPower GM-series motors)**
- iFlight sells the GM2804 and GM3506 with an AS5048A in an aluminium housing; the encoder version of the GM2804 is 25 mm tall and 51 g **[maker]** — [iFlight GM2804 w/ encoder](https://shop.iflight.com/ipower-gm2804-gimbal-motor-with-as5048a-encoder-pro288)

**SimpleFOC Mini (driver, for context only)**
- Max 3 A, 8–35 V, **no current sensing** **[docs]** — [SimpleFOC Mini docs](https://docs.simplefoc.com/simplefocmini)

### Inferences
- **For this robot [est]:** an MT6701 read over SSI at 1–8 MHz, or over ABZ into ESP32 PCNT hardware, meets the FOC commutation need cheaply. Its 30–55 krpm rating is far above the motor's top speed of about 2300 rpm at 9 V. Use the MT6835 (16 MHz SPI, 21-bit, self-calibration) if a later step needs very fine angles for the spring-like stiffness control. AS5600 over I2C should be avoided for 12 FOC loops.
- **Encoder placement.** With the encoder on the motor before an N:1 gearbox, the output angle is known only modulo 360°/N after power-up. The joint then needs homing (against a hard stop with current limiting) or a second output-side encoder. Integrated actuators solve this with dual encoders (see Q5). The ±25° swing at 7:1 covers 175° of motor rotation, so a single motor-side absolute encoder plus a known start pose could be enough, provided the robot always powers up near its rest pose. This is a design choice for the owner.
- **Magnet.** The common standard is a diametric NdFeB disc of 6 × 2.5 mm, which is what ams ships with the AS5047P adapter. On a hollow-shaft gimbal motor the magnet goes in a printed cap on the rotor end, as on the 2804 + AS5600 kits with a 5.5 mm bore magnet ring.
- **Board size.** A 14 × 14 mm MT6701 board (PCBWay project) fits behind a 35 mm motor. Plan an M2 or M2.5 pair of holes on a printed carrier, since no common module drawing was found.

### Gaps
- The magnetic field range in mT and the recommended air gap from the official datasheets were not found for any IC. The 0.5–3 mm gap for the AS5600 comes from a third-party site.
- The AS5047P's UVW and PWM outputs, its supply options, and the AS5048A's interface details were not re-checked in this session.
- No board outline or mounting-hole drawing was found for common MT6701, MT6835 or AS5600 modules.
- No price was found for loose 6 × 2.5 mm diametric magnets, or for MT6835 modules in USD or NZD (a Fruugo NZ listing exists, but no price was captured).

## Q5. Are there integrated joint actuators (motor + gearbox + encoder + FOC driver) of 40 mm diameter or less and 60 g or less?

### Takeaway
None were found. The smallest integrated units are the MyActuator RMD-L-4005 (39.6 × 23 mm, 65 g, but direct drive, peak 0.25 Nm) and the Steadywin GIM3505-8 (Ø43 × 30 mm, 97 g with driver, 8:1, 0.65 Nm rated, 1.27 Nm stall, CAN/RS-485). Everything geared and integrated weighs 84–400 g, so twelve of them would be 1–5 kg.

### Cited Findings
- **Steadywin GIM3505-8**:
  - Size and mass: Ø43 × 23.6 mm and 84 g without driver; Ø43 × 30 mm and 97 g with the GDS34 driver.
  - Gearing and torque: 8:1 planetary, 0.65 Nm nominal, 1.27 Nm stall, 384 rpm max output.
  - Electrical: 24 V nominal (12–48 V), 29 W, rated current 1.53 A, peak 3.99 A, 14-bit encoder.
  - Mechanical: backlash 15 arcmin, IP54, −20 to +80 °C, max axial load 75 N, radial 300 N.
  - **[seller]** — [OpenELAB GIM3505-8](https://openelab.com/products/steadywin-gim3505-8-robot-gear); [AIFitLab](https://aifitlab.com/products/steadywin-gim3505-8-planetary-reducer-servo-motor); [Robotics Center](https://www.roboticscenter.ai/ar/store/product/steadywin-gim3505-8-planetary-reducer-servo-motor)
- GIM3505 versions: V1.0 (48-slot star winding) works only over SPI and not with the GDS/GDZ drivers. V1.1 supports CAN and RS-485 with the GDS34/GDZ34 drivers. The driver name appears as both GDS34 and GDZ34 **[seller]** — [OpenELAB IT](https://openelab.io/it/products/steadywin-gim3505-8-planetary-gear-motor)
- GIM3505 price: $56.00 for the V1.0 motor only, no driver, backordered **[seller]** — [AIFitLab](https://aifitlab.com/products/steadywin-gim3505-8-planetary-reducer-servo-motor); [Robotics Center](https://www.roboticscenter.ai/ar/store/product/steadywin-gim3505-8-planetary-reducer-servo-motor)
- GIM3505-9: 9:1, 0.71 Nm rated, 1.95 Nm peak, 380 rpm. GIM3505-36: 36:1, 3.12 Nm rated, 8.01 Nm peak, 97 rpm **[seller]** — [Robotics Center -9](https://www.roboticscenter.ai/ar/store/product/steadywin-gim3505-9-motor); [Robotics Center -36](https://www.roboticscenter.ai/ar/store/product/steadywin-gim3505-36-motor)
- Steadywin also sells GIM3510, GIM4305, GIM4310 and GIM4315 planetary joint modules (weights not found) **[maker]** — [Steadywin planetary series](https://steadywin-motor.com/collections/planetary-reduction-series)
- **MyActuator RMD-L-4005-25T**: 39.6 × 23 mm, 65 g, 0.07 Nm nominal, 0.25 Nm peak, 100 W, DRC06 driver **[seller]** — [Amazon](https://us.amazon.com/Myactuator-RMD-L-4005-25T-12V-24V-Brushless-Gimbal/dp/B0D4CXY3K6); 12–24 V, 18-bit encoder **[seller]** — [rcdrone.top](https://rcdrone.top/products/myactuator-rmd-l-4005-25t-12v-24v-high-speed-100w-brushless-dc-servo-motor); CAN bus **[seller]** — [RobotShop](https://www.robotshop.com/products/myactuator-rmd-l-4005-25t-brushless-dc-servo-motor-bldc-can-bus-mc-x-100-o); RS-485 and CAN options, peak 0.25 Nm **[seller]** — [Dings Motion USA 4005](https://www.dingsmotionusa.com/store/p/rmd-l-4005)
- **MyActuator RMD-L-4010**: 92 g, 0.15 Nm (22T, 24 V, 1120 rpm) **[seller]** — [Cutting Edge G](https://www.cuttingedgeg.com/product/myactuator-l-4010-22t-integrated-servo-motor-24v-0-15nm-1120rpm-for-robotics-drones-gimbals-and-lidar-systems); listed with an "open protocol RS485 driver, 5 A, 14-bit" **[seller]** — [SMC Powers](http://shop.smc-powers.com/RMD-L4010.html); peak 0.33 Nm per Dings **[seller]** — [Dings Motion USA 4010](https://www.dingsmotionusa.com/store/p/rmd-l-4010)
- RMD-L-4015-20T V3 is listed in one title at 0.49 Nm nominal and in a summary at 0.22 Nm (conflict). RMD-L-5010-35T: 135 g, 0.26 Nm nominal, 0.65 Nm peak. The L series spans 20–140 mm in diameter. All are direct drive **[seller]** — [RobotShop 4015](https://eu.robotshop.com/products/myactuator-rmd-l-4015-20t-v3-micro-brushless-dc-out-rotor-servo-motor); [RobotShop 5010](https://www.robotshop.com/products/myactuator-rmd-l-5010-35t-brushless-dc-servo-motor)
- MyActuator RMD-X2-P28-7-E: 0.26 kg, 28.17:1, 24 V, 2.5 Nm rated, 7 Nm peak, 142 rpm rated, EtherCAT **[seller]** — [OpenELAB](https://openelab.com/products/myactuator-rmd-x2-p28-actuator); [RobotShop EU](https://eu.robotshop.com/products/myactuator-rmd-x2-p28-7-e-bldc-actuator-281-planetary-reduction-ethercat)
- **LKMTECH** (the company name is LKMTECH, not LKTECH):
  - MS4005 v3: 65 g motor, 12 V, 0.07 Nm rated, 1090 rpm no-load, matched to a separate DS40v3 driver (6–20 V).
  - MG4005E-i10-V3: 183 g, 24 V, 1 Nm rated, 1:10 PG4210 gearbox, 7.4–32 V, RS-485 or CAN, 18-bit motor encoder plus 14-bit output encoder.
  - MG4005-V2: 154 g, 1:10, 1 Nm, 18-bit.
  - **[seller]** — [Robotics Center MS4005](https://www.roboticscenter.ai/ar/store/product/lkmtech-ms4005-v3-motor); [AIFitLab MG4005E](https://aifitlab.com/products/lkmtech-mg4005e-i10-v3-motor); [AIFitLab MG4005-V2](https://aifitlab.com/products/lkmtech-mg4005-v2-motor)
- **DAMIAO**:
  - DM-J3507-2EC: 46 mm OD, 150 g, 7:1, 0.8 Nm rated, 3 Nm peak, dual encoder, "MIT driver".
  - DM-S3519-1EC: 42 × 91.5 mm, 396 g, about 19.2:1, 3.5 Nm rated, 7.8 Nm peak.
  - A 1.5 kg "net weight" on retailer pages looks like shipping weight.
  - **[seller]** — [OpenELAB DM-J3507](https://openelab.com/products/damiao-brushless-servo-dm-j3507); [AIFitLab DM-J3507](https://aifitlab.com/products/damiao-dm-j3507-2ec-motor); [OpenELAB DM-S3519](https://openelab.com/products/damiao-brushless-servo-dm-s3519)
- Other small joint actuators found are all heavier: ATA RE-05 at 191 g (RE-00 at 310 g), FOC with CANopen or MIT protocol; SP series smallest 180 g, CAN; Arcsecond micro joint at 377 g **[maker]** — [ATA RE series](https://www.atarrobot.com/planetary-robot/re-Series-direct/re-planetary-joint-actuators.html); [ATA SP series](https://www.atarrobot.com/planetary-robot/sp-series/SP-planetary-robot-joint.html); [Arcsecond micro joint](https://www.arcsecondrobo.net/home/product/detail?id=95)
- CubeMars sells hollow-shaft planetary actuator modules, sizes not checked here **[maker]** — [CubeMars guide](https://www.cubemars.com/hollow-shaft-planetary-actuator-guide.html)

### Inferences
- **Nothing meets ≤40 mm and ≤60 g.** The best compromise is the GIM3505-8. It gives 0.65 Nm rated at the output, about twice what is needed, but it is Ø43 mm and 84–97 g, so twelve weigh 1.0–1.2 kg, more than the whole robot budget. It is also specified at 24 V. At 9 V its top output speed would be roughly 384 × 9/24 ≈ 144 rpm, about 15 rad/s with no load [est], which is only just above the 10 rad/s target.
- The RMD-L-4005 (39.6 mm, 65 g, 0.25 Nm peak direct drive) fits the diameter but needs about a 1.6:1 or larger extra reduction for 0.35 Nm, and it is too heavy.
- These units are useful only as reference designs. They show that dual encoders (motor and output) and planetary stages of 7–10:1 are normal at this scale.
- **Protocol openness.** DAMIAO is sold as using the "MIT" protocol (the open Mini Cheetah CAN format). ATA lists CANopen or MIT. An SMC Powers listing advertises an "open protocol" RS-485 driver for the RMD-L4010. Firmware for all of these appears to be closed. That is my reading of the listings; I did not confirm it.

### Gaps
- Official datasheets for MyActuator, Steadywin, LKMTECH and DAMIAO could not be fetched. Torque, mass and protocol details are seller-reported and partly conflicting (RMD-L-4010 peak, RMD-L-4015 nominal).
- GIM2208-type Steadywin units, CubeMars's smallest integrated actuator, and any HighTorque or other 2024–2026 micro actuators were not found or not checked.
- No price was found for the GDS34/GDZ34 driver or the GIM3505 V1.1.

## Q6. What have similar small legged robots (2020–2026) used, and what problems did they report?

### Takeaway
No hexapod built with gimbal motors was found. The closest builds are SimpleFOC desktop quadrupeds (Quad Bai Tiny, about 15 cm body), the CM6 arm (gimbal motors with 5–9:1 printed planetaries), TipTapMotor (GBM3506 with 8:1) and ODRI Solo (4004 outrunner with 9:1 belt). The problems they report are heat at sustained current, high winding resistance forcing high voltage, cogging at low speed, AS5600/I2C sensor noise, and backlash or wear in printed drives.

### Cited Findings
- **Quad Bai Tiny** (SimpleFOC forum, 2021): desktop quadruped with a body of about 15 cm, aiming for low-cost, torque-controllable hardware with a back-drivable actuator module. The first driver (ATmega328P) had no current sensing, so it was not truly torque-controllable. A new STM32 driver with CAN was in progress **[forum]** — [SimpleFOC Quad Bai Tiny](https://community.simplefoc.com/t/quadruped-bai-tiny/1313); the repo contains models, BOM, electronics, simulation and source **[project]** — [Hackaday.io 183900](https://hackaday.io/project/183900)
- **SimpleFOC "Selecting gimbal motors" thread**:
  - A builder planned a 12-DOF quadruped with cycloidal drives and estimated about 0.092 Nm from a gimbal motor, short of the 2 Nm / 120 rpm goal.
  - The builder worried the motors would "get too hot way too fast", and noted that RCTimer gives no continuous-current rating.
  - Replies: what matters is motor temperature, and brief bursts (jumps, landings) are fine if average power is manageable. High-resistance gimbal motors push you to drivers with external MOSFETs above 2 A. Choose more poles and lower KV for higher voltage and lower current.
  - **[forum]** — [SimpleFOC thread 5061](https://community.simplefoc.com/t/selecting-gimbal-motors-to-build-an-actuator-for-a-small-quadruped/5061); [SimpleFOC "Quadruped Robot"](https://community.simplefoc.com/t/quadruped-robot/4564)
- Cogging: it looks worse at low speed with no load, so judge it under real load. One of several drone motors tested was unusable with SimpleFOC, and replacing the motor fixed it **[forum]** — [SimpleFOC "Quadruped Robot"](https://community.simplefoc.com/t/quadruped-robot/4564); [SimpleFOC thread 5061](https://community.simplefoc.com/t/selecting-gimbal-motors-to-build-an-actuator-for-a-small-quadruped/5061)
- Low-cost hobby BLDC motors cause torque ripple at very low speed (ODRI architecture paper, 2019) **[paper]** — [arXiv 1910.00093](https://arxiv.org/pdf/1910.00093)
- A SimpleFOC quadruped by a Chinese developer: SimpleFOC was "good enough" to control it, after an RC-servo version failed on precision and torque **[forum]** — [SimpleFOC thread 472](https://community.simplefoc.com/t/quadruped-robot-using-simplefoc/472)
- A large SimpleFOC robot dog (about 25 kg, 12 DOF, custom motors and drivers, Dyneema DM20 rope transmission): its main limit was maximum torque, set by the turns-per-slot choice **[forum]** — [SimpleFOC thread 8249](https://community.simplefoc.com/t/made-a-large-quadruped-robot-using-custom-simplefoc-based-drivers-and-bldc-motors/8249)
- A Hackaday.io legged robot built on 5222 gimbal motors with a Minitaur-style deltoid leg: cheap controllers that handle large currents were hard to find **[project]** — [Hackaday.io 176419](https://hackaday.io/project/176419)
- Q8bot (UCLA, MIT licence): palm-sized quadruped on smart TTL servos, able to jump and climb moderate slopes **[paper]** — [arXiv 2508.01149](https://arxiv.org/html/2508.01149)
- mjbots quad A0: small jumping quadruped, Apache-2.0, custom moteus servos with Mini-Cheetah-style planetaries **[project/news]** — [Hackaday.io mjbots quad](https://hackaday.io/project/167845-mjbots-quad); [Hackster](https://www.hackster.io/news/the-mjbots-quad-a0-is-a-small-quadruped-capable-of-jumping-eda26a6382aa)
- ODRI Solo: BSD-3 hardware, 4004 300KV with 9:1 belt, 150 g module, 2.5 Nm at 12 A (see Q3) **[GitHub]** — [ODRI actuator v1](https://github.com/open-dynamic-robot-initiative/open_robot_actuator_hardware/blob/master/mechanics/actuator_module_v1/README.md); its belts slip under high load **[paper]** — [arXiv 2503.14255](https://arxiv.org/pdf/2503.14255)
- An ODrive-forum quadruped used original 3D-printed gearboxes inspired by OpenTorque **[forum]** — [ODrive forum](https://discourse.odriverobotics.com/t/experimental-quadruped-with-3d-printed-gearboxes/3659)
- Printed cycloidal: 1–2° backlash. Printed planetary: tooth failure under shock. Capstan: steel cable fatigue and binding from misalignment (see Q3) — [Hackaday.io 165592](https://hackaday.io/project/165592); [JeongSeoJin QDD](https://github.com/JeongSeoJin/quasi-direct-drive-actuator); [Hackster CARA](https://www.hackster.io/news/aaed-musa-s-capstan-drive-equipped-robot-dog-amazes-us-9ae9cea22714)
- Encoder noise with the AS5600 over I2C (see Q4) — [SimpleFOC AS5600 thread](https://community.simplefoc.com/t/sensor-update-taking-too-long-with-as5600-causing-vibration/3116)

### Inferences
- Every small torque-controlled legged robot that worked used real current sensing and a fast encoder interface. That matches the plan (FOC with current sensing). The SimpleFOC Mini, with no current sensing, is not suitable.
- The most-repeated advice (lower KV with more poles, and lower resistance rather than "100T" windings) matches the Q2 arithmetic. At 9 V, the winding's resistance matters more than its KV label.
- Heat is the stated worry, but Q2 shows that with low-resistance windings at about 8:1, standing losses are about 0.35 W per joint, which is small. Heat becomes real with high-resistance windings (about 1.1–1.3 W standing, 8–9 W at peak).

### Gaps
- No gimbal-motor hexapod was found, and no published joint mass or torque figures for a desktop-scale (about 1 kg) gimbal-motor legged robot.
- The Quad Bai Tiny repo, its motor model and its measured performance were not retrieved.
- The CM6 GitHub repo (motor models per joint, licence) could not be reached; the URL tried returned 404.

## Q7. Shortlist: which combination best meets the torque, speed, size and weight targets?

### Takeaway
No combination meets 0.35 Nm peak and 10 rad/s at 9 V and 1.5 A inside 25–30 g per joint. A realistic joint is about 45–55 g (motor 39–41 g plus gearbox, bearing and encoder), so twelve weigh about 0.55–0.65 kg. **First choice: CubeMars GL30 + single-stage printed planetary at about 8:1 + MT6701 over SSI.** It meets torque and speed with margin and has the lowest losses, at $51–102 per motor. **Budget choice: iPower GBM2804H-100T + about 7.5:1 + MT6701.** It walks well, but hops reach only about 0.17 Nm at 10 rad/s, at $18.99 per motor.

### Cited Findings
- GL30: Φ34.5 × 15.7 mm, 41 g, phase-to-phase resistance 1.53 Ω, Kt 0.038 Nm/A (listed), 0.28 Nm peak, $50.99 bare, $88–102 with encoder — [CubeMars](https://www.cubemars.com/product/gl30-kv290-gimbal-motor.html); [RobotShop](https://www.robotshop.com/products/cubemars-gl30-kv290-brushless-dc-motor); [CubeMars store](https://store.cubemars.com/products/gl30); [RobotShop w/ encoder](https://www.robotshop.com/products/cubemars-gl30-kv290-w-encoder)
- GBM2804H-100T: 35 × 15 mm, 39 g, 10 Ω, $18.99 — [iFlight store](https://shop.iflight.com/ipower-gimbal-brushless-motor-gbm2804h-100t-pro218)
- DFRobot 2804: 220 KV, 2.3/5.1 Ω, 34.5 × 19.5 mm, ships with AS5600 — [DFRobot wiki](https://wiki.dfrobot.com/fit1034/); [DFRobot](https://www.dfrobot.com/product-3005.html)
- 2204 260KV: 26 g, 28 × 13 mm, 600 mA max operating current — [Zbotic](https://zbotic.in/?p=463615); [Robu](https://robu.in/?p=57801)
- Printed single-stage planetary 5:1–9:1 on gimbal motors (CM6); 8:1 on GBM3506 (TipTapMotor, MIT) — [Hackaday.io CM6](https://hackaday.io/project/180588-cm6-compliant-3d-printed-robotic-arm); [TipTapMotor](https://github.com/DarrenLevine/TipTapMotor)
- MT6701 module about $7 with magnet, SSI/ABZ recommended over I2C — [Walmart](https://www.walmart.com/c/kp/angle-encoder); [SimpleFOC](https://community.simplefoc.com/t/mt6701-magnetic-position-encoder-support/2618)

### Inferences
**Ranked shortlist [est, based on Q2 arithmetic and the listed numbers]:**

| Rank | Combination | Ratio | Peak at stall | Torque at 10 rad/s | Standing loss per lift joint | Joint mass est. | Cost per joint est. | Main risk |
|---|---|---|---|---|---|---|---|---|
| 1 | CubeMars GL30 + printed planetary + MT6701 (SSI) | 8:1 (7.2–8.5) | 0.35 Nm at 1.5 A | 0.35 Nm | ~0.35 W | ~50–55 g | ~$60–110 | price; GL30 stock (official store sold out); encoder version mass conflict (41 vs 83 g) |
| 2 | DFRobot 2804 (220 KV) + printed planetary + MT6701 (swap out the AS5600) | 7.3:1 | 0.35 Nm at 1.5 A | ~0.31 Nm | ~1.2 W | unknown motor mass + ~10–15 g | unknown | mass and resistance not confirmed |
| 3 | iPower GBM2804H-100T + printed planetary + MT6701 | 7.4:1 | 0.35 Nm at ~1.04 A (voltage-limited) | ~0.17 Nm | ~1.1 W | ~50–55 g | ~$30 | weak hop push; 8 W of heat per motor at peak |
| 4 (swing joints only) | 2204 260KV + printed planetary + MT6701 | 8–9:1 | ~0.35 Nm if R_phase ≤ 3.4 Ω; otherwise ~0.15 Nm at 0.6 A | depends on R | unknown | ~35–40 g | ~$15–20 | resistance unknown; 600 mA rating |
| Excluded | GM3506 (40 mm, 64 g); GM2804 with housing (51 g); GB2208 (0.09 Nm at 10 rad/s); GL40/GM4108 (>46 mm); all integrated actuators (≥65 g) | — | — | — | — | — | — | — |

- **Joint mass build-up [est]:** motor 39–41 g, printed planetary 6–12 g, output bearing 3–6 g, encoder board and magnet 1–2 g, screws about 2 g, for about 51–63 g. Using GL30 or GBM2804H on the six lift joints and a lighter motor (2204 class) on the six swing joints gives roughly 6 × 55 + 6 × 40 ≈ 570 g. That is about 210–270 g over the 300–360 g target. The owner should decide whether to accept a heavier robot (about 1.1–1.2 kg, which then raises the needed torque), take the risk on 2204-class motors throughout with higher ratios (12–16:1, two-stage, less backdrivable), or reduce hop targets.
- **Ratio choice.** About 8:1 lands near the top of what a single printed planetary stage fits in 35–40 mm. It keeps reflected friction modest so the spring-like joint control stays backdrivable, and it suits the GL30's speed headroom (up to about 17:1 is allowed for speed).
- **Encoder.** Put an MT6701 on the motor side for commutation. Add homing, or a second cheap sensor on the output, to know the joint angle at power-up.
- **Before committing, bench-test** one GL30 and one GBM2804H on the real 9 V supply: measure Kt, phase resistance, cogging, and temperature rise holding 0.13 Nm through a printed 8:1 stage. The Q2 numbers rest on seller-listed KV and resistance, which ODrive developers warn are often wrong.

### Gaps
- Real joint masses for a printed 8:1 stage around these motors are not published. They need a test print.
- No source confirms the GL30's cogging or long-run temperature in legged use.
- Prices in NZD and New Zealand availability or shipping were not found.
