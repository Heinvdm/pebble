# Low-resistance motors let Pebble's hexapod hop

Pebble's 12-motor hexapod can reach its hop target, but only with joints about twice the planned weight. The best fit for each lift joint is a **CubeMars GL30 gimbal motor (Ø34.5 × 15.7 mm, 41 g, 1.53 Ω)** turning a **single-stage printed planetary gear of about 8:1**, read by a **14-bit MT6701 magnetic encoder**, with an open **SimpleFOC-microspora-style board (STM32G431 + TI DRV8316, 33 × 34 mm, MIT licence)** bolted behind every motor. At the fixed 9 V the Xiaomi bank gives, a motor's winding resistance, not its size, decides whether it can push 0.35 Nm at 10 rad/s. The GL30 can, losing about 0.35 W per joint while holding the walking load. The cheaper, high-resistance **iPower GBM2804H-100T** reaches only about 0.17 Nm at hop speed, so it is better kept for the six swing joints, whose vertical axes carry no weight. A finished joint comes out at roughly **51–63 g, not 25–30 g**, which puts the robot at about **1.1–1.3 kg** instead of 850–920 g. Nothing light closes that gap: no integrated actuator is under 60 g, and the 23 g Dynamixel XC330 smart servo tops out at about **2.7 W against the 3.5 W the hop push needs**. The rest of the body is settled:
- **Main board:** an ESP32-S3-Zero on a small carrier board.
- **Motor bus:** two CAN-FD buses through MCP2518FD chips, because the S3's own CAN is the older, slower kind and tops out near 300 Hz for 12 joints.
- **Sensors:** a ±32 g IMU, a VL53L4CD laser distance sensor for drop edges, and a separate digital IR sensor wired to a CH32V003 safety chip.
- **Power:** an INA228 power monitor, a CH224Q chip that asks the bank for 9 V, a TPS25947 electronic fuse that holds the bank to about 2.2 A, and four 10 F Maxwell supercapacitors that carry the hop.
- **Dock:** sprung pins carry plain USB-C lines from a multi-port charger, and one switch in the body moves the bank's single port from the motors to the dock. The bank is back to 80 % in about 51 minutes.

The owner now has to choose between heavier joints and a lower hop. Nearly every vendor number below came from search-result extracts rather than full pages, so build and measure one joint before ordering twelve.

*How to read the numbers.* Each figure carries a tag: **(O)** official, from the maker's datasheet, product page, repo or docs; **(S)** from a seller, distributor or other third-party page; **(F)** from a forum or community report; **(E)** an estimate, meaning arithmetic or judgement in the research notes or in this report. The research sessions could not open most vendor sites, so (O) and (S) figures mostly come from search-engine extracts of the linked pages. GitHub files and several datasheets were read directly. Prices are in US dollars unless marked, as seen on 17 October 2026, and the date each listing was captured is unknown. The power bank is the only part with New Zealand prices. Repo files are named by their repo path, such as `plans/new-bodies.md`.

## At 9 V, only low-resistance motors can push a 10 rad/s hop

The fixed 9 V bus decides which motors can work. Under field-oriented control (FOC), the smooth three-phase current control that makes motor current track torque, the most voltage a driver can put across one phase is about **9 ÷ √3 ≈ 5.2 V** (E). That caps the current. A winding of 5 Ω per phase cannot draw more than about **1.04 A even at standstill**, and it draws less once it turns, because a spinning motor makes its own opposing voltage. Gimbal motors are wound with many turns for slow camera work at 12–24 V (a "100T" motor has 100 turns per tooth), so most of them are starved at 9 V. The usual rule turns a motor's speed constant into torque: Kt (Nm per amp) ≈ 8.27 ÷ KV (rpm per volt). ODrive developers warn that makers "fudge their kv/kt", so it has to be measured ([ODrive forum](https://discourse.odriverobotics.com/t/question-about-torque-calculation/4295); [ODrive forum](https://discourse.odriverobotics.com/t/hover-board-hub-motor-less-torque-than-expected/6426)). The resistance iFlight lists is almost certainly measured across two leads, so the per-phase value is half of it (E).

| Motor | Size (mm) | Mass (g) | KV (rpm/V) | Listed resistance | Torque and speed listed | Price (USD) | Sources |
|---|---|---|---|---|---|---|---|
| **CubeMars GL30 KV290** | Ø34.5 × 15.7, 6 mm through-hole (O) | 41 (O); one seller lists 83 for the encoder version (S, conflict) | 255 listed despite the name (O) | 1.53 Ω across two leads (S) | 0.08 Nm rated, 0.28 Nm peak, 3,060 rpm no-load, 12 V rated (O); Kt 0.038 Nm/A (S); rated current 2.13 or 2.3 A (S, conflict) | 50.99 bare, sold out (O); 79 (S); 76–102 with encoder (S) | [CubeMars](https://www.cubemars.com/product/gl30-kv290-gimbal-motor.html), [T-Motor store](https://store.tmotor.com/goods-1123-GL30.html), [RobotShop](https://www.robotshop.com/products/cubemars-gl30-kv290-brushless-dc-motor), [CubeMars store](https://store.cubemars.com/products/gl30), [rcdrone](https://rcdrone.top/products/cubemars-gl30-kv290-brushless-gimbal-motor-6mm-hollow-shaft-41g-low-cogging-ip45), [MyBotShop](https://www.mybotshop.de/CubeMars-Robot-Dynamics-GL30-KV290-w-Encoder_1) |
| **iPower GBM2804H-100T** | Ø35 × 15, hollow shaft about 7 mm across (O/S) | 39 (O) | ~155 (E, from 1,468–1,622 rpm at 10 V (O)) | 10 Ω (O); one user measured 6.3 Ω (F) | 0.025–0.034 Nm load torque, 25 W max (O) | 18.99 (O); 28.46 (S) | [iFlight](https://shop.iflight.com/ipower-gimbal-brushless-motor-gbm2804h-100t-pro218), [ATGroup](https://atgroup.store/product/gbm2804h-100t/), [SimpleFOC forum](https://community.simplefoc.com/t/inductance-request-for-help-with-wiring/7824) |
| iPower GM2804 + AS5048A | Ø35 × 25 with encoder housing; hollow 6.5 mm bore (O) | 51 (42.3 motor only) (O) | ~169 (E) | 9 Ω (O) | 0.025–0.034 Nm (O) | ~39 (O); 40.99 (S) | [iFlight](https://shop.iflight.com/ipower-gm2804-gimbal-motor-with-as5048a-encoder-pro288) |
| iPower GM3506 | Ø40 × 17.8; hollow shaft 12 mm outside, 8.6 mm bore (O); M2.5 screws (F) | 64 (O) | ~141 (E) | 5.6 Ω (O) | 0.059–0.098 Nm (O) | not found | [iFlight](https://shop.iflight.com/ipower-motor-gm3506-brushless-gimbal-motor-pro967), [SimpleFOC forum](https://community.simplefoc.com/t/gimbal-motor-external-shaft/8162) |
| T-Motor GB2208 KV128 | Ø27.5 × 23 (S) | 39.5 with cable (S) | 128 (S) | 14.4 Ω (S) | sold for 100–300 g cameras (S) | not found | [RobotShop](https://www.robotshop.com/products/tmotor-gimbal-motor-gb2208) |
| DFRobot 2804 + AS5600 | Ø34.5 × 19.5 (O) | not found | 220 (O) | 2.3 Ω per phase and 5.1 Ω winding, both listed (O) | 0.029 Nm at 12 V, 2,600 rpm (O) | not found | [DFRobot wiki](https://wiki.dfrobot.com/fit1034/), [DFRobot](https://www.dfrobot.com/product-3005.html) |
| Generic 2204 260KV | 28 × 28 × 13 (S) | 26 (S) | 260 (S) | not found | 600 mA max operating current (S) | not found | [Zbotic](https://zbotic.in/?p=463615), [Robu](https://robu.in/?p=57801) |

From those figures, the motor study worked out what each motor gives through a gearbox of about 85 % efficiency, under its 1.5 A per-motor current cap. Every number in this table is an estimate (E):

| Motor | Gear ratio for 0.35 Nm | Joint torque left at 10 rad/s | Loss holding 0.13 Nm | Copper heat at peak |
|---|---|---|---|---|
| **GL30** | 7.2–8.5:1 | **0.35 Nm** (full 1.5 A still available) | **~0.35 W** | ~2.6 W |
| DFRobot 2804 | 7.3:1 | ~0.31 Nm | ~1.2 W | ~8.6 W |
| GM3506 | 4.7:1 | ~0.28 Nm | ~1.3 W | ~9.5 W |
| GM2804 | 7.3:1 | ~0.19 Nm | ~1.2 W | ~9.0 W |
| **GBM2804H-100T** | 7.4:1 | **~0.17 Nm** | **~1.1 W** | ~8.1 W |
| GB2208 | 8.8:1 | ~0.09 Nm | ~0.8 W | ~5.6 W |

The GL30 stands apart because its 0.765 Ω per phase would let it draw about **6.8 A at standstill from 9 V**. The 1.5 A cap binds before the voltage does. At a 10 rad/s joint speed the motor turns at about 85 rad/s, a third of its roughly 240 rad/s no-load speed at 9 V, and it still has current to spare (E). The high-turn 2804s reach 0.35 Nm only near standstill. The energy picture is starker. Six GBM2804H lift motors at peak would turn about **49 W into heat**, the whole 40–60 W supercapacitor burst. Six GL30s use about 37 W in all, 21 W of it as useful work (E). While walking, six lift joints holding 0.13 Nm cost about **2.1 W with GL30s against 6.7–7.4 W with 2804-100T motors**, out of a 22.5 W bank (E). The driver study adds a warning: twelve motors holding 0.5 A in 5 Ω-per-phase windings would use about 22 W, the whole bank (E). These are the same failures small SimpleFOC quadruped builders report, motors that "get too hot way too fast" and high-resistance windings that need high voltage ([SimpleFOC forum](https://community.simplefoc.com/t/selecting-gimbal-motors-to-build-an-actuator-for-a-small-quadruped/5061)).

The swing joints are a different problem, and that is where the cheap motor belongs. They need only 0.10–0.15 Nm, roughly 30–45 % of the peak current. Their axes are vertical, so the robot's weight does not hang on them while it stands (E). The GBM2804H's 0.17 Nm at 10 rad/s covers that, at **$18.99 against $50.99**, through the same 8:1 gear (E). Using it also halves the number of GL30s to find, which matters because the official store is sold out. Other numbers about the GL30 also disagree: KV 255 against the "290" in its name, 41 g against 83 g for one encoder version, and a 2.13 or 2.3 A rated current. Its **4 × M3 front and 3 × M2.5 rear holes come from one reseller only** ([FlyVisionPro](https://www.flyvisionpro.com/product/cubemars-gl30-kv290-brushless-gimbal-motor-6mm-hollow-shaft-41g-low-cogging-ip45/)). Another reseller lists official STEP and PDF drawings, which should be downloaded before the hip is drawn ([Pendulum Robotics](https://pendulumrobotics.com/products/gl30)). The 26 g generic 2204 could save about 13 g per swing joint, but its resistance is unknown and its 600 mA rating points against it. The DFRobot 2804 (220 KV) looks good on paper at about 0.31 Nm at speed, but its mass and price were not found.

No ready-made "joint in a can" fits. Nothing integrated is both **40 mm across or less and 60 g or less**. The Steadywin GIM3505-8 is the closest geared unit: Ø43 × 23.6 mm, 84 g bare or 97 g with its driver, 8:1, 0.65 Nm rated and 1.27 Nm at stall, CAN or RS-485. It is rated 12–48 V, though, so 9 V is below its range, and twelve of them would weigh 1.0–1.2 kg ([OpenELAB](https://openelab.com/products/steadywin-gim3505-8-robot-gear)). The MyActuator RMD-L-4005 fits the width (39.6 × 23 mm, 65 g), but it is direct drive with only 0.25 Nm peak, and it is rated 12–24 V ([Amazon](https://us.amazon.com/Myactuator-RMD-L-4005-25T-12V-24V-Brushless-Gimbal/dp/B0D4CXY3K6); [rcdrone](https://rcdrone.top/products/myactuator-rmd-l-4005-25t-12v-24v-high-speed-100w-brushless-dc-servo-motor)). These units are still useful as reference designs: they show that encoders on both the motor and the output, and planetary gears of 7–10:1, are normal at this scale. The weight sum is simple. The motor is 39–41 g, the printed gear 6–12 g, the output bearing 3–6 g, the magnet and encoder 1–2 g and the screws about 2 g, so a joint is **about 51–63 g before its driver board** (E). The cheaper motor saves almost none of that.

## One 8:1 printed gear stage and a 14-bit encoder finish each joint

A **single-stage printed planetary gear** is the proven reduction at this size. The CM6 compliant arm uses 5:1 to 9:1 printed stages on gimbal motors so the arm stays soft to push back ([Hackaday.io CM6](https://hackaday.io/project/180588-cm6-compliant-3d-printed-robotic-arm)). **TipTapMotor (MIT licence)** puts an 8:1 three-planet printed planetary on a GBM3506 in a 47 mm cube for about $74 an actuator ([TipTapMotor](https://github.com/DarrenLevine/TipTapMotor)). A printed drive measured about **84 % efficient** ([How To Mechatronics](https://howtomechatronics.com/how-it-works/what-is-the-best-3d-printed-drive-for-your-next-robotic-project/)). A stage sized to a 35 mm motor has a ring gear about 35–38 mm across and is under 15 mm deep, with gear teeth of module 0.5–0.6 and a sun gear of 9–12 teeth. That reaches 5:1 to 8:1, so **8:1 is the top of what one stage fits** (E), and 9:1 or more means two stages or a cycloidal drive. One 8:1 design can serve all twelve joints, since the swing motor's torque comes out the same at 7.4:1 and 8:1 (E).

The risk is landing shock. Small printed teeth concentrate stress and "can fail suddenly under shock" ([JeongSeoJin QDD](https://github.com/JeongSeoJin/quasi-direct-drive-actuator)). The evidence on material disagrees. In one 80:1 test, PLA showed very little wear while resin failed early ([Hackaday](https://hackaday.com/2022/02/10/resin-printed-gears-versus-pla-which-is-tougher/)), but a robotics team found PLA gears worn after one match while nylon held up ([Chief Delphi](https://www.chiefdelphi.com/t/printing-a-404-1-planetary/358482)). About 0.1 mm of added tooth clearance worked for one builder. That gearbox showed under 0.01 mm of play at 10 cm under light load, but visible movement under force ([How To Mechatronics](https://howtomechatronics.com/how-it-works/how-planetary-gears-work-3d-printed-planetary-gearbox-design-and-test/)). No one has published measured play or efficiency for a 5–8:1 printed stage this small, so that is the first print to test. The other reductions all lose at the hip:
- **Printed cycloidal drives** show about 1–2° of play ([Hackaday.io](https://hackaday.io/project/165592)), which is large next to a ±25° swing. Twente's preloaded designs cut that 2–3 times ([University of Twente](https://research.utwente.nl/en/publications/anti-backlash-mechanisms-for-cycloidal-drive-robotic-actuators-de/)).
- **Capstan (rope) drives** at 6:1 needed an 18 mm drum on the motor and a 108 mm drum on the joint ([PWr report](https://kcir.pwr.edu.pl/~witold/ip/2022_reports/Jakub_Tomaszewski.pdf)), far too big for a 35–40 mm hip. The CARA robot dog's steel cable also snapped after a few hours and had to be replaced with Dyneema rope ([Hackster](https://www.hackster.io/news/aaed-musa-s-capstan-drive-equipped-robot-dog-amazes-us-9ae9cea22714)).
- **Belts**, as in the ODRI Solo module (BSD-3, 9:1 in two belt stages, 150 g) ([ODRI](https://github.com/open-dynamic-robot-initiative/open_robot_actuator_hardware/blob/master/mechanics/actuator_module_v1/README.md)), slip under high load ([arXiv 2503.14255](https://arxiv.org/pdf/2503.14255)).
- **Metal planetary gearheads** made for gimbal outrunners were not found at all.

The encoder choice is easier:

| Encoder chip | Resolution | Interface | Notes | Price | Sources |
|---|---|---|---|---|---|
| **MagnTek MT6701** | 14-bit | SSI, I²C, ABZ (1–1,024 pulses per turn), UVW, PWM, analog; 3.3–5 V (O) | 30,000 rpm in Rev 0.1, 55,000 rpm in a later revision; SOP-8 about 5 × 3.9 × 1.75 mm, or QFN 3 × 3 (O/S) | module with magnet about $7.10 (S) | [datasheet](https://voltiq.ru/datasheets/MT6701.pdf), [Compel](https://www.compel.ru/infosheet/MAGNTEK/MT6701QT-ACD), [JLCPCB](https://jlcpcb.com/partdetail/MT6701CT-STD-R/C3003196), [Walmart](https://www.walmart.com/c/kp/angle-encoder) |
| MagnTek MT6835 | 21-bit | SPI to 16 MHz (S) | built-in calibration to ±0.07° (S) | not found | [Compel](https://www.compel.ru/infosheet/MAGNTEK/MT6835GT-STD), [Ineltek](https://www.ineltek.com/en/magntek-novosense-mt6835-encoder/) |
| ams AS5047P | 14-bit | SPI, plus ABI to 1,024 pulses per turn (O) | 28,000 rpm; adapter ships with a Ø6 × 2.5 mm magnet (O/S) | not found | [datasheet](https://www.infineon.com/row/public/documents/24/49/infineon-as5047p-datasheet-en.pdf), [Farnell](https://jp.farnell.com/en-JP/ams-osram-group/as5047p-ts-ek-ab/adapter-board-kit-position-sensor/dp/3976974) |
| ams AS5600 | 12-bit | I²C, analog or PWM (O) | **avoid for FOC:** slow I²C reads cause noise, limit the loop to about 1–2 kHz, and cause trouble above about 100 rad/s (F) | ~$6.68 module (S) | [SimpleFOC forum](https://community.simplefoc.com/t/sensor-update-taking-too-long-with-as5600-causing-vibration/3116) |

A SimpleFOC maintainer recommends reading the MT6701 over SSI or ABZ rather than I²C ([SimpleFOC forum](https://community.simplefoc.com/t/mt6701-magnetic-position-encoder-support/2618)). Each chip reads a **Ø6 × 2.5 mm NdFeB disc magnet, magnetised across its face**. A third-party AS5600 guide gives an air gap of 0.5–3 mm ([tinkered.ai](https://tinkered.ai/components/as5600)). The official field ranges were not found. On a hollow-shaft gimbal motor the magnet sits in a cap at the end of the shaft, as the 2804 + AS5600 kits do with a 5.5 mm-bore magnet ring ([Amazon](https://www.amazon.com/Hollow-Outrunner-Brushless-Encoder-Support/dp/B0FSZ7XWG2)) and iFlight does inside its AS5048A housing. The microspora board carries its own MT6701, so bolting the board behind the motor reads the magnet with no extra wiring. Because the encoder sits before an 8:1 gear, the ±25° swing is ±200° of motor turn, more than one revolution. The motor encoder alone therefore cannot know the joint angle at power-up (E). The plan already covers this: on waking, each motor pushes gently into its rubber stop to find its true angle (`plans/new-bodies.md`, section 7). A second encoder on the output is optional.

## Smart servos fit 25 g but peak at 2.7 W of the 3.5 W hop

The only ready-made joints inside the 25–30 g budget are small smart servos: a motor, gearbox, encoder and controller in one case on a shared serial bus. The hop point is 0.35 Nm at 10 rad/s, which is **3.5 W of mechanical power per lift joint** (E). The "at 0.35 Nm" and "at 10 rad/s" columns below come from a straight-line speed–torque model between each servo's official stall and no-load points (E).

| Servo | Size (mm) | Mass | Supply | Stall torque (current) | No-load speed | Speed at 0.35 Nm (E) | Torque at 10 rad/s (E) | Price | Sources |
|---|---|---|---|---|---|---|---|---|---|
| Dynamixel XL330-M288-T | 20 × 34 × 26 | 18 g | 3.7–6 V | 0.52 Nm at 5 V (1.47 A) (O) | 10.8 rad/s at 5 V (O) | 3.5 at 5 V; 5.4 at 6 V | 0.04 at 5 V; 0.13 at 6 V | €39.78–40.20 (S); $19.90 list price in 2021 (O) | [ROBOTIS data](https://raw.githubusercontent.com/ROBOTIS-GIT/emanual/master/_data/dxl_x_info.yml), [Generation Robots](https://www.generationrobots.com/en/403817-dynamixel-xl330-m288-t-servo-motor.html) |
| **Dynamixel XC330-M181-T** | 20 × 34 × 26 | 23 g | 3.7–6 V | 0.60 Nm at 5 V (1.80 A); 0.66 at 6 V (2.15 A) (O) | 13.5 at 5 V; 16.2 at 6 V (O) | **5.6 at 5 V; 7.6 at 6 V** | **0.16 at 5 V; 0.25 at 6 V** | not captured | [ROBOTIS data](https://raw.githubusercontent.com/ROBOTIS-GIT/emanual/master/_data/dxl_x_info.yml) |
| Dynamixel XC330-M288-T | 20 × 34 × 26 | 23 g | 3.7–6 V | 0.93 at 5 V; 1.10 at 6 V (O) | 8.5; 10.2 (O) | 5.3; 6.9 | 0.02 at 6 V | $103.39 including US tariffs (S) | [RobotShop](https://www.robotshop.com/es/products/robotis-dynamixel-xc330-m288-t-smart-servo-actuator) |
| Dynamixel XC330-T181-T | 20 × 34 × 26 | 23 g | 6.5–12 V | 0.65 at 9 V (0.61 A) (O) | 8.7 at 9 V (O) | 4.0 at 9 V | cannot reach 10 at 9 V | not found | [ROBOTIS data](https://raw.githubusercontent.com/ROBOTIS-GIT/emanual/master/_data/dxl_x_info.yml) |
| Dynamixel XM335-T323-T | 19 × 35 × 22 | 27 g | 6.5–12 V | 0.85 at 9 V (O) | 4.5 at 9 V (O) | 2.7 at 9 V | cannot reach 10 | €168 (S) | [Generation Robots](https://www.generationrobots.com/en/404426-dynamixel-xm335-t323-t-servo-motor.html) |
| Feetech STS3032 | 23.2 × 12.1 × 28.5 | 20 g | 4.8–6 V | 0.44 Nm at 6 V (1.2 A) (S) | ~11.6 at 6 V (S) | 2.4 | 0.06 | not found | [aifitlab](https://aifitlab.com/products/feetech-sts3032-servo-motor), [Eckstein](https://eckstein-shop.de/Motors?mf=1580) |

Every servo in the weight class meets the running load (0.13 Nm at 6 rad/s), and none meets the hop. The closest is the **XC330-M181 at 6 V**, which peaks at about 2.7 W: 0.35 Nm at about 7.6 rad/s, or 0.25 Nm at 10 rad/s (E). Six XL330-M288s on the swing joints and six XC330-M181s on the lift joints weigh **246 g of servos**. That leaves 54–114 g of the 300–360 g budget for horns and brackets, so the planned 850–920 g robot survives, at about **$1,030 for 14 servos** (E, at an unverified 1.08 USD per euro). These servos need a 9 V to 6 V converter rated about 5 A continuous and 10 A peak. Each servo's current limit must also be set to about 0.8 A, so that twelve stalled servos cannot ask for 25.8 A (E). The XC330-T181 runs straight from 9 V but is slower (4 rad/s at 0.35 Nm), and it needs 5 V logic.

The control quality is weaker than it looks. ROBOTIS says the X330 "measures current at its input power source", not in the motor windings ([ROBOTIS e-manual source](https://raw.githubusercontent.com/ROBOTIS-GIT/emanual/master/docs/en/dxl/x/xl330-m288.md)). A springy joint built on its current-based position mode would therefore feel stiffer when moving fast and softer when nearly still, and it would need calibrating against a known weight (E). On the useful side, it has a current-based position mode, a **bus watchdog** that stops the servo after 1–127 × 20 ms without commands ([ROBOTIS](https://raw.githubusercontent.com/ROBOTIS-GIT/emanual/master/_includes/en/dxl/control_table_buswatchdog.md)), a broadcast ID that reaches every servo at once, and a Fast Sync Read that collects all replies in one packet ([Protocol 2.0](https://raw.githubusercontent.com/ROBOTIS-GIT/emanual/master/docs/en/dxl/protocol2.md)). In practice the bus tops out at 4 Mbaud ([Bit-Bots](https://docs.bit-bots.de/meta/manual/tutorials/lowlevel.html)). That makes 500 Hz–1 kHz plausible on one ESP32-S3 serial port (E, not measured).

Builders' experience is mixed. The Open Duck Mini biped moved its legs from XL330 to XC330 servos because they were "way more powerful", reported "too much play at some joints", then moved again to the larger STS3215 ([Open Duck Mini](https://raw.githubusercontent.com/apirrone/Open_Duck_Mini/main/README.md)). Gears of 181–288:1 are hard to turn from the output side, so landing shocks go into the teeth (E). STS3215 owners report stripped gears and burned-out servos after stalls ([HBRobotics](https://groups.google.com/g/hbrobotics/c/wMPp7it97i4)). Feetech's "load" register reports motor drive (PWM duty), not torque, and its torque limit caps that drive rather than regulating current ([FTServo](https://raw.githubusercontent.com/ftservo/FTServo_Arduino/main/src/SMS_STS.h)). Heavier servos are out on mass: STS3215 about 55 g, Hiwonder LX-224 57–63 g, Lynxmotion LSS-HT1 80 g, Kondo KRS-2572HV 47.7 g.

Choosing servos would **reverse a decided point in `plans/new-bodies.md`**: "Brushless motors, each with a magnetic encoder and FOC control." The licences are mostly fine. DynamixelSDK is Apache-2.0 ([LICENSE](https://raw.githubusercontent.com/ROBOTIS-GIT/DynamixelSDK/main/LICENSE)) and Feetech's own FTServo libraries are MIT ([LICENSE](https://raw.githubusercontent.com/ftservo/FTServo_Arduino/main/LICENSE)). **The Waveshare-derived "SCServo" code and Waveshare's ugv_base_general are GPL-3.0, which is copyleft, so keep them out of Pebble** ([scservo](https://raw.githubusercontent.com/workloads/scservo/main/LICENSE); [ugv_base_general](https://raw.githubusercontent.com/waveshareteam/ugv_base_general/main/LICENSE)). At a 52 mm hip spacing, an X330 lift servo must sit almost directly over the swing axis. Stacked there, it leaves about 13 mm between neighbours at full swing. Moved 15 mm off the axis, neighbours touch, and the stacked joint is about 50 mm tall (E).

## Twelve 33 mm open driver boards ride on the motors

The 9 V bus rules out the polished commercial driver boards, which all need 10–12 V or more:

| Board | Size (mm) | Holes | Mass (g) | Input | Current | Current sensing | Chips, encoder, link | Licence | Price | Works at 9 V? |
|---|---|---|---|---|---|---|---|---|---|---|
| **SimpleFOC-microspora v1.7** (2026-06) | **33 × 34** (O) | **3 slots 3.2 × 5 mm for M2 or M3, 22–28 mm apart** (O) | not published (~5, E) | 5–35 V (README) or 8–35 V (docs) (O, conflict) | about 8 A max (O) | all three phases plus bus voltage (O) | STM32G431 + DRV8316; MT6701 on board; CAN on two 3-pin JST plugs, 1 Mbps in the example (O) | **MIT** (O) | about $20 to make at JLCPCB (O); shop price not found | yes, if the 8 V figure holds |
| SimpleFOC Mini v2.3 | 24 × 25 (O) | not stated | not found | 5–35 V (O) | 8 A (O) | three low-side, 150 mV/A (O) | driver only: 3 PWM inputs + enable | MIT (O) | about €5 to make (O) | yes |
| ODRI Micro Driver (two motors) | 51 × 50 (O) | not stated | 13 (O) | 5–32 V (README) or 5–45 V (mirror) (O/S, conflict) | 15 A per channel (S) | six 7 mΩ shunts (O) | TI C2000; SPI to an ESP32 master board (O) | BSD-3 (O) | not sold | yes |
| mjbots moteus-c1 | 38 × 38 × 9 (O) | not found | 8.9 (O) | 10–51 V (O) | 5 A without cooling, 20 A peak (O) | yes | STM32G4; CAN-FD at 5 Mbps (O) | Apache-2.0, hardware too (O) | $69 for one, $61 at 100+ (O) | no |
| ODrive Micro | 32 × 32 × 7.5 (O) | 4 × M3 on a 26 × 26 square (O) | 6.8 (O) | 10–30 V (O) | 3.5 A continuous, 7 A peak (O) | yes | CAN 2.0B at 1 Mbps (O) | **firmware closed** (O) | $89 for one (O) | no |
| Tinymovr M5.1 | 29.5 × 29.5 (S) | not found | 8 (S) | 12–38 V (S) | 5 A (S) | yes | MA702 encoder, CAN (S) | not checked | not found | no |
| ST B-G431B-ESC1 | 30 × 41 (S) | not found | not found | 3S–6S (11.1–22.2 V) (S) | 40 A peak (S) | 3 mΩ shunts (S) | STM32G431, CAN (S) | ST | $18.59 (S) | no |

Sources: [microspora repo](https://github.com/simplefoc/SimpleFOC-microspora), [microspora docs](https://raw.githubusercontent.com/simplefoc/simplefoc.github.io/master/docs/boards/microspora/connecting.md), [SimpleFOC Mini docs](https://raw.githubusercontent.com/simplefoc/simplefoc.github.io/master/docs/boards/simplefoc_mini/index.md), [ODRI micro driver](https://github.com/open-dynamic-robot-initiative/open_robot_actuator_hardware/blob/master/electronics/micro_driver_electronics/README.md), [moteus](https://github.com/mjbots/moteus), [moteus-c1 store](https://mjbots.com/products/moteus-c1), [ODrive Micro](https://shop.odriverobotics.com/products/odrive-micro), [ODrive firmware](https://github.com/odriverobotics/odrive), [Tinymovr](https://robots.ros.org/tinymovr/), [Digi-Key reference design](https://www.digikey.it/reference-designs/en/motor-control/2840), [ST eStore](https://estore.st.com/en/products/evaluation-tools/product-evaluation-tools/mcu-mpu-eval-tools/stm32-mcu-mpu-eval-tools/stm32-discovery-kits/b-g431b-esc1.html).

The chip that makes 9 V work is TI's **DRV8316**: 4.5–35 V (40 V absolute maximum), 8 A peak, 95 mΩ, current sensing built in with no separate resistors, a VQFN-40 package of 7 × 5 mm, and **$4.60 for one or $2.61 at 1,000** ([TI](https://www.ti.com/product/DRV8316); [Digi-Key](https://digikey.cn/en/products/detail/texas-instruments/DRV8316RRGFR/16592525)). The low-voltage gimbal chips TMC6300 (2–11 V) and STSPIN233 (1.8–10 V) sit too close to a 9 V bus that rises when an unpowered leg is pushed and its motor generates (E) ([ADI TMC6300](https://www.analog.com/en/products/tmc6300.html); [ST STSPIN233](https://st.com/en/motor-drivers/stspin233.html)). On the processor side, SimpleFOC documents low-side current sensing for **one motor per STM32** ([SimpleFOC](https://raw.githubusercontent.com/simplefoc/simplefoc.github.io/master/docs/simplefoc_library/hardware/mcus/index.md)), although the library README says "one per ADC", so the two disagree ([Arduino-FOC](https://github.com/simplefoc/Arduino-FOC)). One forum user reports a G431 running its current loop at 15–16 kHz ([SimpleFOC forum](https://community.simplefoc.com/t/is-it-possible-to-control-3-bldc-closed-loop-motor-in-foc-with-a-stm32g474-ic/7116)). The ESP32's motor timers drive four three-phase motors at most ([SimpleFOC](https://docs.simplefoc.com/microcontrollers)), so the ESP32-S3 should not drive the motors itself.

The boards have to live on the motors. Twelve microspora boards cover about 13,500 mm², more than the deck's 11,200 mm² (E). Mounted on the back of each motor, each hip then needs only power and the CAN pair, instead of three motor wires plus four to six encoder wires. A dead board is a $20 swap. The boards barely warm: the DRV8316 loses about 20 mW per motor at 0.5 A (E). The heat in this body comes from the motors' windings and from twelve idle processors, about 1–2 W in all (E).

A Pebble version of the board needs five changes:
- **Fit a CAN-FD transceiver.** The microspora repo does not name its transceiver. The STM32G431 itself supports CAN-FD.
- **Bring out the DRV8316's enable and fault pins** (EN and nFAULT) to shared lines. The board lists only a CAN enable today ([microspora docs](https://raw.githubusercontent.com/simplefoc/simplefoc.github.io/master/docs/boards/microspora/connecting.md)).
- **Raise the current-sense gain to 0.375 V/A.** At that gain, one step of the processor's analog reading is about 2.1 mA (E) ([SimpleFOC DRV8316 driver](https://raw.githubusercontent.com/simplefoc/Arduino-FOC-drivers/master/src/drivers/drv8316/drv8316.h)).
- **Confirm the true minimum input voltage.** The docs' 8 V figure would sit right at the 8.2–8.4 V a hop leaves on the bus.
- **Use JST-GH plugs** to match the body.

For the firmware, copy the ODRI command frame. It is 34 bytes per two-motor board and carries the mode, two positions, two speeds, two extra-push currents, two stiffnesses and two dampings, current limits, an index and a checksum. It takes under 35 µs at 8 MHz, and the motors are switched off if no valid command arrives within 0–255 ms ([ODRI SPI interface](https://raw.githubusercontent.com/open-dynamic-robot-initiative/master-board/master/documentation/BLMC_%C2%B5Driver_SPI_interface.md)). moteus offers timeout modes from "stopped" through "hold position" to "brake" ([moteus configuration](https://raw.githubusercontent.com/mjbots/moteus/main/docs/reference/configuration.md)). No built-in command timeout was found for SimpleFOC, so it has to be written. A sensible split is that a lost link brakes and holds in firmware, while a safety trip cuts power and lets the body sink onto its belly (E).

The link to the main board decides the bus. The ESP32-S3's built-in CAN is the older classic kind, and Espressif says it "will interpret [FD] frames as errors" ([ESP-IDF TWAI](https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32s3/api-reference/peripherals/twai.html)). A command and a reply for 12 joints on classic CAN at 1 Mbps takes 2.7–3.2 ms, which caps the rate at **310–370 Hz at full bus load** and about 250 Hz at a sane load. That fails the plan's 500–1,000 Hz (E). Two **MCP2518FD** CAN-FD controllers fix it: 1 Mbps arbitration, up to 8 Mbps data, SPI up to 20 MHz, or 17 MHz on one variant ([Mouser](https://www.mouser.com/new/microchip/microchip-mcp2518fd-controllers); [Microchip](https://microchip.com/en-us/product-comparison.mcp2517fd.mcp2518fd)). Put one bus on each side, six joints each, with one broadcast command per cycle. That runs about 1 kHz at roughly 60 % bus load (E). It matches the mjbots quadruped, which commanded and read 12 servos plus an IMU in 740 µs over four 5 Mbps CAN-FD buses ([Hackaday.io](https://hackaday.io/project/167845/log/179913)). The transceivers can be **TJA1051T/3** chips (CAN-FD to 5 Mbps, 5 V supply with a 3.3 V logic pin) ([robu.in](https://st.robu.in/?p=1880540)), or the Adafruit CAN Pal, which makes its own 5 V (£3.80) ([Adafruit](https://learn.adafruit.com/adafruit-can-pal)). The ESP-IDF MCP2518FD driver needs retries at power-up and must be switched into FD mode ([Espressif registry](https://components.espressif.com/components/solderedelectronics/soldered-mcp2518fd-esp-idf-component/versions/1.0.0/readme)). A strong later option is six two-motor leg boards (STM32G474 plus two DRV8316s). That halves the boards and their idle power, but no open firmware yet runs two current loops on one processor. The ODRI two-motor boards on an ESP32 master board at 1 kHz over SPI (BSD-3 and BSD-2) are the proven open pattern, but they use a TI C2000 processor and a 51 × 50 mm board ([ODRI master board](https://github.com/open-dynamic-robot-initiative/master-board)).

## A 60 × 40 mm carrier holds the ESP32-S3, IMU, edge sensors and safety cut

None of the tiny ESP32-S3 boards has mounting holes. They are made to be soldered flat onto another board by their edge pads, or held in a printed cradle, so the body needs a small carrier board, about **60 × 40 mm with four M2 holes** (E). The **Waveshare ESP32-S3-Zero** is the best module for it:
- **Size:** 23.5 × 18 mm, with edge pads (O).
- **Pins:** about 24 programmable pins (O/S).
- **Power:** an 800 mA, 3.3 V regulator (ME6217C33M5G), fed with 3.7–6 V on its "5V" pad (O).
- **Memory:** 4 MB flash and 2 MB PSRAM (S).
- **USB:** a USB-C port wired straight to the chip's own USB, so it plugs into the phone with no bridge chip (E).
- **Antenna:** Waveshare says to keep the board, metal and plastic clear of it.

Source: [Waveshare docs](https://docs.waveshare.com/ESP32-S3-Zero). The body needs about 20 signals in all (E), which rules out boards with fewer pins. The **Seeed XIAO ESP32S3 Plus** (21 × 17.8 mm, 16 MB flash, 8 MB PSRAM, about 20 pins) is the alternative ([CNX Software](https://www.cnx-software.com/2025/01/13/seeed-studio-xiao-plus-series-adds-more-gpio-castellated-holes/)). For a later all-in-one board, the bare **ESP32-S3-MINI-1** module (15.4 × 20.5 × 2.4 mm) can be soldered on directly, but it needs oven soldering ([Espressif](https://www.espressif.com/sites/default/files/documentation/esp32-s3-mini-1_mini-1u_datasheet_en.pdf)). Rule out the ESP32-S3-Tiny (it has no USB port), the DevKitC-1 (too big), and the QT Py and base XIAO (too few pins). USB to the phone runs at full speed (12 Mbit/s) in 1 ms frames ([Espressif](https://docs.espressif.com/projects/esp-iot-solution/en/latest/usb/usb_overview/usb_otg.html)), so the fast balance loop must close on the ESP32, not the phone. **Licence flag:** Pebble's firmware uses the Arduino framework, and the **arduino-esp32 core is LGPL-2.1**, a weak copyleft licence ([arduino-esp32 LICENSE](https://github.com/espressif/arduino-esp32/blob/master/LICENSE.md)). Pebble can build on it, because it publishes its own source and anyone can rebuild against a changed core. Any changes to the core itself must stay LGPL.

The IMU must survive landings. A small hexapod landing on stiff printed feet can see brief spikes above 16 g at the body, and a clipped reading corrupts both impact detection and the tilt estimate at exactly the wrong moment (E).

| IMU | Acceleration range | Turn-rate range | Gyro noise | Interface | Breakout and price | Sources |
|---|---|---|---|---|---|---|
| **TDK ICM-45686** | **±32 g** (O) | ±4,000 °/s (O) | 3.8 mdps/√Hz (O) | not confirmed | no major-vendor breakout found | [TDK](https://adm.invensense.tdk.com/icm-45686) |
| TDK ICM-42688-P | ±16 g (O) | up to ±2,000 °/s | 2.8 mdps/√Hz (O) | SPI 24 MHz (O) | open DIY boards only | [TDK](https://invensense.tdk.com/products/icm-42688-p/) |
| **ST LSM6DSO32** | **±32 g** (S) | ±2,000 °/s (S) | not found | SPI or I²C (S) | **Adafruit #4692, $12.50** (O) | [Adafruit](https://www.adafruit.com/product/4692) |
| ST LSM6DSV16X | ±16 g (O) | ±4,000 °/s (O) | not found | SPI/I²C, built-in orientation output (O) | SparkFun Micro 19.05 × 7.62 mm, $25.50 (O/S) | [SparkFun](https://www.sparkfun.com/sparkfun-micro-6dof-imu-breakout-lsm6dsv16x-qwiic.html) |
| Bosch BMI088 | ±24 g (O) | ±2,000 °/s (S) | 0.014 °/s/√Hz (O/S) | SPI or I²C (S) | BobbieBots 10 × 17 mm, I²C (S) | [datasheet](https://cdn.sparkfun.com/assets/c/c/e/4/7/BMI088_Datasheet.pdf), [Tindie](https://www.tindie.com/products/bobbiebots/bmi088-i2c-breakout/) |
| CEVA BNO085 | ±8 g per one third-party driver (S) | — | — | I²C/SPI | fused output tops out at 400 Hz, so not for the balance loop (S) | [Luxonis](https://docs.luxonis.com/hardware/platform/sensors/imu/bno08x.md) |

Prototype with the Adafruit LSM6DSO32 over SPI and drop-test it. If landing peaks stay under about 12 g, the ICM-42688-P is enough. Otherwise put the ICM-45686 (or the vibration-hardy BMI088, which Bosch "designed for drone and robotics applications" ([Bosch flyer](https://www.mouser.lt/pdfdocs/BoschSensortec_Productflyer_BMI088.pdf))) on the carrier, rigidly mounted near the body's centre (E).

For drop edges, the **ST VL53L4CD** replaces today's VL53L0X. It ranges from **1 mm** to 1.2 m, has a narrow **18° cone**, and reads at **up to 100 Hz** ([ST](https://www.st.com/en/imaging-and-photonics-solutions/vl53l4cd.html)), against the VL53L0X's 25° and about 50 Hz ([Pololu #2490](https://www.pololu.com/product/2490)). The Pololu #3692 carrier is 13 × 18 × 2 mm and costs $16.95 ([Pololu](https://www.pololu.com/product/3692)). Pololu's laser-sensor carriers share one board design, so the parts swap without changing the mount ([Pololu](https://www.pololu.com/category/306/carriers-for-st-time-of-flight-tof-distance-sensors)). Today's sensor looks 32° forward and reads about 32 mm on a flat floor (`interfaces.md`), and the same trick carries over. The hexapod's nose height changes with stance, though. The cameras sit about 7.5 cm up at rest and 11 cm standing (`plans/new-bodies.md`, section 7a), so the expected floor distance must follow the leg angles (E).

For the independent hardware cut, add a **Pololu digital distance sensor** wired only to the safety chip. Its output is a plain high or low signal. The Sharp GP2Y0D805Z0F it replaces is discontinued and switches at 0.5–5 cm, updating every 2.56 ms ([Pololu #1131](https://www.pololu.com/product/1131)). The Pololu replacements come in 5, 10 and 15 cm versions with the same pinout ([Pololu #5550](https://www.pololu.com/product/5550/pictures); [Core Electronics 10 cm](https://core-electronics.com.au/catalog/product/view/sku/POLOLU-4052)). Choose the range so the floor sits mid-range while standing. The output goes "no object" when the floor drops away or the sensor dies, so a fault fails safe (E). The two edge sensors use different physics and different processors, so no single failure blinds both.

The power monitor is a **TI INA228**: 85 V, 20-bit, readings as fast as 50 µs, a 75 µs alert, and built-in energy and charge counters ([TI](https://ti.com/product/INA228)). Use the Adafruit #5832 board (25.8 × 20.2 × 10.1 mm, 3.3 g, 15 mΩ, up to 10 A) on the bench ([Adafruit](https://adafruit.com/product/5832); [The Pi Hut](https://thepihut.com/products/adafruit-ina228-i2c-85v-20-bit-high-or-low-side-power-monitor-stemma-qt-qwiic)). On the carrier, use the chip with a 2 mΩ shunt. Place it on the bank's input, where its charge counter becomes the battery gauge, since the bank's cell is sealed away (E).

The safety cut uses a **WCH CH32V003** (48 MHz RISC-V, two watchdogs, TSSOP-20 with 18 pins) ([CNX Software](https://www.cnx-software.com/2022/10/22/10-cents-ch32v003-risc-v-mcu-offers-2kb-sram-16kb-flash-in-sop8-to-qfn20-packages/)). It watches four inputs:
- a heartbeat from the ESP32 that must keep toggling inside a time window;
- the IR edge sensor;
- its own tilt sensing;
- the INA228's alert line.

It drives the enable pin of the motor-power switch. A resistor holds that pin off, so a dead or unflashed safety chip means no motor power. After a cut it stays off until the ESP32 sends a deliberate re-arm and every input is good (E). A **TI TPS3430** window watchdog (1.6–6.5 V, 3 × 3 mm) can guard the same line with no firmware at all ([TI](https://www.ti.com/lit/gpn/tps3430)). The motor-power switch must carry the whole hop burst, about 6–7 A (E). Three parts fit, from simplest to most robust:
- a **TPS25982** electronic fuse: 2.7–24 V, adjustable 2–15 A limit, trips in under 400 ns on a short ([Mouser](https://www.mouser.fr/new/texas-instruments/ti-tps25982-smart-efuses));
- two **TPS25947** fuses, 5.5 A each, one per three legs ([TI](https://www.ti.com/product/TPS25947));
- an **LTC4365** or **LM74502** controller driving two MOSFETs back to back ([ADI](https://www.analog.com/jp/resources/technical-articles/no-blocking-diode-needed-to-protect-sensitive-circuits.html); [TI](https://www.ti.com/document-viewer/lit/html/SLVAFB3)).

Put a voltage clamp (a TVS diode) and bulk capacitors on the motor side, because legs still moving when power is cut push current back onto the bus (E). This is how the laws in `brain/pebble/laws.py` reach the hardware. Signal cables should use **JST-GH (1.25 mm, about 1 A per pin, 50 V)** with the Pixhawk CAN pinout of 5 V, CAN_H, CAN_L, GND ([JST](https://grobotronics.com/images/companies/1/datasheets/jst%20core%20selection.pdf); [ARK Electron](https://docs.arkelectron.com/knowledge-base/knowledge-base/connectors-and-wiring)). Never mix in Molex PicoBlade, which is not compatible ([PX4](https://docs.px4.io/v1.14/zh/flight_controller/pixhawk.html)). Motor power goes on a separate, heavier plug.

## One switch makes the Xiaomi bank both motor supply and dock load

The owner's bank is the **Xiaomi UltraThin Magnetic Power Bank 5000 15W, model MDY-20-EB**:
- **Size and capacity:** 98.5 × 71.5 × 6 mm, 98 g, 18.95 Wh in the cell, rated 3,000 mAh at 5 V ([Xiaomi](https://www.mi.com/global/product/xiaomi-ultrathin-magnetic-power-bank-5000-15w/specs/)). A teardown measured 5.87 mm thick.
- **Its one USB-C port works both ways** at fixed **5 V 3 A or 9 V 2.5 A**, with no variable-voltage (PPS) mode. It uses Nuvolta chips ([ChongDianTou teardown](https://www.chongdiantou.com/archives/1760059044364.html); [chip list](https://www.chongdiantou.com/archives/1760320760897.html)).
- **Recharging:** about **51 minutes to 80 % and 2 h 12 min to full** ([ChongDianTou review](https://www.chongdiantou.com/archives/1773106578355.html)).
- **No charging while powering the motors.** Its only charge-and-discharge-at-once mode is USB-C in with wireless out, and in that mode it charges itself at only about 5.15 W.
- **The wireless face is output only.** Using it at the same time cuts USB-C to 5 V 1.5 A.
- **Usable energy:** about 14–15 Wh at the port (E).
- **Price:** NZ$79.19–99 at PB Tech ([PB Tech](https://www.pbtech.co.nz/product/BAPMIX74833/Xiaomi-5000mAh-225W-1-Output-Ultra-Thin-Magnetic-W)).

A 27 W wired version went on sale in China on 16 October 2026 at ¥299. It might give more current at 9 V, but its exact voltage and current options are unconfirmed ([Sina Tech](https://finance.sina.com.cn/tech/discovery/2026-10-16/doc-inivmiif7672528.shtml)). Xiaomi does not document how little current makes the bank switch itself off. Its low-current mode needs a button press, and on other models it lasts 2 hours ([Xiaomi FAQ](https://www.mi.com/global/support/faq/details/KA-300034/)), so it cannot be relied on.

To get 9 V, use the **WCH CH224Q**, a chip that asks a USB-C power source for a set voltage. It accepts 4–30 V, is 2 × 2 mm, talks I²C at address 0x22 or 0x23, and in that mode reads the source's full list of offers, so the firmware can confirm it got 9 V 2.5 A ([WCH datasheet](https://done.land/assets/files/ch224aq_datasheet.pdf)). Keep it on 3.3 V logic, because one library warns that 5 V logic can damage the CH224A ([FGV_CH224X](https://github.com/felixardyansyah/FGV_CH224X)). The **Hynetek HUSB238** is the alternative ([Hynetek](https://www.hynetek.com/uploadfiles/site/219/news/aabbbbdb-48c9-4a44-a6dc-2c15f53282e6.pdf)). To wake a bank that has switched itself off, briefly break the CC line, the USB-C wire that tells the bank something is attached (E, to be tested).

The hop runs on supercapacitors held behind a current limit:

| Stack | Capacitance | Rated voltage | Resistance of the stack | Mass | Cell size | Energy from 9 to 7 V | Bus after a 6 J hop | Sources |
|---|---|---|---|---|---|---|---|---|
| **4 × Maxwell BCAP0010 P270 S01 (10 F)** | 2.5 F | 10.8 V | 80–120 mΩ (cells 20 typical, 30 max) (O) | **~12.6 g** (3.1 each) (O) | Ø10 × 30.5 mm (O) | 40 J (E) | **~8.2–8.4 V** (E) | [Maxwell](https://maxwell.com/wp-content/uploads/2021/08/2_7_10F_ds_3001976_datasheet.pdf), [JLCPCB X01](https://jlcpcb.com/partdetail/5121822-BCAP0010_P270X01/C4550729) |
| 4 × Eaton HV1020-2R7505-R (5 F) | 1.25 F | 10.8 V | ~160 mΩ (40 per cell) (O) | ~9.2 g (2.3 each) (O) | Ø10 × 22.3 mm in the datasheet, 10.5 × 21.2 on the product page (O, conflict) | 20 J (E) | ~7.7 V (E) | [Eaton](https://www.eaton.com/us/en-us/skuPage.HV1020-2R7505-R.html) |

A 60 W push lasting 0.1 s needs 6 J, so the Maxwell stack has a wide margin (E). Avoid Maxwell's T01 version, which has 75 mΩ per cell ([Mouser](https://www.mouser.com/ProductDetail/Maxwell-Technologies/BCAP0010-P270-T01?qs=GQp755mzIP2TfG2h%2ByGJoQ%3D%3D)). Prefer the 10 F Maxwells over the lighter Eatons, because the Eatons' deeper dip would fall below microspora's possible 8 V minimum (E). Lithium-ion capacitors have 0.15–0.5 Ω per cell and would sag 1–3 V at 5 A ([Taiyo Yuden](https://www.farnell.com/datasheets/1972296.pdf)). The LTC3350 controller only draws on its capacitors once the input fails, so a hop would still pull more than 2.5 A from the bank ([ADI](https://analog.com/en/products/ltc3350)).

The power path then runs:
1. **The bank's port goes to the CH224Q**, which asks for 9 V.
2. **A TPS25947 electronic fuse in current-limit mode, set to about 2.2 A,** comes next. Its ±10 % tolerance keeps the bank at or under 2.42 A ([TI](https://www.ti.com/product/TPS25947)), and during a hop it lets the bus sag instead of overloading the bank. It turns about 1.5 W into heat for 0.1–0.3 s, and whether that is within its safe limits is unconfirmed (E).
3. **The supercapacitor stack sits on the 9 V bus after that fuse**, with four 10 kΩ balancing resistors (E).
4. **The safety-switched motor fuse** feeds the joint boards.

Filling 2.5 F from empty through any simple linear path wastes about 101 J (E). Use a 10–15 Ω, 3 W resistor with a MOSFET that bypasses it once the stack is nearly full. That is a time constant of 25–40 s, or a minute or two from flat (E). Once charged, the stack loses only about 1 V in 3 hours through the balancing resistors, if the logic is not drawing on it (E). The fixed 9 V level can run a few percent high under USB rules; the notes assume up to about 9.45 V, which is 2.36 V per cell against a 2.7 V rating (E, unverified).

On the dock, the "turn the port round" problem in `plans/new-bodies.md` goes away. It needs no dual-role USB power chip in the body. The recommended dock is **plain USB-C on sprung pins**:
- **The dock** holds a multi-port USB-C charger of 45–65 W, each port able to give 9 V at 2.5 A or more (E). Its power and CC lines run to sprung pins pointing up out of a low pad.
- **The belly carries six pads:** bank power, bank CC, phone power, phone CC, and two grounds, plus an optional "docked" pad (E). The robot's own weight presses them down, about 8.8 N at 900 g and about 11–12 N at 1.2 kg.
- **Today's dock** shows the pattern: brass pads 30 × 4 mm on the robot, 3 A sprung pins, two pairs of 10 × 3 mm magnets, and an AprilTag for the last metre (`interfaces.md`; `reference/spec_snapshot_2026-10-15.txt`). Add a Hall sensor, which detects the dock magnet, as a second "seated" signal.
- **The switch:** while docked, a normally-open switch in the body hands the bank's port from the 9 V sink to the dock pads. Two MOSFETs back to back switch the power line and an analog switch handles CC (E). The bank and charger then negotiate between themselves and the bank charges at its full rate.
- **The pins stay dead until Pebble sits.** A USB-C charger keeps its power line off until it sees the 5.1 kΩ resistor a real device presents on CC, so a coin or a metal desk cannot turn it on (E, from the USB-C rules, not checked here).
- **The cost:** the motors are off while docked, which suits a robot that rests on its belly anyway.

A body-mounted 2S lithium pack with its own charger would be cleaner electrically: it could charge while running, never switch itself off, and drop the supercapacitors. But it means designing and documenting a custom lithium pack, where the bank is a finished, protected product. The bank cannot be charged wirelessly, because its wireless face only gives power.

The phone is the open question. The Flip 7 has a 4,300 mAh battery, 25 W wired charging and 15 W wireless ([Wikipedia](https://en.wikipedia.org/wiki/Samsung_Galaxy_Z_Flip_7)). The bank cannot usefully charge it, because the bank lies face down and gave a non-Xiaomi phone only 5 W wirelessly ([GSMArena](https://www.gsmarena.com/xiaomi_ultrathin_magnetic_power_bank_5000_15w_review-news-74788.php)). Samsung documents nothing about charging while the phone runs a USB device. Reports differ by model, and a Samsung moderator said Samsung has no tested USB-C hub for its phones ([octo4a](https://github.com/feelfreelinux/octo4a/discussions/121); [Samsung community](https://r1.community.samsung.com/t5/tablets/usb-c-hub/td-p/11546211)). Three paths remain, in order:
- **First, test** a cheap USB-C adapter that passes charger power through, placed between the phone and the ESP32 and fed from the dock's phone pins. If the phone charges and the ESP32 stays connected, build that in.
- **Fallback 1** is Android Open Accessory, where the body becomes the USB host and powers the phone by default ([Android](https://source.android.com/devices/accessories/protocol)). It reverses the plan's "phone is the USB host" decision, so it needs the owner's approval.
- **Fallback 2** is a wireless charging coil in the holder's backrest, but only if the Flip keeps charging wirelessly while it runs a USB device.

Without fast-charge support the phone probably charges near 15 W, as the Flip 4's rating suggests ([Wikipedia](https://en.wikipedia.org/wiki/Samsung_Galaxy_Z_Flip_4)), so a full charge takes about 1.3–1.6 h (E). At rest, the phone's own USB power can keep the ESP32 awake so the body can wake the bank (E).

## Conclusion: what to buy, draw, decide and test

The torque target is not what breaks here; the weight target is. At a fixed 9 V, only a low-resistance brushless joint delivers the 3.5 W a hop push needs, and that joint weighs about twice the budget, so the owner is really choosing a robot weight. One option is a 0.9 kg servo robot that cannot fully hop. The other is a 1.1–1.3 kg brushless robot that can. The heavier body raises the load it has to lift: about 0.17–0.18 Nm steady and 0.45–0.5 Nm peak per lift joint for the same hop (E). The GL30 has the headroom to absorb that, with bursts of about 1.8–2.2 A at 8:1, near its listed 2.1–2.3 A rating and drawing about 55–60 W from the bus (E). The 2804-100T does not. Holding the 1.5 A cap instead gives about three-quarters of the planned push (E).

The next limit is probably space, not power. Lift joints about 38 mm across at a 52 mm hip spacing leave only about 2–3 mm when neighbours swing toward each other, and the 75 mm-wide phone pushes the middle hips outboard (E). That geometry belongs in `cad/check.py` before anything is ordered. The dock, by contrast, turned out simpler than planned: one switch and plain USB-C replace a dual-role power chip. Only phone charging cannot be settled on paper.

### Recommended parts set, with alternatives

| Job | Recommended part | Qty (with spares) | Key numbers | Price seen | Licence or openness | Alternatives |
|---|---|---|---|---|---|---|
| Lift motors | **CubeMars GL30 KV290**, bare | 6 + 1 | Ø34.5 × 15.7 mm, 41 g, 1.53 Ω across two leads, KV 255, 12 V rated (O/S) | $50.99 (O, sold out); $79 (S) | commercial part | DFRobot 2804 if its mass checks out; GM3506 (64 g) only if a 40 mm hip is allowed |
| Swing motors | **iPower GBM2804H-100T** | 6 + 1 | Ø35 × 15 mm, 39 g, 10 Ω (O) | $18.99 (O) | commercial part | GL30 (one part to stock); 2204 260KV if its resistance measures low |
| Gear stage | **Printed single-stage planetary, 8:1**, PETG or nylon | 12 + 2 | ring ~35–38 mm across, ≤15 mm deep, 6–12 g (E) | filament | Pebble's own design; TipTapMotor (MIT) as reference | two-stage planetary for 10:1 or more; preloaded cycloidal |
| Output bearing | thin-section ball bearing sized to the gear carrier (not researched) | 12 | 3–6 g (E) | not researched | — | — |
| Encoder | **MT6701** on the joint board, read over SPI or SSI | 12 | 14-bit (O) | ~$7 as a module (S) | chip | MT6835 for finer angles; AS5047P |
| Magnet | **Ø6 × 2.5 mm NdFeB, magnetised across the face** | 12 + 4 | air gap ~0.5–3 mm (S) | not found | — | — |
| Joint board | **SimpleFOC-microspora v1.7, Pebble version** (CAN-FD transceiver, EN and nFAULT brought out, 0.375 V/A gain, JST-GH) | 12 + 2 | 33 × 34 mm, STM32G431 + DRV8316 + MT6701 (O) | ~$20 each to make (O) | **MIT** | six two-motor leg boards later; SimpleFOC Mini v2.3 with central processors |
| Joint firmware | SimpleFOC plus an ODRI-style command frame and a timeout | — | 15–16 kHz current loop (F) | — | MIT (SimpleFOC); BSD (ODRI) | moteus firmware as a reference (Apache-2.0) |
| Main processor | **Waveshare ESP32-S3-Zero** on a ~60 × 40 mm carrier | 1 + 1 | 23.5 × 18 mm, ~24 pins, 800 mA regulator (O) | not captured | schematic licence not stated | XIAO ESP32S3 Plus; ESP32-S3-MINI-1-N4R2 soldered on |
| Motor bus | **2 × MCP2518FD + 2 × TJA1051T/3** (one bus per side) | 2 sets | up to 8 Mbps data (S) | CAN Pal £3.80 (S) | chips | built-in classic CAN plus one MCP2518FD in classic mode (~250–400 Hz) |
| IMU | **Adafruit LSM6DSO32** to prototype; **ICM-45686** on the carrier | 1 each | ±32 g (O) | $12.50 (O) | Adafruit board design CC BY-SA if copied | ICM-42688-P if landings stay under ~12 g; BMI088 |
| Edge distance | **Pololu VL53L4CD #3692** | 1 | 1 mm–1.2 m, 18°, 100 Hz (O) | $16.95 (S) | — | VL53L0X (today's part) |
| Edge hardware cut | **Pololu digital distance sensor**, 5 cm (#5550) or 10 cm | 1 | on/off output; Sharp predecessor updated every 2.56 ms (O) | not captured | — | Sharp GP2Y0D805Z0F while stock lasts |
| Power monitor | **INA228** with a 2 mΩ shunt on the carrier (Adafruit #5832 on the bench) | 1 | 20-bit, 85 V, 75 µs alert (O) | not captured | — | Adafruit INA238 board |
| Safety chip | **CH32V003** (TSSOP-20) plus a **TPS3430** watchdog | 1 + 1 | two watchdogs in the CH32V003 (S) | "under 10 cents" claim (S) | — | TPS3430 with logic gates only |
| Motor power cut | **TPS25982** electronic fuse at ~8–10 A | 1 | 2.7–24 V, 2–15 A, under 400 ns short trip (S) | not captured | — | 2 × TPS25947; LTC4365 or LM74502 with two MOSFETs |
| 9 V request | **WCH CH224Q** in I²C mode | 1 | 2 × 2 mm, reads the bank's offers (O) | not captured | — | HUSB238 |
| Bank current limit | **TPS25947** in current-limit mode, ~2.2 A | 1 | 2.7–23 V, 28 mΩ, 2 × 2 mm (O) | not captured | — | — |
| Hop buffer | **4 × Maxwell BCAP0010 P270 S01** (or X01) | 4 + 1 | 10 F, 2.7 V, ≤30 mΩ, 3.1 g each (O) | not found; JLCPCB stocks X01 (S) | — | 4 × Eaton HV1020 5 F (lighter, deeper dip) |
| Battery | **Xiaomi UltraThin Magnetic Power Bank 5000, MDY-20-EB** | 1 | 98.5 × 71.5 × 6 mm, 98 g, 9 V 2.5 A (O) | NZ$79.19–99 (S) | sealed product | 27 W version (check its 9 V current); 2S pack with charger |
| Dock | multi-port USB-C charger, 45–65 W, sprung pins, belly pads, port switch in the body | 1 | six pads plus optional "docked" pad (E) | not researched | — | one dock input with a USB power source chip in the body |
| Phone charging | off-the-shelf USB-C adapter that passes charger power through (test first) | 1 | — | — | — | Android Open Accessory; wireless coil in the backrest |
| Signal cables | **JST-GH 1.25 mm**, Pixhawk pinouts | — | ~1 A per pin, 50 V (O) | — | — | JST-SH (Qwiic) on the bench only |

The joint set costs about **$770** for seven GL30s, seven GBM2804Hs and fourteen boards, before gears, bearings and magnets (E). By comparison, twelve moteus-c1 boards alone cost $732–828, and the light servo set costs about $1,030. The estimated weight of the recommended robot:

| Part | Grams | Grade |
|---|---|---|
| Galaxy Z Flip 7, folded | 188 | repo (`plans/new-bodies.md`) |
| Xiaomi bank | 98 | O |
| 6 lift joints (GL30 + gear + bearing + magnet + screws) | 318–372 | E |
| 6 swing joints (GBM2804H + the same) | 306–360 | E |
| 12 joint boards | ~60 | E |
| Supercapacitors | ~13 | O |
| Carrier with ESP32, IMU, CAN, power and safety parts, plus nose sensors | ~25–30 | E |
| Legs and feet | ~60–80 | E |
| Deck, phone holder and belly | ~50–80 | E |
| Wiring and plugs | ~15–25 | E |
| **Total** | **~1,130–1,300** | E |

The plan's target is 850–920 g. With smart servos instead (set A), the joints are 246 g of servos plus horns and brackets, and the robot stays near the plan.

**Licence flags.** Watch these:
- **The Waveshare-derived SCServo code and Waveshare's ugv_base_general are GPL-3.0 (copyleft):** do not use them.
- **The arduino-esp32 core is LGPL-2.1 (weak copyleft):** fine to build on, but changes to the core must stay LGPL.
- **Adafruit and SparkFun board designs are usually CC BY-SA (share-alike)** ([SparkFun repo](https://github.com/sparkfun/LilyPad_Arduino_Simple); [cadlab mirror](https://cadlab.io/project/2057/master/files/misc/Adafruit-VL53L0X-ToF-Distance-Sensor-PCB-master)). This only matters if their layouts are copied into Pebble's own boards.
- **Some older SparkFun designs carried non-commercial wording** ("please do not use our code or schematics for commercial use") ([SparkFun forum](https://community.sparkfun.com/t/restrictions-on-sparkfun-open-source-hardware-components/15405)). Check any SparkFun layout before copying it.
- **ODrive's current firmware is closed source.**
- **Licences not stated or not checked:** CM6, OpenMutt, the cycloidal projects, Tinymovr, MKS ESP32 FOC, Unexpected Maker's design files, the CH224A trigger board, Seeed/Waveshare/LilyGO schematics, and the TDK, ST and Bosch IMU drivers. Treat them as all rights reserved until checked.
- **Permissive, safe to build on:** SimpleFOC and microspora (MIT), moteus (Apache-2.0), ODRI (BSD-3 and BSD-2), TipTapMotor (MIT), DynamixelSDK (Apache-2.0), FTServo (MIT) and LeRobot (Apache-2.0).

No non-commercial licence was found on any recommended part.

### Body-design dimensions table

| Part | Size (mm) | Mass (g) | Mounting and connections | Grade |
|---|---|---|---|---|
| **GL30 lift motor** | Ø34.5 × 15.7; 6 mm through-hole | 41 | 4 × M3 on the rotor face (drives the sun gear), 3 × M2.5 on the stator face (bolts to the hip); bolt circles not found, so take them from the official STEP; three motor leads (length not found) | size and mass O; holes S |
| **GBM2804H-100T swing motor** | Ø35 × 15; hollow shaft about 7 mm across | 39 | holes "see drawing"; a sibling RCTimer 2804 has base holes 16 and 19 mm apart and rotor holes 12 mm apart (a lead only) | O; holes S |
| **8:1 printed planetary** | ring ~35–38 across, ≤15 deep; module 0.5–0.6; sun 9–12 teeth | 6–12, plus bearing 3–6 | sun on the rotor face; carrier output to the thigh or swing arm; about 0.1 mm extra tooth clearance | E |
| **Joint stack** (board + motor + gear) | ~Ø35–38 × 33–40 long | ~51–63, plus ~5 board | — | E |
| **Encoder magnet** | Ø6 × 2.5, magnetised across the face | <1 | printed holder in the rear end of the hollow shaft; ~0.5–3 mm gap to the MT6701 | S |
| **MT6701 chip** (on the board) | SOP-8 ~5 × 3.9 × 1.75, or QFN 3 × 3 | — | centred on the motor axis | O |
| **Joint board** (microspora v1.7) | 33 × 34 | ~5 (not published) | 3 slots 3.2 × 5 mm for M2 or M3, 22–28 mm apart; a printed adapter if the motor's rear holes differ; CAN in and out (two 3-pin JST today), 6-pin SPI, 5-pin I²C; 9 V power pair | O; mass E |
| Hip stack height (swing joint under lift joint) | ~70–80 tall | — | sets the lift-axis height and the leg geometry | E |
| Neighbour clearance at 52 mm spacing | ~14–16 at rest; ~2–3 when neighbours swing 25° toward each other | — | fixes: widen the spacing to ~56–58 mm, splay the front and back legs, limit opposite swings to about ±20°, or set neighbours at different heights | E |
| **Galaxy Z Flip 7, folded** | 85.5 × 75.2 × 13.7; ~55 front to back when leaned 30° | 188 | hinge down, 30° back, right-angle USB-C at the top pointing back; if it stands between the middle hips, those hip stacks must sit outboard of about ±59 mm from the centre line | repo; E |
| **Xiaomi bank** | 98.5 × 71.5 × 6 (5.87 measured) | 98 | flat in the belly, wireless face down, metal and coils kept off the face; one USB-C port (position not in the notes, so measure it); keep the hip stacks outboard of ±36 mm or above it | O |
| **4 × Maxwell 10 F supercapacitors** | each Ø10 × 30.5; e.g. a ~41 × 31 × 10 block side by side | ~12.6 | in series with 4 × 10 kΩ balancing; along the spine | O; layout E |
| Alternative: 4 × Eaton 5 F | each Ø10 × 22.3 (or 10.5 × 21.2) | ~9.2 | as above | O, conflict |
| Precharge resistor | 10–15 Ω, 3 W, plus a bypass MOSFET | — | on the carrier or the bus board | E |
| **Carrier board** | ~60 × 40 | — | 4 × M2; rigid at the body's centre under the phone holder; carries the IMU | E |
| **ESP32-S3-Zero** | 23.5 × 18 | not found | soldered flat by its edge pads, no holes; antenna clear of metal; USB-C cable to the phone | O |
| ESP32-S3-MINI-1 (option) | 15.4 × 20.5 × 2.4 | — | oven-soldered onto the carrier | O |
| MCP2518FD (×2) | SOIC-14 | — | SPI to the ESP32 | S |
| TJA1051T/3 (×2) | SO-8 or 3.0 × 3.0 DFN-8 | — | needs 5 V plus 3.3 V logic | S |
| CH224Q | 2 × 2 DFN-10 | — | I²C 0x22 or 0x23; on the bank's USB-C line | O |
| TPS25947 | 2 × 2 QFN-10 | — | between the 9 V request chip and the bus | O |
| TPS25982 | 4 × 4 | — | between the bus and the joint boards | S |
| CH32V003 / TPS3430 | TSSOP-20 / 3 × 3 VSON-10 | — | on the carrier | S / O |
| INA228 bench board (#5832) | 25.8 × 20.2 × 10.1 | 3.3 | 3.5 mm screw terminals, Qwiic | S |
| Adafruit LSM6DSO32 (prototype IMU) | not given; the sibling LSM6DSOX board is 25.6 × 17.8 × 4.6 | — | SPI pads, Qwiic | O |
| SparkFun Micro LSM6DSV16X (option) | 19.05 × 7.62 | — | Qwiic | O |
| **Pololu VL53L4CD #3692** | 13 × 18 × 2 | ~0.5 (the same board as the VL53L0X carrier) | I²C at 0x29 with the shutdown-pin readdressing used today; nose, pitched down and forward to fit the 7–22 mm nose slope; holes not given, so check Pololu's drawing | O |
| **Pololu digital distance sensor** | same outline as the Sharp carriers; the Sharp sensor is 13.6 × 7 × 7.96 | ~0.8 (Sharp) | 3-pin JST-GH to the safety chip; floor mid-range when standing | O |
| Dock pads on the belly | 6 pads plus optional "docked"; today's pads are 30 × 4 mm brass | — | flush or recessed, ground pads first to touch; two pairs of 10 × 3 mm magnets; Hall sensor | repo; E |
| Dock pins | 3 A sprung pins on today's dock; two per power line | — | pointing up from a 1–3 mm pad in a locating recess | repo; E |
| Dock tag | AprilTag tag36h11 id 0, 48 mm | — | read to about 2 m | repo |
| Signal plugs | JST-GH, 1.25 mm pitch | — | 4-pin CAN (5 V, CAN_H, CAN_L, GND), 4-pin I²C; 26 AWG | O |
| Servo option: X330 | 20 × 34 × 26 | 18–23 | ROBOTIS FPX330 frames; horn pattern not captured | O |
| Servo option: STS3032 | 23.2 × 12.1 × 28.5 | 20 | 25-tooth spline | S |

### Decisions the owner must make

| Decision | Options | What it changes | Suggested default |
|---|---|---|---|
| **Joint weight or hop** | (a) accept ~51–63 g brushless joints and a ~1.1–1.3 kg robot; (b) keep ~25 g joints with XC330/XL330 servos and a hop of ~0.25 Nm at 10 rad/s; (c) cheap 2804-100T joints with a weak hop | (a) meets the hop but breaks the weight target; (b) keeps 850–920 g but reverses the brushless/FOC decision; (c) is as heavy as (a) and weaker | (a), after the bench joint proves it |
| **Lift burst current** | keep 1.5 A; allow ~2 A bursts | ~2 A restores the full hop at the heavier weight but draws ~55–60 W from the bus | allow ~2 A with a thermal cap, if the bench test passes |
| **Swing motor** | GBM2804H-100T; GL30 | saves ~$32 a joint, against one part type and more speed margin | GBM2804H-100T |
| **Joint electronics** | 12 one-motor boards; 6 two-motor leg boards; a smart-servo bus | 12 boards work with stock firmware today; 6 halve the idle power but need new firmware | 12 one-motor boards |
| **Motor bus** | 2 × CAN-FD; classic CAN | CAN-FD gives ~1 kHz; classic gives ~250–400 Hz with the joints filling in between | 2 × CAN-FD |
| **Hip layout at 52 mm spacing** | wider spacing (~56–58 mm); splayed front and back legs; swing limited to ~±20° when neighbours move opposite ways; staggered heights | collision margin, foot reach, deck size | decide in `cad/check.py` |
| **Edge cut during hops** | a short blanking window, only while the safety chip itself senses a launch; no blanking (no hops near edges); edge cut only while walking | whether hops are possible with the hardware cut armed | a short window armed by the safety chip's own sensing |
| **Lost link** | brake and hold; go limp | how the body behaves if the ESP32 stops talking | brake and hold in firmware; a hardware trip goes limp |
| **Bank version** | original 22.5 W; the new 27 W version | possibly more current at 9 V | check the 27 W version's 9 V current first |
| **Dock power** | USB-C on sprung pins with the in-body switch; 2S pack with its own charger | the motors are off while docked versus a custom lithium design | USB-C on sprung pins |
| **Phone charging** | pass-through adapter (phone stays USB host); Android Open Accessory (body becomes host); wireless coil | Open Accessory reverses the phone-as-host decision | test the pass-through adapter first |
| **Main board form** | ESP32-S3-Zero on a carrier; MINI-1 soldered onto one board | easier for other builders versus fewer parts | the Zero on a carrier |
| **IMU** | ICM-45686; ICM-42688-P; BMI088 | landing headroom versus mature drivers versus vibration | decide after the drop test |

### Bench tests before committing

| Test | How | Pass mark | Decides |
|---|---|---|---|
| **Motor constants** (GL30, GBM2804H, and a 2204 if tried) | measure resistance across two leads; spin each motor to get its KV; measure Kt with a lever and scale at a known current; feel and log cogging under load | Kt within ~15 % of the listing; GL30 near 1.5 Ω across two leads | motor choice, gear ratio |
| **One printed 8:1 stage** in PETG, nylon and PLA | weigh it; measure play at the output; compare torque in and out; drop a weighted leg on it repeatedly | joint ≤ ~55 g; play well under 1°; efficiency ≥ ~80 %; no broken teeth | gear material, joint mass |
| **Hop push** on one lift joint at 9 V with a joint board and the supercapacitors | drive 0.35 Nm (and 0.45 Nm) at 10 rad/s into a weighted arm | holds torque at speed; bus stays above 8 V; the board does not reset | hop target, burst current, capacitor size |
| **Heat** | hold 0.13 and 0.17 Nm for 30 minutes inside a closed mock-up of the body | motor and board temperatures acceptable (limits not published) | vents, current caps |
| **Joint board at 9 V** | current-loop noise at 0.3–1.5 A; crosstalk between phases; lowest input voltage before reset; enable and fault lines; command timeout leading to braking | clean current; survives dips to 7.7–8.4 V | the Pebble board version |
| **Bus timing** | ESP32-S3 with two MCP2518FDs and 6 boards each (or stand-ins) at 500 Hz and 1 kHz, with the phone link running | 1 kHz at ≤ ~60–70 % bus load, no lost frames | bus design |
| **Bank behaviour** | step a load from 300 mA down to 10 mA at 5 V and 9 V and time the switch-off; wake it by breaking CC; try more than 2.5 A at 9 V; move the port from the sink to a charger within seconds; check the 27 W version's offers | known switch-off threshold; wake works every time; it limits rather than latching off | power firmware, bank version |
| **Hop pulse on the power path** | 60 W for 0.1 s, then ten hops at 1 Hz, through the 2.2 A fuse and the capacitors; log bank current and fuse temperature; check no current flows back into the bank; time the precharge | bank never above 2.5 A; fuse within its limits | fuse setting, capacitor size |
| **Safety cut** | stop the heartbeat, uncover the IR sensor, tilt the body, trigger the INA228 alert, press stop; cut power while the legs are moving | motor power off within a few ms of the sensor; re-arms only on a deliberate command; the voltage spike stays below the TVS and driver limits | safety design, the laws |
| **IMU drop test** | the ±32 g LSM6DSO32 on the body, through hops and drops at the planned heights | peak g recorded | ICM-42688-P against ICM-45686 or BMI088 |
| **Edge sensors** on the owner's real desks (dark, shiny, glass, wood) | resting, standing, walking and hopping | floor seen in every stance; an edge seen well before the front feet reach it | sensor range and angle |
| **Phone on the dock** | Flip 7 through a pass-through adapter: does it charge while running the ESP32, does the ESP32 stay connected, what happens when dock power appears and goes; how much current the phone's USB gives; does wireless charging work while it runs a USB device | phone charges at ~15 W or more with the link up | phone-charging path |
| **Dock contacts** | contact resistance at 2.5–3 A under the robot's weight; seating with the magnets; a coin and a metal desk on the pins; whether the charger resets its ports when a second port connects | pins stay cool; pads dead off the dock; no port resets | dock design |
| **Fit check** in `cad/check.py` | real joint envelopes at 25° opposite swings; phone, bank and supercapacitor clearances | ≥ ~2–3 mm everywhere (E) | hip spacing and layout |
| **Noise** | sound of one joint walking and hopping on a desk | acceptable to the owner for a desk pet | gear material, motor choice |
