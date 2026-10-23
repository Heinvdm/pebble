# FOC driver boards and chips for a 12-motor mini hexapod (Pebble, Z Flip 7 body)

Research date: 2026-10-17. All prices were seen on that date unless a different date is given.

How to read the evidence tags:
- **[D]**: read directly from the page or file linked (mostly GitHub repos and raw doc files).
- **[S]**: taken from a search engine's extract of the linked page. The page itself could not be opened from this session, because mjbots.com, docs.simplefoc.com, odriverobotics.com, st.com, ti.com, hackaday.io, makerfabs.com and community.simplefoc.com all failed DNS lookups. Treat [S] figures as good leads to check on the page itself.
- **(official)**: from the maker's own repo, docs or store. **(seller)**: a retailer listing. **(forum)**: a community post. **(3P)**: another third-party page.
- **[Est]**: my own calculation or estimate, with the working shown.

A key constraint runs through all of this. The bus is **9 V** (USB-C PD), with supercapacitor bursts, so a driver has to work across about 8–12 V. **moteus (all models), ODrive Micro/S1, Tinymovr M5 and the B-G431B-ESC1 are all rated for 10 V or 12 V minimum**, or 3S nominal. That rules them out at 9 V unless the bus is raised to 12 V or more.

## Single-axis boards: what exists, with exact numbers

### Takeaway
Two families of small boards run from 9 V with real current sensing:
- DRV8316-based boards: SimpleFOC Mini v2.3 (driver only, 24 × 25 mm) and SimpleFOC-microspora v1.7 (an all-in-one STM32G431 + DRV8316 + MT6701 + CAN board, 33 × 34 mm, MIT, about US$20 to make at JLCPCB).
- Older DRV8313 boards, which have no current sensing.

The polished commercial servo boards are excellent but are rated for 10 V minimum and cost $69–$89 each:
- moteus-c1: 38 × 38 mm, 8.9 g, Apache-2.0 hardware and firmware.
- ODrive Micro: 32 × 32 mm, 6.8 g, closed firmware.
- Tinymovr M5: 29.5 × 29.5 mm, 8 g.

### Cited Findings

**Catalogue table (single-axis).** Each row's details and sources are in the bullets below it.

| Board | Power stage | MCU | Size (mm) | Holes | Mass (g) | Vin (V) | Phase current | Current sensing | Encoder | Link | Firmware / licence | Price (USD) | Runs at 9 V? |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SimpleFOC Mini v1.1 | DRV8313 | none | 20 × 26 | not stated | not found | 8–35 | 2.5 A/phase max | none | none (on MCU) | 3PWM + EN | SimpleFOC (MIT) / HW MIT badge | not found | yes, little margin |
| SimpleFOC Mini v2.3 (2025-07) | DRV8316 (3PWM) | none | 24 × 25 | not stated | not found | 5–35 | 8 A max (chip peak) | 3-phase low-side, 150 mV/A | none (on MCU) | 3PWM + EN | SimpleFOC (MIT) / MIT | ~€5 to make (JLCPCB) | yes |
| SimpleFOC-microspora v1.7 (2026-06) | DRV8316 (SPI) | STM32G431CBU6 | 33 × 34 | 3 slots 3.2 × 5 (M2/M3), 22–28 spacing | not found | 5–35 (README) / 8–35 (docs) | 8 A max | 3-phase (ISENS A/B/C) + Vbus sense | MT6701 onboard (SPI) | CAN (2 × JST-3, 1 Mbps in example) | SimpleFOC (MIT) / MIT | ~$20 to make (JLCPCB); Makerfabs price not found | yes |
| SimpleFOCShield v3.2 | DRV8313 | none (Arduino shield) | Arduino UNO shield | UNO | not found | 8–35 | 3 A cont, 3.5 A peak | inline ACS712 Hall, ±5 A | on MCU | 3PWM | SimpleFOC (MIT) | not found | yes, but large |
| Dagor rev 2.7 (alpha) | 3 MOSFET half-bridges (DRV8305 likely) | ESP32 | 44 × 44 | not stated | 12 | 5–24 | 40 A peak | shunt resistors | 14-bit magnetic onboard | wired/wireless; RS-485 unfinished | SimpleFOC; repo MIT | not sold | yes, but large and alpha |
| B-G431B-ESC1 | L6387 + STL180N6F7 FETs | STM32G431CB | 30 × 41 incl. ST-LINK part [S] (3P says 50 × 50) | not found | not found | 3S–6S (11.1–22.2 nominal) | 40 A peak | 3 × 3 mΩ shunts, op-amp gain 16 | external (pads) | FDCAN, UART, PWM | ST MCSDK or SimpleFOC (low-side, 1 motor) | $18.59 ST eStore; €16.30 Farnell | no (3S min) |
| moteus-c1 (2024-04) | gate driver + FETs | STM32G4 | 38 × 38 × 9 | not found | 8.9 | 10–51 | 20 A peak; 5 A uncooled, 14 A cooled | yes (internal) | onboard + external | CAN-FD 5 Mbps | moteus, Apache-2.0 (HW too) | $69 (1), $65 (10–99), $61 (100+) | no (10 V min) |
| moteus-n1 | gate driver + FETs | STM32G4 | 46 × 46 × 8 | not found | 14.6 | 10–54 | 100 A peak; 9 A uncooled, 26 A cooled | yes | onboard + external | CAN-FD, RS-422 | Apache-2.0 | not found | no |
| moteus-r4.11 | gate driver + FETs | STM32G4 | 46 × 53 | not found | 14.2 | 10–44 | 100 A peak; 12 A uncooled, 32 A cooled | yes | onboard + external | CAN-FD 5 Mbps | Apache-2.0 | $59 at a reseller (was $79) | no |
| ODrive Micro | integrated | not stated | 32 × 32 × 7.5 | 4 × M3 on 26 × 26 | 6.8 | 10–30 (32 max, 28 rec. max) | 3.5 A cont, 7 A peak | yes | 12-bit magnetic onboard; ext. Hall/ABZ/SPI | CAN 2.0B 1 Mbps (FD planned) | ODrive v0.6, closed source | $89 (1), $79 (100); sold out (US) | no |
| ODrive S1 | FETs | not stated | 66 × 50 | not found | 35 (55 with terminals) | 12–48 (50.5 max) | 40 A cont, 80 A peak | yes | onboard + ext. | CAN, UART, step/dir | closed | $149 | no |
| Tinymovr M5.1 | integrated | not stated | 29.5 × 29.5 | not found | 8 | 12–38 | 5 A cont (Tindie says 6 A) | yes | MA702 onboard | CAN, 2 connectors (daisy chain) | Tinymovr (licence not checked) | not found | no |
| FOCn (PLab, 2024) | DRV8323 + FETs | ESP32-S3 | 85.4 × 62 | not found | not found | 9–45 | 10 A cont, 25 A peak | DRV8323 shunt amps | external | Wi-Fi/BT/USB-C | SimpleFOC | $68.86 (Lectronz) | yes, but far too big |
| SparkFun TMC6300 (ROB-21867) | TMC6300 | none | not found | not found | not found | 2–11 | 2 A peak (1.4 A rms) | one SEN pin (foot-point shunt) | none | 6 PWM | n/a | $17.95 | only just (11 V max) |

**SimpleFOC Mini v1.x (DRV8313)**
- v1.1 is DRV8313-based, 8–35 V, "2.5A per phase" max, no current sensing, no supply-voltage sensing, 3.3 V regulator up to 10 mA, 20 × 26 mm. — [SimpleFOC docs source, boards/simplefoc_mini/index.md](https://raw.githubusercontent.com/simplefoc/simplefoc.github.io/master/docs/boards/simplefoc_mini/index.md) [D] (official)
- The voltage range is quoted differently in different places: 8–24 V in the repo and the v1.0 docs, 8–30 V from DFRobot, 8–35 V in the v1.1 docs. The v1.0 docs give an absolute maximum of 5 A. Sizes quoted range from 26 × 20 to 26 × 21.5 mm. — [SimpleFOCMini repo](https://GitHub.com/simplefoc/SimpleFOCMini), [docs v1.0](https://docs.simplefoc.com/simplefocmini), [DFRobot DRI0058](https://wiki.dfrobot.com/SKU_DRI0058_SimpleFOCMini_BLDC_Driver_Board), [Domoticx](https://domoticx.net/webshop/bldc-3-fase-motor-foc-8-30v-25a-simplefocminiv1-module-drv8313) [S] (official + seller)
- The docs say the board is "primarily designed for gimbal motors with internal resistance R > 10 Ω". The newer product page lists 3 A max and 8–35 V. — [SimpleFOC Mini product v1](https://simplefoc.com/simplefoc_mini_product_v1), [docs](https://docs.simplefoc.com/simplefocmini) [S] (official)

**SimpleFOC Mini v2.x (DRV8316), new in 2025**
- Release log: v1.0 2022-04; v1.1 2024-04; v2.0 2025-01, "a complete redesign around the DRV8316"; v2.3 2025-07, smaller, better layout, supply-voltage sensing added. — [SimpleFOCMini README](https://raw.githubusercontent.com/simplefoc/SimpleFOCMini/main/README.md) [D] (official)
- v2.3 specs: DRV8316 in 3-PWM mode; 5–35 V; 8 A max; three low-side current sensors at 150 mV/A; supply sensing at 0.101 V/V; 3.3 V LDO up to 20 mA; 24 × 25 mm. Its pinout matches v1.1. MIT badge, "fully open-source" (EasyEDA files). JLCPCB production cost is about €5. Sold through Makerfabs and the SimpleFOC shop. — [SimpleFOC docs source](https://raw.githubusercontent.com/simplefoc/simplefoc.github.io/master/docs/boards/simplefoc_mini/index.md); [SimpleFOCMini repo](https://github.com/simplefoc/SimpleFOCMini) [D] (official)
- Caution from the maintainers: "Low-side current sensing isn't supported on every MCU architecture." — [SimpleFOCMini README](https://raw.githubusercontent.com/simplefoc/SimpleFOCMini/main/README.md) [D]
- In the v2.1 design thread, the author reported about 7 % crosstalk from phase C current when phases B and C are sensed. — [SimpleFOCMini v2.1 thread](https://community.simplefoc.com/t/simplefocmini-v2-1/7113) [S] (forum)

**SimpleFOC-microspora v1.7: an all-in-one servo node, new 2025–2026**
- STM32G431CBU6 + DRV8316 (controlled over SPI) + MT6701 magnetic encoder (SPI). 33 × 34 mm. Three mounting slots, 3.2 × 5 mm, for M3 or M2 screws. 5–35 V. 8 A max. Phase current sense on PA0/PA1/PA2. Vbus sense on PB11 (÷11). CAN on PB8/PB9, transceiver enable on PC13, two 3-pin JST connectors for daisy-chaining. 6-pin JST SPI and 5-pin JST I2C/encoder/GPIO connectors, Qwiic/Stemma-style. Reset and boot buttons. MIT. "About $20 to manufacture at JLCPCB". Versions: v0.1 2025-05, v1.7 2026-06. The CAN transceiver part and the current-sense gain are not named. — [SimpleFOC-microspora repo](https://github.com/simplefoc/SimpleFOC-microspora) [D] (official)
- The docs page gives 8–35 V, "max current is around 8A", a 5 V buck limited to about 200 mA, a 120 Ω CAN terminator that can be cut away, CAN at 1 Mbps in the example firmware, and "hole spacing from 22mm to 28mm". The only enable signal listed is CAN_ENABLE (PC13); no driver enable pin is listed. — [microspora connecting.md](https://raw.githubusercontent.com/simplefoc/simplefoc.github.io/master/docs/boards/microspora/connecting.md) [D] (official)
- It is a fork of RamBros' MicroSpora and is sold by Makerfabs. — [microspora index.md](https://raw.githubusercontent.com/simplefoc/simplefoc.github.io/master/docs/boards/microspora/index.md); [RamBros original](https://github.com/rambros3d/MicroSpora-SimpleFOC) [D]

**SimpleFOCShield v2 / v3**
- v3.x moved from the L6234 to the DRV8313, and from INA240 amplifiers to ACS712 Hall sensors (inline, up to 5 A both ways). Max 3 A (3.5 A peak), 8–35 V. Stackable, 2 shields (2 motors) per Arduino. v3.1 (10/22) was a full redesign; v3.2 (04/24) was the official release. A maintainer said the next version switches back to INA amplifiers. — [simplefoc_shield_product_v3](https://simplefoc.com/simplefoc_shield_product_v3), [forum thread](https://community.simplefoc.com/t/current-simplefoc-shield-v3-x-easyeda-files-use-ina240-instead-of-acs712/7916), [Arduino-SimpleFOCShield repo](https://github.com/simplefoc/Arduino-SimpleFOCShield) [S] (official + forum)

**Dagor and Lepton (SimpleFOC community designs)**
- Dagor: ESP32, three MOSFET half-bridges, onboard 14-bit magnetic encoder, current-sense resistors, 5–24 V, "peak RMS up to 40 A", 44 × 44 mm, 12 g. Alpha stage, hardware rev 2.7. RS-485 protocol unfinished; CAN not mentioned. Repo sidebar shows MIT. — [Dagor repo](https://github.com/byDagor/Dagor-Brushless-Controller) [D]; [Dagor product page](https://simplefoc.com/dagor_product) [S]
- Lepton v2: 30 × 40 mm, 2-layer, STM32G031 + Fortior driver + 30 V/80 A MOSFETs, 12 V buck, **no current sensing**, community design. — [Lepton v2 thread](https://community.simplefoc.com/t/lepton-v2-revised-design-tested-working-30v-80a-mosfets/2489) [S] (forum)

**ST B-G431B-ESC1**
- STM32G431CB, L6387 gate drivers, STL180N6F7 MOSFETs, 3 mΩ shunts, op-amp gain 16, three internal op-amps (one per phase), 40 A peak. FDCAN1 on PA11/PB9, with CAN termination control on PC14. — [NuttX B-G431B-ESC1 board doc](https://nuttx.apache.org/docs/latest/platforms/arm/stm32g4/boards/b-g431b-esc1/index.html) [S] (3P)
- Input voltage: Digi-Key's reference design is titled "3S ~ 6S in, 11.1–22.2 VDC". Cirkit Designer gives 9–25.2 V (3P). The ST page gives 30 × 41 mm, including the ST-LINK part (via search extract). Cirkit Designer says 50 × 50 mm. — [Digi-Key ref design 2840](https://www.digikey.it/reference-designs/en/motor-control/2840), [ST product page](https://www.st.com/en/evaluation-tools/b-g431b-esc1.html), [Cirkit Designer](https://docs.cirkitdesigner.com/component/2f9d6e18-0795-435f-a8c5-23619d245e7f/b-g431b-esc1-front-side) [S]
- SimpleFOC docs: "1 motor, 30V/40A", low-side current sensing supported for one motor, inline not supported, fault protection. — [SimpleFOC stm32.md](https://raw.githubusercontent.com/simplefoc/simplefoc.github.io/master/docs/simplefoc_library/hardware/mcus/stm32.md) [D]
- Price: US$18.59 at the ST eStore (listing says "2u", which is unclear); €16.30 excluding VAT at Farnell; 599 SEK at Electrokit; HK$167.90 at RS HK. — [ST eStore](https://estore.st.com/en/products/evaluation-tools/product-evaluation-tools/mcu-mpu-eval-tools/stm32-mcu-mpu-eval-tools/stm32-discovery-kits/b-g431b-esc1.html), [Farnell](https://es.farnell.com/stmicroelectronics/b-g431b-esc1/kit-discovery-control-velocidad/dp/3247670), [Electrokit](https://www.electrokit.com/en/b-g431b-esc1-discovery-kit), [RS HK](https://hkcn.rs-online.com/web/p/microcontroller-development-tools/1939781) [S] (seller)
- An ST moderator says raising the op-amp gain without changing the bias circuit may be dangerous for the board; a user reports gains of 32 and 64 have no effect. — [ST community](https://community.st.com/s/question/0D53W00000DK4nGSAT/i-cant-set-the-opamp-gain-higher-than-16-with-bg431besc1-and-motor-control-workbench) [S] (forum)

**mjbots moteus (c1, n1, r4.11)**
- Electrical limits table: c1 min 10 V, nominal 24 V, abs max 51 V, 20 A peak output, 3 V aux 50 mA, 5 V aux 100 mA. r4: 10 V min, 44 V max, 100 A. n1: 10 V min, 54 V, 100 A. Peak power at a 30 kHz PWM rate: c1 "≤28V 250W, linear derated", ≥41 V 150 W. Allowed power scales with PWM rate (half at 15 kHz). — [moteus hardware.md](https://raw.githubusercontent.com/mjbots/moteus/main/docs/reference/hardware.md) [D] (official)
- Spec table from the README:
  - c1: 10–51 V, 250 W @ 28 V, 8.9 g, 5 A uncooled, 14 A cooled, 20 A peak, 38 × 38 × 9 mm.
  - n1: 10–54 V, 1.3 kW @ 36 V, 14.6 g, 9 / 26 / 100 A, 46 × 46 × 8 mm.
  - r4.11: 10–44 V, 900 W @ 30 V, 14.2 g, 12 / 32 / 100 A, 46 × 53 mm, STM32G4, 5 Mbps CAN-FD, control rate 15–30 kHz, PWM 15–60 kHz.
  - Licence: "All files ... unless otherwise noted, are available under an Apache 2.0 License". The hw/ folder holds the c1, n1, r4.11 and x1 PCB designs.
  - Source: [moteus README](https://github.com/mjbots/moteus) [D] (official)
- Price of c1: US$69 (1), $65 (10–99), $61 (100+). The page shows both "Sold out" and "1302 in stock". Developer kit $149–169. — [mjbots moteus-c1](https://mjbots.com/products/moteus-c1), [dev kit](https://mjbots.com/products/moteus-c1-developer-kit) [S] (official store). EU: €153.21 at DHM Online. — [DHM](https://www.dhm-online.com/en/mjbots/13470-moteus-c1-mjbots.html) [S] (seller). The $69 launch price dates from the 2024-04-30 log. — [Hackaday.io log](https://hackaday.io/project/179234/log/229334) [S]
- c1 drops the RS-422 and AUX1 connector that the n1 has. — [Hackaday.io log](https://hackaday.io/project/179234/log/229334) [S]
- r4.11 at a reseller: $59, was $79. — [reach.dog r4.11](https://m.reach.dog/shop/mjbots-robotic-systems/products/moteus-r4-11) [S] (seller)
- Limits doc: "The maximum electrical frequency is 4kHz." — [moteus limits.md](https://raw.githubusercontent.com/mjbots/moteus/main/docs/reference/limits.md) [D]

**ODrive Micro and S1**
- Micro: 32 × 32 × 7.5 mm, 6.8 g, 4 × M3 on a 26 × 26 mm pattern. 10–30 V (32 V max, 28 V recommended max). 3.5 A continuous, 7 A peak, 100 W continuous, 180 W peak. Onboard 12-bit magnetic encoder plus external Hall/ABZ/SPI. CAN 2.0B at 1 Mbps; the hardware is ready for CAN-FD, but the firmware is only "planned". $89 (1) down to $79 (100), sold out in the US shop; the EU listing says €89. — [ODrive Micro shop](https://shop.odriverobotics.com/products/odrive-micro), [Micro datasheet](https://docs.odriverobotics.com/v/latest/hardware/micro-datasheet.html), [CNX Software 2024-07-29](https://www.cnx-software.com/2024/07/29/odrive-micro-compact-brushless-motor-controller-designed-for-space-constrained-robotics-applications/), [EU shop](https://eu.odriverobotics.com/shop/odrive-micro) [S] (official + press)
- S1: 12–48 V (50.5 V max), 40 A continuous with a heat spreader, 80 A peak, 66 × 50 mm, 35 g (55 g with screw terminals), $149. — [ODrive comparison](https://docs.odriverobotics.com/v/latest/hardware/odrive-comparison.html), [S1 shop](https://shop.odriverobotics.com/products/odrive-s1), [S1 datasheet](https://docs.odriverobotics.com/v/latest/hardware/s1-datasheet.html) [S] (official)
- Firmware for the new generation (Pro, S1, Micro) is not public: "Its source code is currently not publicly available. Access may be available under NDA". v3.6 stays open. — [odriverobotics/odrive GitHub](https://github.com/odriverobotics/odrive) [S] (official)

**Tinymovr M5.1**
- 12–38 V, 5 A max continuous (Tindie says 6 A), 29.5 × 29.5 mm, 8 g. MA702 absolute encoder onboard. Two CAN connectors for daisy-chaining, external 120 Ω terminator needed. Supported motors: 0.5–20 Ω phase resistance, 1e-5 to 1e-2 H inductance. — [ROS wiki mirror](https://whiteoak.umd.edu/roswiki/Robots(2f)tinymovr.html), [robots.ros.org](https://robots.ros.org/tinymovr/), [Tinymovr docs guide](https://tinymovr.readthedocs.io/en/latest/hardware/guide.html), [Tindie](https://www.tindie.com/products/tinymovr/tinymovr-m5/), [Hackster](https://hackster.io/news/the-new-tinymovr-m5-is-a-cute-yet-powerful-brushless-motor-controller-with-python-arduino-support-049180f31da9) [S]

**Other small boards**
- FOCn (PLab, 2024): ESP32-S3 + DRV8323, 9–45 V, 10 A continuous, 25 A peak, 85.4 × 62 mm, $68.86. — [CNX Software 2024-04-22](https://www.cnx-software.com/2024/04/22/focn-esp32-s3-bldc-driver-module-simplefoc/), [Lectronz](https://www.lectronz.com/products/focn) [S]
- SparkFun TMC6300 breakout ROB-21867: $17.95, in stock; 2–11 V; "up to 2A (1.4ARMS)"; SEN (current sense) and DIAG pins; needs 6 PWM signals. — [SparkFun](https://www.sparkfun.com/sparkfun-brushless-motor-driver-3-phase-tmc6300.html), [The Pi Hut](https://thepihut.com/products/sparkfun-brushless-motor-driver-3-phase-tmc6300) [S] (seller)
- AliExpress "mini FOC" boards with MT6701: I found no listing with verified specs. A SimpleFOC thread flags an unvetted "SimpleFOC compatible" dual board on AliExpress whose performance nobody could confirm. SimpleFOC also says AliExpress stores are not linked to the project. — [New? Aliexpress board](https://community.simplefoc.com/t/new-aliexpress-board/2421), [SimpleFOC order page](https://simplefoc.com/order?v=3) [S]

### Inferences
- At 9 V, only the DRV8316 boards (SimpleFOC Mini v2.3, microspora), DRV8313 boards (Mini v1.x, Shield v3), Dagor, the ODRI micro driver (5–32 V, see the multi-axis section) and FOCn are inside their rated range. Every moteus, ODrive and Tinymovr model, and the B-G431B-ESC1, would need the bus raised to 12 V or more. Even at 12 V, moteus/ODrive's 10 V minimum leaves almost no margin for sag during 40–60 W bursts.
- SimpleFOC-microspora v1.7 is the closest ready-made match to the brief: a small single-axis FOC node with an MCU, current sensing, an onboard MT6701 and CAN, at about $20 each to make, MIT licensed and sold by Makerfabs. At 33 × 34 mm it is roughly the size of the back of a 2804-class gimbal motor. My recollection is that 2204 motors are about 27–28 mm across and 2804 about 33–34 mm, so it would overhang a 2204 slightly; check against the chosen motor's drawing.
- Commercial-servo cost for 12 joints [Est]: moteus-c1 12 × $61–69 = $732–828; ODrive Micro 12 × $79–89 = $948–1068; microspora 12 × about $20 = about $240 plus assembly. All are USD.
- The B-G431B-ESC1's sensing is scaled for 40 A [Est]. 3 mΩ × gain 16 = 48 mV/A, and a 12-bit 3.3 V ADC step is about 0.8 mV, so one step is about 17 mA. A 0.5 A current is only about 30 steps. That is coarse for spring-like torque control. The DRV8316's integrated amplifier at 0.375 V/A gives about 2.1 mA per step.

### Gaps
- Mounting-hole patterns for moteus-c1, Tinymovr M5, SimpleFOC Mini v2.3 and B-G431B-ESC1. The board-vendor sites could not be reached, and the moteus pinout and mechanical drawings exist only as images/SVG in the repo.
- Masses of SimpleFOC Mini v2.3 and microspora. Not published in what I could read; by analogy, likely under 6 g [Est, unverified].
- Makerfabs retail prices for SimpleFOC Mini v2.3 and microspora (makerfabs.com did not resolve).
- The microspora CAN transceiver part number, and whether it is CAN-FD rated. The STM32G431 has FDCAN, so CAN-FD depends on the transceiver.
- Tinymovr firmware and hardware licence (not checked). STSPIN32G4-based small boards and DengFOC boards (not reached before the search budget ran out).
- No NZD prices were found for any board. Convert at the rate on the day of purchase.

## Multi-axis boards (2, 4, 6 or more motors)

### Takeaway
I found no ready-made small 4- or 6-motor FOC board with per-motor current sensing that runs at 9 V. The best open multi-motor reference is the ODRI (Solo-12 quadruped) system:
- **Micro Driver v2**: a dual-motor board, 51 × 50 mm, 13 g, 5–32 V, 10 kHz torque control, BSD-3.
- **Master Board**: an ESP32 that talks SPI to up to 8 dual drivers at 1 kHz.

Commercial dual boards (MKS ESP32 FOC, MKS Dual FOC) need 12 V or more and are poorly documented.

### Cited Findings
- ODRI Micro Driver: "dual brushless motor driver electronics", a miniaturised version of TI's evaluation boards. 5–32 V input; the robots run at 24 V. Torque control at 10 kHz per motor. Talks to the Master Board over SPI at 1 kHz. 51 × 50 mm, 13 g. Phase current measured with six 7 mΩ ±1 % shunts. Two encoder connectors plus an SPI connector (Hirose DF13). 6-layer FR4. BSD 3-Clause (MPG and NYU, 2019–2021). — [ODRI micro driver README](https://github.com/open-dynamic-robot-initiative/open_robot_actuator_hardware/blob/master/electronics/micro_driver_electronics/README.md) [D] (official)
- A mirrored ODRI doc gives the same board as "5V - 45V (typically 24V)", up to 15 A continuous (20 A peak) per channel, FOC at 10 kHz. This **conflicts** with the 5–32 V in the README. Its predecessor was a TI LaunchPad F28069M with two DRV8305 BoosterPacks (85 g). — [ODRI TI evaluation boards (mirror)](https://www.mintlify.com/open-dynamic-robot-initiative/open_robot_actuator_hardware/electronics/ti-evaluation-boards), [TI electronics README](https://github.com/open-dynamic-robot-initiative/open_robot_actuator_hardware/blob/master/electronics/ti_electronics/README.md) [S]
- ODRI Master Board: ESP32 (ESP-IDF). Up to 8 SPI slaves ("max 80Mhz, DMA capable"), compatible with the µDriver SPI interface. 1 kHz closed-loop demos. Round trip with a 127-byte message: 1.2 ms over ESP-NOW Wi-Fi, 0.2 ms over raw Ethernet. BSD-2-Clause. — [ODRI master-board repo](https://github.com/open-dynamic-robot-initiative/master-board) [D] (official). A Hackaday log describes 8 SPI lines driving up to 8 dual BLDC drivers. — [Hackaday.io log](https://hackaday.io/project/161896/log/168678) [S]
- MKS ESP32 FOC V2.0: dual-motor, ESP32, "onboard high-precision current sensor", Hall and magnetic encoders. — [Newegg listing](https://www.newegg.com/p/0J2-0788-00977) [S] (seller)
  - A forum user reports two L6234 drivers without a heatsink, and that the board is powered from "12v+". Users report wrong Hall pin assignments in the official examples and "0 direction/help on header pinout". — [Makerbase Dual FOC thread](https://community.simplefoc.com/t/makerbase-dual-foc/2987), [Deng FOC thread](https://community.simplefoc.com/t/deng-foc-board-easy-to-use/1971/16) [S] (forum)
  - The GitHub README (Mega branch) states no specs and no licence. — [MKS-ESP32FOC repo](https://github.com/makerbase-motor/MKS-ESP32FOC) [D]
- MKS Dual FOC (V3.x): 12–48 V, 15 A per channel, 60 × 50 × 15 mm. — [Cirkit Designer](https://docs.cirkitdesigner.com/component/f41fcfaf-536a-4b1a-82b0-1e6631fbf6ed/mks-dual-foc) [S] (3P)
- Storm32 BGC: STM32F103 + DRV8313 driving 3 motors, listed in the SimpleFOC docs. No current sensing. — [SimpleFOC stm32.md](https://raw.githubusercontent.com/simplefoc/simplefoc.github.io/master/docs/simplefoc_library/hardware/mcus/stm32.md) [D]
- ST STEVAL-GMBL02V1: a 3-axis gimbal kit, STM32F303RE + STSPIN233 drivers, 50 × 50 mm. — [STEVAL-GMBL02V1 datasheet mirror](https://www.nyang-tech.com/datasheet/2364163508/STMicroelectronics/STEVAL-GMBL02V1.pdf) [S]
- SimpleFOCShield v3 stacks to 2 motors per Arduino. — [shield v3 product](https://simplefoc.com/simplefoc_shield_product_v3) [S]
- An ESP32-S3 dual FOC ESC ("E²SC") from rbts.co exists, but I could not open its page for specs. — [rbts.co blog](https://rbts.co/Blog/esc-small-dual-foc-hall-esc-based-on-the-esp32-s3) [S]

### Inferences
- Six ODRI-style dual boards (one per leg, serving both the swing and lift motor at that hip) is the proven open pattern for 12 joints: 12 motors on 6 boards on one ESP32. But the ODRI board is 51 × 50 mm and uses a TI C2000 MCU with TI's motor libraries, so it is a design reference, not a part to copy outright. Its 7 mΩ shunts are scaled for 15–20 A, far more than 1.5 A.
- A per-leg 2-axis board halves the node count (6 instead of 12). It also keeps phase and encoder wires short, because both motors of a leg sit at the same hip.

### Gaps
- No 4- or 6-motor small open FOC board with current sensing was found. Robot-specific boards from small open quadrupeds other than ODRI were not covered (the search budget ran out).
- DengFOC (dual ESP32) specs were not retrieved.

## Chips for a custom board: drivers, MCUs, motors per MCU, reference designs

### Takeaway
**DRV8316** suits 9 V and about 1.5 A, with integrated current sensing so no shunts are needed: 4.5–35 V, 8 A peak, 95 mΩ, 7 × 5 mm VQFN, about $4.60 for one, $2.61 at 1k. **DRV8311** is a smaller 5 A part, and its P variant (tSPI) lets one MCU run several motors over SPI. DRV8313 has no sense amplifier. TMC6300 (11 V max) and STSPIN233 (10 V max) are too close to a 9 V bus that rises with supercaps and back-EMF.

On the MCU side, SimpleFOC officially supports low-side current sensing for **one motor per STM32**. The ESP32's MCPWM gives at most four 3-PWM drivers. A multi-motor board therefore means either one small MCU per motor, or custom firmware.

### Cited Findings
**Driver ICs**
- **TI DRV8316**: 4.5–35 V (40 V abs max), 8 A peak, 95 mΩ HS+LS at 25 °C, integrated current sensing (no external sense resistors), VQFN-40 (RGF) 7 × 5 mm. Datasheet Rev. B, 2021-09-17. Variants: R (SPI), T (hardware-set), and an automotive Q1 part. — [TI DRV8316](https://www.ti.com/product/DRV8316), [DRV8316-Q1](https://www.ti.com/product/DRV8316-Q1) [S] (official)
  - A DRV8316C variant exists (Digi-Key lists DRV8316CRRGFR). — [Digi-Key](https://punchouttest.digikey.com.mx/en/products/detail/texas-instruments/DRV8316CRRGFR/17395029) [S]
  - Register options from the SimpleFOC driver library: current-sense gain 0.15 / 0.1875 / 0.25 / 0.375 V/A; PWM modes 6PWM, 6PWM with current limit, 3PWM, 3PWM with current limit; slew rate 25 / 50 / 150 / 200 V/µs; overcurrent level 16 A or 24 A; optional EN (active-low option) and nFAULT pins; a `setDriverOffEnabled()` register call. — [Arduino-FOC-drivers drv8316.h](https://raw.githubusercontent.com/simplefoc/Arduino-FOC-drivers/master/src/drivers/drv8316/drv8316.h) [D]
  - Price: Digi-Key US about $4.60 (1) and about $2.61 (1k, cut tape) for DRV8316RRGFR. Some regional Digi-Key pages showed it out of stock, 6-week lead time. — [Digi-Key DRV8316RRGFR](https://digikey.cn/en/products/detail/texas-instruments/DRV8316RRGFR/16592525) [S] (distributor). The LCSC price was not found.
- **TI DRV8311**: 5 A peak, 210 mΩ HS+LS at 25 °C, three integrated current-sense amplifiers, 24-pin RRW package. Variants: H (hardware), S (SPI), P (tSPI). The DRV8311P "provides capability to generate and configure PWM timers over ... tSPI, and allows the control of multiple BLDC motors directly over the tSPI interface", using standard 4-wire SPI, which "reduces the number of required I/O ports". Digi-Key: active, 6-week lead time. — [TI DRV8311](https://ti.com/product/DRV8311), [datasheet SLVSFN2B](https://ti.com/document-viewer/DRV8311/datasheet/GUID-7E542EF0-1E0A-43D8-828B-5FEF50B87F07), [Digi-Key DRV8311HRRWR](https://digikey.cn/en/products/detail/texas-instruments/DRV8311HRRWR/16186290) [S]
  - A TI forum post describes one MCU driving six DRV8311P chips in two tSPI groups of three. — [ti2k.com forum mirror](https://www.ti2k.com/183233.html) [S] (forum)
- **TI DRV8313**: about 8–60 V; 2.5 A peak or 1.75 A rms per half-bridge (24 V, 25 °C, with PCB heatsinking); 28-pin HTSSOP PowerPAD. Each half-bridge has its own ground pin for low-side shunt sensing, plus an uncommitted comparator. Overcurrent, short-circuit, undervoltage and overtemperature protection. A third-party parametric listing gives 480 mΩ HS+LS. — [Mouser DRV8313 datasheet](https://mouser.com/datasheet/2/405/drv8313-441257.pdf), [Mouser DRV8313 page](https://www.mouser.com.tr/TI-DRV8313-hbridge), [radiolocman](https://www.radiolocman.com/datasheet/data.html?di=201537) [S]
- **ADI/Trinamic TMC6300**: 2–11 V; up to 2 A peak; "1.2A" rms in the datasheet order code (TMC6300-LA, QFN20) **versus** "1.4A RMS" on ADI's product page. About 170 mΩ per side. Current feedback "via a single foot-point shunt". Standby under 50 nA. — [TMC6300 datasheet rev1.08](https://www-cce.cldnet.analog.com/media/en/technical-documentation/data-sheets/TMC6300_datasheet_rev1.08.pdf), [ADI TMC6300](https://www.analog.com/en/products/tmc6300.html), [TMC6300-BOB datasheet](https://www.mouser.com/datasheet/2/256/TMC6300-BOB_Datasheet_Rev1.00-1880634.pdf) [S] (official)
- **ST STSPIN233**: 1.8–10 V, 1.3 A rms, three-shunt sensing, VFQFPN 3 × 3 × 1.0 mm. 0.4 Ω HS+LS typical per ST; Embedded.com says 200 mΩ (conflict). OCP, OTP and short-circuit protection. Standby under 80 nA. Aimed at gimbals, drones and robotics. — [ST STSPIN233](https://st.com/en/motor-drivers/stspin233.html), [AllAboutCircuits](https://allaboutcircuits.com/news/motor-driver-three-phase-battery-operated-motors-STMicroelectronics), [Embedded.com](https://www.embedded.com/?p=6220) [S]

**MCUs and how many motors each can run**
- STM32G474: "3 x 16-bit 8-channel advanced motor control timers", five fast 12-bit ADCs, seven comparators, six op-amps. — [embeddedrelated STM32G474](https://www.embeddedrelated.com/parts/p/STM32G474RET6), [Future Electronics](https://www.futureelectronics.com/ftm/motor-control/stmicroelectronics-stm32g474-series-microcontrollers/) [S]
  - On a SimpleFOC forum: "G431 can do 15-16KHz in foc_current mode, so 3 motors will be a little over 5KHz update rate". Advanced timers are needed only for 6PWM; 3PWM can use general timers. — [SimpleFOC forum: 3 BLDC on STM32G474](https://community.simplefoc.com/t/is-it-possible-to-control-3-bldc-closed-loop-motor-in-foc-with-a-stm32g474-ic/7116) [S] (forum)
  - Dual-motor FOC on one STM32 is done by offsetting the two timers so each motor's current sample lands at the right moment (hoverboard firmware); with two ADCs this is not needed. — [Arduino-FOC PR #374](https://github.com/simplefoc/Arduino-FOC/pull/374) [S]
- SimpleFOC current-sensing support table: STM32 F1/F4/G4/L4/F7/H7 inline yes, low-side "(one motor)". B-G431B-ESC1 low-side (one motor). ESP32/ESP32-S3 inline and low-side. ESP32-S2/C3 inline only. RP2040 ("Raspberry Pi Pico") inline only. — [SimpleFOC mcus/index.md](https://raw.githubusercontent.com/simplefoc/simplefoc.github.io/master/docs/simplefoc_library/hardware/mcus/index.md) [D]
  - **Conflict**: the library README says STM32 supports "multiple motors low-side CS (one per ADC)". — [Arduino-FOC README](https://github.com/simplefoc/Arduino-FOC) [D]
- The SimpleFOC library is MIT licensed; the latest release named is v2.4.0. — [Arduino-FOC](https://github.com/simplefoc/Arduino-FOC) [D]
- ESP32 with MCPWM: "4 instances of 3PWM mode drivers, ... 2 instances of 6PWM". Low-side sensing needs timer–ADC sync, which only MCPWM on ESP32 provides; LEDC cannot. The MCPWM hardware has two groups, each with 3 timers and 3 operators. — [SimpleFOC choosing PWM pins / microcontrollers](https://docs.simplefoc.com/microcontrollers), [SimpleFOC esp32 MCPWM source](https://source.simplefoc.com/drivers_2hardware__specific_2esp32_2esp32__mcpwm__mcu_8cpp_source.html) [S]
  - A forum report of a 4th 3PWM instance hanging an STM32F767. — [SimpleFOC forum](https://community.simplefoc.com/t/simplefoc-3pwm-cannot-support-more-than-3-motors-at-a-time/4952) [S]
- RP2040 (Pico): 16 PWMs, 4 ADC pins, ADC "insufficient for low-side current sensing", inline only. RP2350 is not covered in the docs. — [SimpleFOC rpi_pico.md](https://raw.githubusercontent.com/simplefoc/simplefoc.github.io/master/docs/simplefoc_library/hardware/mcus/rpi_pico.md) [D]
- TI TMS320F28069M (the ODRI dual-driver MCU family): 90 MHz C28x with FPU and CLA, up to 256 KB flash, 2 SPI, 1 CAN, 2 UART, up to 8 ePWM, 12-bit ADC. — [TI TMS320F28069M](https://www.ti.com/product/TMS320F28069M) [S]

**Open reference designs**
- Single-axis, open: SimpleFOC-microspora (STM32G431 + DRV8316 + MT6701 + CAN, MIT) [D]; SimpleFOC Mini v2.3 (DRV8316, MIT) [D]; moteus c1/n1/r4.11 (STM32G4, hardware files in hw/, Apache-2.0) [D]. — [microspora](https://github.com/simplefoc/SimpleFOC-microspora), [SimpleFOCMini](https://github.com/simplefoc/SimpleFOCMini), [moteus](https://github.com/mjbots/moteus)
- Dual-axis, open: ODRI Micro Driver (BSD-3) [D]. — [ODRI micro driver](https://github.com/open-dynamic-robot-initiative/open_robot_actuator_hardware/blob/master/electronics/micro_driver_electronics/README.md)

### Inferences
- Current sense range [Est]: the DRV8316's top gain of 0.375 V/A turns ±1.5 A into ±0.56 V, about a third of a 3.3 V ADC's half-range. That is fine. Sense resolution, not driver current, is what matters here. Any of these drivers far exceeds the 1.5 A peak needed.
- Bus voltage, not the driver, limits current [Est]. With space-vector PWM, the largest phase-voltage amplitude is Vbus/√3, so 9/√3 ≈ 5.2 V. For a motor of 10 Ω line-to-line (5 Ω per phase), stall current can reach only about 1.04 A, and less when moving because of back-EMF. Reaching 1.5 A at 9 V needs about 7 Ω or less line-to-line. **Flag for the motor researcher**: check whether "5–15 Ω" means line-to-line or per phase.
- A custom 12-channel board has two realistic shapes:
  - **(a) One MCU per motor.** Twelve STM32G431 + DRV8316 "cells" (UFQFPN48 7 × 7 mm + VQFN 7 × 5 mm each) on one or two PCBs, running stock SimpleFOC (one low-side motor per MCU). This is essentially microspora tiled.
  - **(b) Two motors per MCU.** Six STM32G474s, each running two DRV8316s. TIM1/TIM8 or general timers plus separate ADCs per motor are possible on paper, but need custom dual-motor current-loop firmware, because SimpleFOC's documented low-side support is one motor.
  - A DRV8311P tSPI design moves PWM generation into the driver. The sense amplifier outputs are still analog, so each motor still needs 2–3 ADC channels sampled at the right time.
- ESP32-S3 as the motor MCU: four 3PWM drivers at most with MCPWM (two units), so at least three ESP32-S3 chips for 12 motors. Low-side sensing on several motors per chip is not documented as tested. Not a good fit for the motor side.
- Possible chip cost per motor channel [Est]: DRV8316 about $2.6–4.6, STM32G431 a few dollars (price not looked up), MT6701 (not looked up). This fits microspora's "about $20 per board at JLCPCB".

### Gaps
- DRV8311 supply range and package size (I believe 3–20 V and 3 × 3 mm, but did not confirm). DRV8311P tSPI device count per bus and PWM-sync behaviour.
- STSPIN830, STSPIN32G4 and Allegro parts were not reached (the search budget ran out).
- Prices of STM32G431/G474, MT6701, MCP2518FD and CAN-FD transceivers (LCSC/Digi-Key) were not looked up.
- No published benchmark of 2 or more motors with low-side FOC current loops on one STM32G4 under SimpleFOC. ST's MCSDK dual-motor support was not checked.

## Link to the main ESP32-S3 board (12 joints at 500 Hz or more)

### Takeaway
The ESP32-S3's built-in TWAI is **classic CAN only** (one controller). One classic CAN bus at 1 Mbps cannot carry 12 commands plus 12 replies at 500 Hz; the ceiling is about 310–370 Hz at full load. Workable options:
- CAN-FD through an external MCP2518FD (or two of them, one per side of the body), with a broadcast command frame.
- ODRI-style SPI to 6 two-axis boards. This is proven at 1 kHz on an ESP32, with a 34-byte packet per dual board taking under 35 µs.

moteus users report a 740 µs full cycle for 12 servos plus an IMU over four 5 Mbps CAN-FD buses.

### Cited Findings
- ESP-IDF's TWAI supports classic CAN, not CAN FD, and treats FD frames as errors; FD needs external hardware. A common pattern is an external Microchip MCP2518FD over SPI. The ESP32-S3 has one TWAI controller. — [esp32.com thread](https://esp32.com/viewtopic.php?p=130806), [Copperhill ESP32-S3 CAN-FD board](https://copperhilltech.com/esp32s3-5-480x854-ips-lcd-with-can-fd-and-classical-can-ports/), [esp32_canfd lib](https://github.com/dbstephan/esp32_canfd) [S]
- moteus speaks 5 Mbps CAN-FD. The pi3hat has 4 × 5 Mbps CAN-FD ports. After tuning, "a full cycle of commanding and querying all 12 servos and reading the IMU" took **740 µs** on a quad A1 (one author's result). The FAQ advises isolcpus, real-time priority and mlockall. — [Hackaday.io quad A1 pi3hat log](https://hackaday.io/project/167845/log/179913), [moteus-pi3hat](https://libraries.io/pypi/moteus-pi3hat) [S]
- The moteus Rust example notes that over CAN "there is a watchdog which requires commands to be sent at least every 100ms". — [moteus multiservo.rs](https://docs.rs/crate/moteus/0.5.3/source/src/examples/multiservo.rs) [S]
- ODrive Micro: CAN 2.0B at 1 Mbps, FD "firmware planned". Since v0.6.9 it sends no heartbeat until a node ID is set. — [Micro datasheet](https://docs.odriverobotics.com/v/latest/hardware/micro-datasheet.html), [ODrive changelog](https://docs.odriverobotics.com/v/latest/changelog.html) [S]
- microspora runs CAN at 1 Mbps in its example firmware, with two JST connectors for daisy-chaining. — [microspora connecting.md](https://raw.githubusercontent.com/simplefoc/simplefoc.github.io/master/docs/boards/microspora/connecting.md) [D]
- Tinymovr M5 has two CAN connectors for daisy-chaining and needs an external 120 Ω terminator. — [Tinymovr guide](https://tinymovr.readthedocs.io/en/latest/hardware/guide.html) [S]
- ODRI µDriver SPI protocol, a ready-made impedance-control frame [D]:
  - A 34-byte command per dual board: mode, 2 × 32-bit position, 2 × 16-bit velocity, 2 × 16-bit Iq (feed-forward current), 2 × 16-bit Kp, 2 × 16-bit Kd, 2 × 8-bit current limit, index, CRC32.
  - A 34-byte reply: status, timestamp, positions, velocities, Iq, coil resistances, ADC, last command index, CRC32.
  - 8 MHz SPI mode 1, under 35 µs per transaction, at least 0.7 ms between transactions to the same board. Sensor data updates at about 1.5 kHz. Kp = Kd = 0 gives pure current control.
  - Source: [BLMC µDriver SPI interface](https://raw.githubusercontent.com/open-dynamic-robot-initiative/master-board/master/documentation/BLMC_%C2%B5Driver_SPI_interface.md)
- The ODRI Master Board (ESP32) drives up to 8 such SPI slaves at a 1 kHz loop. — [master-board](https://github.com/open-dynamic-robot-initiative/master-board) [D]

### Inferences
- **Classic CAN at 1 Mbps** [Est]: an 8-byte standard frame is 111 bits plus up to about 24 stuff bits, so 111–135 µs. Twelve commands plus twelve replies is 2.7–3.2 ms, which caps the rate at about 310–370 Hz at 100 % bus load. **This fails 500 Hz.** Packing two joints per frame with 6 two-axis nodes gives 12 frames, 1.3–1.6 ms, about 600–750 Hz at 100 %. That is 500 Hz at 70–80 % load: too tight.
- **CAN-FD at 1/5 Mbps** [Est]: a 16-byte frame takes about 65–70 µs and a 64-byte frame about 160–170 µs.
  - One 64-byte broadcast command (12 joints × 5 bytes) plus 12 16-byte replies is about 1.0 ms per cycle: about 1 kHz at full load, or 500 Hz at about 50 %.
  - Splitting into two buses (left 3 legs, right 3 legs), each on its own MCP2518FD on the ESP32-S3's SPI, roughly halves this.
  - moteus's 740 µs over 4 buses for 12 servos agrees with this order of magnitude.
- **SPI** [Est]: six ODRI-style two-axis boards × under 35 µs is about 0.21 ms per cycle, plus chip-select overhead. That allows 1 kHz with lots of margin (the 0.7 ms gap rule allows about 1.4 kHz per board). SPI is a board-level bus, though. Running 8 MHz SPI over 10–15 cm wires through moving hips needs care: twisted pairs, a slower clock, or RS-485 / LVDS line drivers.
- With 12 single-axis nodes, CAN-FD (2 buses) is the clean choice. With 6 two-axis leg boards, either CAN-FD on one bus or SPI works.

### Gaps
- No measured latency for SimpleFOC over CAN, or for microspora's CAN stack. Not found.
- Not checked: whether microspora's transceiver is CAN-FD rated, and the throughput of MCP2518FD on ESP32-S3 SPI (driver overhead per frame).
- ESP32-S3 UART top baud rate for an RS-485 alternative was not checked.

## Safety: enable/fault lines, cutting motor power, behaviour on lost link

### Takeaway
Every serious option has a command watchdog:
- moteus: `servo.default_timeout_s` and `servo.timeout_mode` (stop, hold, zero velocity or brake).
- ODrive: an optional CAN watchdog.
- ODRI µDriver: a 0–255 ms timeout that cuts current.

SimpleFOC boards have only a driver EN pin (Mini) or nothing listed (microspora), so a timeout must be written into the firmware. For a hard cut of all 12 drivers, use one eFuse on the 9 V motor rail. TI TPS25982 (2.7–24 V, 2–15 A, under 400 ns short-circuit trip) covers 6.7 A bursts. TPS25947 (6 A max) is marginal. Wire the DRV8316 enable and nFAULT pins to a shared line.

### Cited Findings
- moteus `servo.default_timeout_s` is the position-mode command watchdog; `nan` disables it. `servo.timeout_mode`: 0 = stopped (driver off), 10 = slow to zero and hold position, 12 = zero velocity, 15 = brake. `servo.max_voltage` triggers a fault that stops all torque. `servo.max_current_A` caps phase current. `servo.pwm_rate_hz` defaults to 30000 (range 15–60 kHz). — [moteus configuration.md](https://raw.githubusercontent.com/mjbots/moteus/main/docs/reference/configuration.md) [D]
- ODrive: an optional watchdog makes the ODrive stop when the CAN link is broken. — [ODrive Arduino CAN guide](https://docs.odriverobotics.com/v/latest/guides/arduino-can-guide.html) [S]
- ODRI µDriver: an 8-bit timeout, 0–255 ms (0 = infinite). "If no valid command arrives within the timeout, the system is disabled and the motor receives no current"; bad-CRC commands are ignored. — [µDriver SPI interface](https://raw.githubusercontent.com/open-dynamic-robot-initiative/master-board/master/documentation/BLMC_%C2%B5Driver_SPI_interface.md) [D]
- SimpleFOC Mini v2.3 has a 3PWM + ENABLE input. — [SimpleFOCMini](https://github.com/simplefoc/SimpleFOCMini) [D]. The SimpleFOC DRV8316 driver takes optional `en` (can be active-low) and `nFault` pins and has a driver-off register call. — [drv8316.h](https://raw.githubusercontent.com/simplefoc/Arduino-FOC-drivers/master/src/drivers/drv8316/drv8316.h) [D]
- microspora lists no motor-driver enable pin; the only enable is CAN_ENABLE (PC13). — [connecting.md](https://raw.githubusercontent.com/simplefoc/simplefoc.github.io/master/docs/boards/microspora/connecting.md) [D]
- DRV8313: overcurrent, short-circuit, undervoltage and overtemperature protection; an uncommitted comparator usable for a current limit. — [Mouser DRV8313](https://www.mouser.com.tr/TI-DRV8313-hbridge) [S]
- TI TPS25947 eFuse: 2.7–23 V, current limit adjustable up to 6 A, analog current-monitor output, circuit-breaker or current-limit response, adjustable overcurrent blanking time. — [TI TPS25947](https://www.ti.com/product/TPS25947), [Mouser](https://www.mouser.in/new/texas-instruments/ti-tps25947-efuses/) [S]
- TI TPS25982 eFuse: 2.7–24 V, 2–15 A adjustable limit, short-circuit trip in under 400 ns typical, latch-off or auto-retry, 4 × 4 mm. — [Mouser TPS25982](https://www.mouser.fr/new/texas-instruments/ti-tps25982-smart-efuses) [S]

### Inferences
- Burst current [Est]: 40–60 W at 9 V is 4.4–6.7 A. TPS25982 set to about 8–10 A fits. TPS25947's 6 A ceiling is too close. Put the switch **between the supercapacitor bank and the drivers**, so the cut also isolates stored energy. The safety circuit drives the eFuse enable, and the same line also drives every driver's EN/DRVOFF, so the cut works both ways.
- A dead driver lets a back-driven motor act as a generator: back-EMF rectified by the MOSFET body diodes can push the rail up. Keep a TVS or bulk capacitance on the driver side of the switch, and keep the bus below the driver's absolute maximum. The DRV8316 has 40 V abs max, so it has headroom; TMC6300 (11 V) and STSPIN233 (10 V) do not. **This is another reason to avoid those two chips.**
- Cutting power makes the joints go limp, and the body will sag onto its belly. A "brake" mode (all low-side switches on, like moteus `timeout_mode` 15) instead holds the legs softly. The laws and stop handling should choose between them. A reasonable default is: lost link → brake/hold in firmware; safety trip → hardware cut.
- DRV8316 nFAULT pins (open-drain on TI parts, by TI convention; check the datasheet) can be wired-OR'd into one "any driver fault" line to the ESP32-S3 and the safety circuit.

### Gaps
- Not confirmed from the TI datasheet: the DRV8316 DRVOFF/nSLEEP pin behaviour and how long the outputs take to turn off.
- SimpleFOC's built-in command timeout: I found no documented one; assume it must be written.
- ODrive Micro enable pin and its watchdog default value were not retrieved.

## Heat at about 0.5 A continuous in a closed small body

### Takeaway
The boards will barely warm at 0.5 A. Every candidate's continuous rating (DRV8313 1.75 A rms; moteus-c1 5 A uncooled; ODrive Micro 3.5 A) is 3–10 times higher, and DRV8316 conduction loss is about 20 mW per motor. The heat problems in this body are elsewhere:
- **The motors' copper loss**: about 2 W per motor at 0.5 A in a 5 Ω-per-phase winding.
- **The idle draw of 12 MCUs**: perhaps 1–2 W in total.

### Cited Findings
- moteus-c1: 5 A uncooled, 14 A cooled phase current. — [moteus README](https://github.com/mjbots/moteus) [D]
- ODrive Micro: 3.5 A continuous, 100 W. — [ODrive Micro shop](https://shop.odriverobotics.com/products/odrive-micro) [S]
- DRV8313: 1.75 A rms per channel "with proper PCB heatsinking at 24 V and 25 °C". — [Mouser DRV8313](https://www.mouser.com.tr/TI-DRV8313-hbridge) [S]
- Dagor: maximum continuous current "depends on the quality of heat-sinking and cooling". — [Dagor product](https://simplefoc.com/dagor_product) [S]
- moteus: "efficiency of the controller goes down significantly at higher PWM rates". — [moteus hardware.md](https://raw.githubusercontent.com/mjbots/moteus/main/docs/reference/hardware.md) [D]
- A SimpleFOC thread titled "SimpleFOCMini Over Heating" exists (contents not read). — [forum](https://community.simplefoc.com/t/simplefocmini-over-heating-arduino-bldc/3545) [S]

### Inferences
- DRV8316 at 0.5 A amplitude (0.35 A rms) [Est]: about 47.5 mΩ per conducting switch × 3 phases × 0.35² ≈ 18 mW, plus switching loss in the low milliwatts at 20 kHz. DRV8313 (about 240 mΩ per switch): about 90 mW. Even in still air in a closed box this is negligible.
- MCU and regulator idle [Est, unverified]: an STM32G431 at 170 MHz draws perhaps 25–40 mA at 3.3 V (about 0.1 W). Twelve nodes with drivers and regulators come to about 1–2 W of standing load out of a 22.5 W supply. Consolidating to 6 two-axis nodes halves this.
- Motor copper loss [Est; flag for the motor and power researchers]: P = 1.5 × I_amp² × R_phase. At 0.5 A and 5 Ω per phase that is about 1.9 W per motor, and 12 motors holding 0.5 A would take about 22 W, the whole power bank. At 0.3 A it is about 0.7 W per motor and 8 W in total. The leg-holding current budget, not driver heat, sets the thermal design.
- Boards mounted on the back of each motor share the motor's heat. Keep MT6701 and MCU temperatures within rating (not checked), and give the body vents near the hips.

### Gaps
- No measured temperature rise for DRV8316 boards at about 0.5 A in an enclosure was found. Measure on the bench.
- STM32G431 run current and DRV8316 quiescent current were not confirmed from datasheets.

## Recommendation: how to drive 12 motors in the space available

### Takeaway
**Recommended: 12 single-axis open boards at the hips.** Use SimpleFOC-microspora v1.7 or a trimmed derivative: STM32G431 + DRV8316 + MT6701 + CAN, 33 × 34 mm, 5–35 V, MIT, about $20 each. Each board sits on the back of its motor. Link them over **two CAN-FD buses** (left and right legs, 6 nodes each) from the ESP32-S3, through MCP2518FD controllers. Use firmware with a moteus/ODRI-style impedance command (position, velocity, Kp, Kd, feed-forward current) and a command timeout. Add a hardware enable line plus one eFuse on the 9 V motor rail.

**A strong second choice for later:** 6 two-axis leg boards (STM32G474 + 2 × DRV8316, ODRI-style SPI or CAN-FD). It is more compact and draws less idle power, but needs custom dual-motor firmware.

**Not recommended at 9 V:**
- moteus, ODrive and Tinymovr: 10–12 V minimum, $69–89 each, and ODrive's firmware is closed.
- B-G431B-ESC1: 3S minimum, and its sensing is scaled for 40 A.
- TMC6300/STSPIN233: 10–11 V maximum.
- Central SimpleFOC Minis: too many wires, and SimpleFOC supports low-side sensing for one motor per MCU.

### Cited Findings
- microspora brings MCU, driver, current sensing, MT6701 and CAN together in 33 × 34 mm with M2/M3 slots 22–28 mm apart, MIT, about $20 at JLCPCB, also from Makerfabs. — [SimpleFOC-microspora](https://github.com/simplefoc/SimpleFOC-microspora) [D]
- SimpleFOC low-side sensing is documented as one motor per STM32. — [SimpleFOC mcus/index.md](https://raw.githubusercontent.com/simplefoc/simplefoc.github.io/master/docs/simplefoc_library/hardware/mcus/index.md) [D]
- ESP32 MCPWM supports 4 × 3PWM drivers at most. — [SimpleFOC microcontrollers](https://docs.simplefoc.com/microcontrollers) [S]
- The ESP32-S3 TWAI is classic CAN only. — [esp32.com](https://esp32.com/viewtopic.php?p=130806) [S]
- 10 V minimums: moteus. — [moteus README](https://github.com/mjbots/moteus) [D]
- 10–30 V: ODrive Micro. — [ODrive Micro](https://shop.odriverobotics.com/products/odrive-micro) [S]
- 12–38 V: Tinymovr M5. — [robots.ros.org](https://robots.ros.org/tinymovr/) [S]
- The ODRI system proves 12 joints on 6 dual boards, with SPI to an ESP32 at 1 kHz and a timeout-to-zero-current. — [ODRI micro driver](https://github.com/open-dynamic-robot-initiative/open_robot_actuator_hardware/blob/master/electronics/micro_driver_electronics/README.md), [µDriver SPI](https://raw.githubusercontent.com/open-dynamic-robot-initiative/master-board/master/documentation/BLMC_%C2%B5Driver_SPI_interface.md) [D]

### Inferences
**Space** [Est]
- The deck is 140 × 80 mm (11,200 mm²), and twelve microspora boards are about 13,500 mm². They cannot lie flat in the body; they must sit on the motors at the hips. That suits the onboard MT6701, which reads a magnet on the motor shaft. Each hip then needs only power (2 wires) plus CAN (2 wires) daisy-chained, instead of 3 phase plus 4–6 encoder wires per motor running to the body.
- Twelve SimpleFOC Mini v2.3 driver-only boards (24 × 25 mm) fit, but need about 7 signals each (3 PWM, EN, 3 sense) to a few central MCUs: about 84 lines.

**Why 12 single-axis nodes first**
- The boards exist today and are open (MIT).
- They run on stock SimpleFOC (one motor per MCU is exactly what is supported), at 15–16 kHz current loops on a G431 per the forum.
- A builder can order them from JLCPCB or Makerfabs.
- A failed node is a $20 swap.
- The costs: 12 MCUs to flash, about 1–2 W of idle draw, and a bus that needs CAN-FD (two MCP2518FDs on the main board).

**Changes worth making to a Pebble derivative of microspora**
- Confirm or fit a CAN-FD transceiver.
- Bring the DRV8316 enable pin out to the hardware enable line from the safety circuit, and an nFAULT output to a shared fault line.
- Raise the DRV8316 sense gain to 0.375 V/A for the 1.5 A range.
- Drop the USB-C and buttons if space is tight.
- Keep the 22–28 mm slot pattern to match the motor backs.

**Firmware command**
- Copy ODRI's frame shape: position, velocity, feed-forward current, Kp, Kd and current limit per joint, a CRC, an index, and a timeout of a few tens of milliseconds.
- On timeout, go to brake/hold (moteus modes 10/15) rather than limp.

**Two-axis per-leg boards** (6 × STM32G474 + 2 × DRV8316 or DRV8311)
- Fewer nodes (6), so one CAN-FD bus or SPI suffices.
- Half the MCU idle power.
- Both motors of a leg are at the same hip, so wires stay short.
- The catch: no stock open firmware does 2 low-side current loops per MCU. This needs bench proof first.

**Bus voltage**
- If the owner can choose a 12 V PD profile, the field widens only a little: moteus-c1 at 10 V minimum still has no margin under sag. The DRV8316 path stays the best fit at 9 V.

### Gaps
- No vendor-confirmed board masses, retail prices (Makerfabs) or NZD prices for the recommended boards.
- No bench data on DRV8316 + STM32G431 FOC with 5–15 Ω gimbal motors at 9 V: current-loop noise at 0.3–1.5 A, or how much the crosstalk reported on Mini v2.1 affects torque.
- Not verified because the search budget ran out: STSPIN32G4 boards, DengFOC, newer 2025–2026 AliExpress "mini FOC + MT6701 + CAN" boards, and RP2350 multi-motor FOC.
