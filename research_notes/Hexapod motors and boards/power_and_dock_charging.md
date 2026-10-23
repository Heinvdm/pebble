# Power system and dock charging for the 12-motor mini hexapod (Xiaomi UltraThin Magnetic Power Bank 5000)

Research date: 17 October 2026. Method note: WebFetch could not resolve any host in this session (DNS errors on mi.com, gsmarena.com, chargerlab.com, ti.com, mightygadget.com), and the shared web-search budget ran out partway through. So every finding below comes from search-result summaries of the pages cited, not from reading full pages. Datasheet numbers that need a full table (pin ratings, regulator quiescent currents, most prices) could not be checked and are listed under Gaps. Repo files are cited by absolute path where they record earlier Pebble decisions.

## 1. The Xiaomi UltraThin Magnetic Power Bank 5000: model, specs and real behaviour

### Takeaway
The owner's bank is the Xiaomi UltraThin Magnetic Power Bank 5000 15W, model **MDY-20-EB**, sold in China as the "金沙江" (Jinshajiang) silicon-carbon magnetic ultra-thin bank. Its single USB-C port is **bidirectional at 5 V 3 A / 9 V 2.5 A (22.5 W) both ways**. It recharges fully in about **2 h 12 min**. It does charge and discharge at once, but only as **USB-C in plus wireless out**, with self-charge cut to about **5 W**. With one USB-C port, it **cannot be charged while that same port powers the motors**. I found no model "P05ZM". A newer **27 W wired / 20 W wireless** version went on sale in China on 16 October 2026.

### Cited Findings
**Identity and official specs (Xiaomi, official):**
- Official name "Xiaomi UltraThin Magnetic Power Bank 5000 15W", model MDY-20-EB. Lithium-ion cell, 4,900 mAh rated / 5,000 mAh typical, about 18.95 Wh typical. Rated battery energy 18.58 Wh (3.79 V, 4,900 mAh). Rated capacity 3,000 mAh at 5 V 2 A. Size 98.5 × 71.5 × 6 mm, mass 98 g — [Xiaomi Global spec page](https://www.mi.com/global/product/xiaomi-ultrathin-magnetic-power-bank-5000-15w/specs/); same page for AU: [Xiaomi AU spec page](https://www.mi.com/au/product/xiaomi-ultrathin-magnetic-power-bank-5000-15w/specs/)
- USB-C output 5 V⎓3 A / 9 V⎓2.5 A, 22.5 W max. Wireless output 15 W max (7.5 W for iPhone). USB-C plus wireless together: 5 V⎓1.5 A 7.5 W max plus 5 W max wireless. Protections include over-voltage, over-temperature, short circuit and dual-NTC temperature control — [Xiaomi Global spec page](https://www.mi.com/global/product/xiaomi-ultrathin-magnetic-power-bank-5000-15w/specs/) (as summarised by search)
- Xiaomi explains that rated capacity (3,000 mAh at 5 V) is lower than cell energy because of boost-conversion losses — [Xiaomi/Redmi Power Bank FAQ KA-300034](https://www.mi.com/global/support/faq/details/KA-300034/)
- Model MDY-20-EB confirmed in the India launch coverage — [TechStories India](https://techstoriesindia.com/xiaomi-ultra-thin-magnetic-power-bank-5000-mdy-20-eb-price-specs-amazon/). Europe launch reported 28 February 2026 — [Gizmochina](https://www.gizmochina.com/2026/02/28/xiaomi-ultrathin-magnetic-power-bank-5000-15w-launched-globally/)

**Teardown and lab measurements (ChongDianTou / 充电头网; teardown and review findings, not official):**
- Model MDY-20-EB, about 6 mm thick, about 98 g, silicon-carbon anode cell, one-piece aluminium shell, 18.95 Wh (5,000 mAh, 3.79 V) — [充电头网 teardown MDY-20-EB](https://www.chongdiantou.com/archives/1760059044364.html); [Zhihu teardown "整机薄至6mm"](https://zhuanlan.zhihu.com/p/1960304332017743735) (glass-fibre face panel, stainless-steel bottom cover, wireless coil on a flex to the PCBA)
- Measured thickness 5.87 mm — [充电头网 review "5.87mm超薄+15W无线快充"](https://www.chongdiantou.com/archives/1773106578355.html); [Zhihu review](https://zhuanlan.zhihu.com/p/2014652965462495532)
- Cell maker: ATL high-energy-density cell — [NetEase/163 teardown summary](https://m.163.com/dy/article/KBJ928FF0511AJLQ.html)
- **Chips: all Nuvolta (伏达).** NU1520 protocol chip (32-bit MCU at 36 MHz, 128 KB flash, 8 KB SRAM, PD3.1 and many fast-charge protocols). NU6803 power-management chip (battery charge and discharge, buck-boost). NU1671 wireless-charging power stage — [充电头网 "采用伏达全套芯片方案"](https://www.chongdiantou.com/archives/1760320760897.html)
- **USB-C input is rated 5 V 3 A / 9 V 2.5 A, 22.5 W max, so 9 V input is supported.** The measured PDOs were the two fixed levels 5 V 3 A and 9 V 2.5 A, with no PPS listed. Protocol test: QC2.0, PD3.0, DCP, Samsung 2 A, Apple 2.4 A — [充电头网 teardown](https://www.chongdiantou.com/archives/1760059044364.html) (via search summary)
- **Self-charge time:** fully charged in about 2 h 12 min; 20 % at 16 min and 80 % at 51 min. Input power climbs in steps to a peak of about 21.3 W, then tapers — [充电头网 review](https://www.chongdiantou.com/archives/1773106578355.html)
- **Pass-through (边充边放):** while charging and discharging at once, the bank's self-charge power was 5.15 W and the wireless pad worked normally — [充电头网 review](https://www.chongdiantou.com/archives/1773106578355.html)
- Launch price in China ¥299 — [Sina Tech, 11 Oct 2025](https://finance.sina.com.cn/tech/roll/2025-10-11/doc-inftnynp0431634.shtml)

**Reviews (independent):**
- The single USB-C port works as input and output. A double press of the status button turns on low-current charging (for earbuds and similar) — [GSMArena review](https://www.gsmarena.com/xiaomi_ultrathin_magnetic_power_bank_5000_15w_review-news-74788.php)
- Xiaomi's general power-bank FAQ: double press the battery button (while not charging) to enter low-current mode; one press exits; each session lasts 2 hours, then ends by itself. (This FAQ covers other models; for MDY-20-EB the session length is not confirmed) — [Xiaomi FAQ KA-300034](https://www.mi.com/global/support/faq/details/KA-300034/)
- Wireless output on a non-Xiaomi phone (Pixel 11 Pro) never went above 5 W. The bank died after 3 hours, with the Pixel at 55 %. iPhone gets 7.5 W; full 15 W is for Xiaomi 17-series phones — [GSMArena review](https://www.gsmarena.com/xiaomi_ultrathin_magnetic_power_bank_5000_15w_review-news-74788.php); [GSMArena test](https://www.gsmarena.com/testing_thexiaomi_ultrathin_magnetic_power_bank_5000_15w-news-71695.php)
- Wired test: a Pixel 11 Pro went to 23 % in 15 min and 61 % at about 51 min, when the bank ran out — [GSMArena test](https://www.gsmarena.com/testing_thexiaomi_ultrathin_magnetic_power_bank_5000_15w-news-71695.php)
- Two tests measured about 3,600–3,650 mAh usable (the summary doesn't say at what voltage) — [Pokde review](https://pokde.net/review/xiaomi-ultrathin-magnetic-power-bank-5000mah-review); [PCQuest review](https://www.pcquest.com/reviews/xiaomi-ultrathin-magnetic-power-bank-5000-review-12590245)
- Full recharge "1.5 to a little over 2 hours" depending on adapter and cable — [91mobiles review](https://www.91mobiles.com/reviews/xiaomi-ultrathin-magnetic-power-bank-5000mah-review/)

**Pass-through on a sibling model:** Xiaomi says its Magnetic Power Bank 6000mAh can charge a phone wirelessly while it is itself being charged. Different model, but the same pattern of USB-C in with wireless out — [Xiaomi Magnetic Power Bank 6000mAh page](https://www.mi.com/global/product/xiaomi-magnetic-power-bank-6000mah/)

**Older, different Xiaomi 5000 mAh magnetic bank (do not confuse):** WPB0507S, 8.7 mm thick, 20 W input, 22.5 W output, 15 W wireless — [ChargerLAB teardown WPB0507S](https://www.chargerlab.com/teardown-of-xiaomi-22-5w-5000mah-magnetic-wireless-power-bank-wpb0507s/). The wired-only PB0520MI uses a SouthChip SC8934 buck charger — [ChargerLAB PB0520MI](https://www.chargerlab.com/teardown-of-xiaomi-5000mah-ultra-thin-power-bank-pb0520mi/)

**Newer variants (2026):**
- "小米金沙江充电宝超薄磁吸5000 27W", on sale 16 October 2026 at ¥299. Input 5 V 3 A / 9 V 2.5 A, wired output up to 27 W, wireless up to 20 W. No teardown yet — [Sina Tech, 16 Oct 2026](https://finance.sina.com.cn/tech/discovery/2026-10-16/doc-inivmiif7672528.shtml); [MyDrivers](https://news.mydrivers.com/1/1158/1158113.htm)
- An orange colour of the 6 mm 5000 was reported for 2026 — [Tencent News, 23 Feb 2026](https://view.inews.qq.com/a/20260223A01NJ100)
- A 10,000 mAh 45 W ultra-thin magnetic "Jinshajiang" bank, 13.2 mm thick, with self-charge input raised to 30 W — [充电头网 teardown](https://www.chongdiantou.com/archives/1780283325609.html); [Sina, 2 Jun 2026](https://finance.sina.com.cn/tech/roll/2026-06-02/doc-inhzzcpr1648022.shtml); [Memeburn](https://memeburn.com/xiaomi-magnetic-power-bank/)

**Prices (seller listings):**
- PB Tech NZ: Glacier Silver NZ$99.00 inc GST (NZ$86.09 + GST); Black on special NZ$79.19 inc GST (NZ$68.86 + GST, limit 3), traveller tax-free NZ$72.99. The cached pages show a 10 August shipping date, so these are about August 2026 — [PB Tech BAPMIX74833](https://www.pbtech.co.nz/product/BAPMIX74833/Xiaomi-5000mAh-225W-1-Output-Ultra-Thin-Magnetic-W); [PB Tech BAPMIX74497](https://www.pbtech.co.nz/product/BAPMIX74497/Xiaomi-5000mAh-225W-1-Output-Ultra-Thin-Magnetic-W)
- Auckland Airport duty-free (via PB Tech) lists Glacier Silver at NZ$73.00. The summary's traveller price (NZ$91.26) reads oddly — [The Mall Auckland Airport](https://themall.aucklandairport.co.nz/en/intl-duty-free/product/pb-tech-m_BAPMIX74497/xiaomi-5000mah-22.5w-1-port-ultrathin-magnetic-power-bank-glacier-silver.html)
- China: ¥299 for both the first version and the 27 W version — [Sina](https://finance.sina.com.cn/tech/roll/2025-10-11/doc-inftnynp0431634.shtml); [Sina 27 W](https://finance.sina.com.cn/tech/discovery/2026-10-16/doc-inivmiif7672528.shtml)

**Earlier Pebble notes:** the plan records the auto-off problem ("the bank switches itself off when almost nothing is drawn"), and the idea of waking it by "replugging it electronically, with a switch on the USB-C line" — plans/new-bodies.md (section 7, "Still to solve"). The original spec warned that power banks often switch off at low load and may not pass power through — reference/spec_snapshot_2026-10-15.txt (line 463)

### Inferences
- **Direction:** with one USB-C port rated both ways, the bank is almost certainly a Type-C dual-role (DRP) port run by the NU1520. It charges when the other end shows Rp (a charger) and gives power when the other end shows Rd (a sink). So the body sets the direction by what it presents on CC. This follows from the Type-C spec; the bank's own docs don't say so.
- **No pass-through on the motor path:** the bank's only "charge while giving power" mode is USB-C in plus wireless out. So charging it on the dock means taking its USB-C port away from the motor bus, and the body needs another supply while docked.
- **Don't use the wireless face:** using it cuts USB-C to 7.5 W at 5 V, and the motors need 9 V. With the face down in the belly, keep metal parts and coils away from it. A Qi ping into steel or a magnet could cause trouble, though I found no source on this bank's foreign-object handling.
- **Usable energy:** 3,000 mAh at 5 V means about 15 Wh at the port. At 9 V, boost losses are likely a little higher, so the plan's 14 Wh is a fair figure. Walking at 5–10 W gives about 1.4–2.8 h; running at 17.5 W about 48 min.
- **Recharge from flat on a 22.5 W+ PD charger:** about 51 min to 80 % and 2 h 12 min to 100 %, measured.
- **The 27 W version** probably adds a 9 V 3 A output, which would give the bus 0.5 A more headroom. Its PDOs are unconfirmed, so check before buying. Same price in China.
- **Auto-off is not documented.** Low-current mode needs a physical button press and lasts about 2 h (going by the FAQ for other models), so it can't be relied on. Better options: let the bank sleep at rest, keep the logic alive another way (section 4), and wake the bank by detaching and re-attaching CC (switch the sink's Rd off and on).

### Gaps
- No "P05ZM" model number was found anywhere. The official model is MDY-20-EB.
- I found no figure for the auto-off current threshold or delay for MDY-20-EB. It must be measured on the real bank: step a resistive load down from 300 mA to 10 mA and time the shut-off at 5 V and at 9 V.
- Not confirmed: whether the bank renegotiates 9 V cleanly after an electronic CC replug, and whether it trips (latches off) or current-limits when asked for more than 2.5 A at 9 V. Test both. The design below assumes it trips.
- I found no evidence that it accepts wireless input. Xiaomi lists wireless output only, which suggests transmit-only, but this is not confirmed.
- No USD price was found. I found no US retail listing; the bank seems to be sold mainly in Europe, Asia and NZ/AU.
- The "3,600–3,650 mAh usable" test figures have no stated voltage basis.

## 2. Getting 9 V from the bank: PD sink chips, and dual-role controllers that can turn the port round

### Takeaway
Any fixed-9 V PD sink chip works, because the bank offers a plain 9 V 2.5 A fixed PDO. The best fit for an ESP32 body is the **WCH CH224Q** (DFN-10, 2 × 2 mm, I²C, can read the source's PDO list), with **HUSB238** and **AP33772S** as I²C alternatives and **CH224K/IP2721** as resistor-set ones. Turning the bank's port round on the dock does **not** need a dual-role PD controller in the body if the dock carries raw USB-C lines (section 3). A dual-role controller (TI TPS65987D/TPS25750 class, Infineon CCG, or FUSB302 plus an MCU) is only needed if the body itself must *source* PD power, for the phone (section 4) or to charge the bank from a single dock input.

### Cited Findings
- **CH224Q / CH224A (WCH):** a PD3.2 sink, up to EPR 140 W, 4–30 V input. The voltage is set by one resistor, by I/O pins, or by I²C (400 kHz, 7-bit address 0x22 or 0x23). CH224Q comes in DFN-10 (2 × 2 mm), CH224A in ESSOP-10. In I²C mode it can read the full list of PDOs offered by the source — [WCH CH224A/Q datasheet V2.0 (done.land mirror)](https://done.land/assets/files/ch224aq_datasheet.pdf); [LCSC CH224Q C46061833](https://www.lcsc.com/product-detail/C46061833.html); [LCSC CH224A C42459160](https://www.lcsc.com/product-detail/C42459160.html)
- One guide lists 6.8 kΩ from CFG1 to GND as 9 V in resistor mode. An Arduino library maps I²C code 1 to 9 V, and warns that 5 V logic can damage the CH224A — [FGV_CH224X library](https://github.com/felixardyansyah/FGV_CH224X); [done.land CH224 family page](https://done.land/components/power/powersupplies/usb/usbtriggers/ch224/)
- An open-source CH224A trigger board (schematic and Gerbers) requests fixed 5/9/12/15/20 V. Licence not stated in the summary — [CH224A_MODULE_FGV](https://github.com/felixardyansyah/CH224A_MODULE_FGV)
- **HUSB238 (Hynetek):** a standalone PD3.0 / Type-C 1.4 sink up to 100 W. It reads the source capabilities after attach, and its I²C allows "advanced PDO request" — [Hynetek HUSB238 datasheet](https://www.hynetek.com/uploadfiles/site/219/news/aabbbbdb-48c9-4a44-a6dc-2c15f53282e6.pdf); [SparkFun copy](https://cdn.sparkfun.com/assets/9/1/7/a/4/USB_PD_Sink_HUSB238.pdf)
- **AP33772S (Diodes):** a PD3.1 EPR sink with AVS up to 28 V and PPS up to 21 V. The host MCU sets voltage and current over I²C — [Diodes AP33772S](https://www.diodes.com/part/view/AP33772S). A community note says the current steps are coarse (250 mA) — [Ueberspannung/AP33772 on GitHub](https://github.com/Ueberspannung/AP33772)
- **STUSB4500 (ST):** an "auto-run" Type-C and PD sink controller that matches its own PDO list against the source's — [ST STUSB4500 datasheet](https://www.st.com/resource/en/datasheet/stusb4500.pdf)
- **TCPC route:** onsemi FUSB307B is a Type-C port controller that needs an MCU-side PD stack — [onsemi FUSB307B datasheet](https://www.onsemi.com/pdf/datasheet/fusb307b-d.pdf)
- **Dual-role accessory precedent:** a TI E2E thread describes a TPS65987D accessory that stays USB device (UFP) while the phone or tablet is host, with dual-role power and Fast Role Swap (about 100 ms to swap power from source to sink) — [TI E2E TPS65987D](https://e2e.ti.com/support/interface-group/interface/f/interface-forum/954114/tps65987d-usb-accessory-power-role-reversal-with-in-data-ufp-mode)
- **Role mechanics:** PR_Swap swaps which side gives power and keeps the data roles. DR_Swap swaps the data roles and keeps the power direction — [Embedded.com, USB Type-C and PD 101](https://www.embedded.com/usb-type-c-and-power-delivery-101-power-delivery-protocol/). By default the Type-C source is also the data host — [Infineon community](https://community.infineon.com/t5/EZ-PD-USB-Type-C/USB-C-Android-Tablet-Charging-in-Host-mode/td-p/223569)

### Inferences
- **Recommended sink:** CH224Q in I²C mode, on the ESP32's I²C bus. It asks for 9 V, reads the bank's PDO list (so the firmware can check it got "9 V 2.5 A", or 9 V 3 A on the 27 W version), and is the smallest part (2 × 2 mm). Its PG/status output plus the bus ADC give "contract OK". It does **not** measure current, so add a current-sense amplifier or eFuse current monitor (section 6) for the firmware's 2.5 A budget.
- **HUSB238** is a good second choice. AP33772S is overkill (no PPS or EPR is needed, since the bank has fixed PDOs only).
- **Electronic replug:** the body can force a fresh attach, which wakes the bank, by briefly opening the sink's CC (or its Rd) with a small MOSFET or analog switch. CH224Q may also allow a re-request over I²C. Not confirmed.
- **Fixed 9 V tolerance:** under USB PD a fixed 9 V can sit anywhere from about 8.55 to 9.45 V (±5 %). Choose motor drivers and supercap ratings for up to 9.45 V. This is spec knowledge, not sourced in this session.
- A dual-role PD controller to turn the bank's port round adds firmware and BOM risk. The raw-USB-C dock in section 3 avoids it: the dock's own off-the-shelf charger talks PD straight to the bank.

### Gaps
- The search budget ran out before checking these. From background knowledge, unverified, check datasheets: CH224K is ESSOP-10 and resistor or pin set to 5/9/12/15/20 V; IP2721 (Injoinic) is TSSOP-16 and pin-select only; HUSB238 comes in DFN-10 and SOT33-6L; STUSB4500 is QFN-24 4 × 4 mm with NVM for 3 PDOs; trigger boards cost about US$1–3 on AliExpress with about 1–2 g mass. **No prices or board masses were confirmed this session.**
- Not researched for lack of budget: TI TPS25750/TPS25751 (DRP controllers that pair with BQ2579x chargers), Infineon CYPD3177 (sink-only) and CCG3PA/CCG6, Injoinic IP2368/IP2366 (bidirectional 2–6S PD chargers). Packages, current ratings and prices are unconfirmed.
- Whether CH224Q reports the *negotiated* current (the RDO) as well as the source PDOs: the datasheet summary only mentions reading PDOs.

## 3. Charging architectures compared: dock through the body, a separate battery, or wireless

### Takeaway
The simplest dock is a **"USB-C on pogo pins" dock**. A standard multi-port USB-C PD charger sits in the dock, and its VBUS, CC and GND lines run to sprung contacts. In the body, a normally-open switch hands the bank's USB-C port from the motor bus over to those contacts while docked, so the bank charges at its full 22.5 W (2 h 12 min) with no custom PD firmware. While docked the motors are off (Pebble rests on its belly), and the logic runs from another source (section 4). A body-mounted 2S pack with a buck-boost charger is cleaner electrically (native pass-through, no auto-off, burst current without supercaps), but means designing a custom Li-ion power system, which a finished, certified bank avoids. Wireless charging of the bank doesn't appear to be possible.

### Cited Findings
- The bank's USB-C input accepts 9 V 2.5 A (22.5 W max) and charges from flat in about 2 h 12 min. Pass-through exists only as USB-C in plus wireless out, with self-charge at about 5.15 W — [充电头网 teardown](https://www.chongdiantou.com/archives/1760059044364.html); [充电头网 review](https://www.chongdiantou.com/archives/1773106578355.html)
- Xiaomi's spec lists wireless as output only (15 W max) — [Xiaomi Global spec page](https://www.mi.com/global/product/xiaomi-ultrathin-magnetic-power-bank-5000-15w/specs/)
- Pebble's current wheeled dock: three horizontal brass strips on the robot (GND, DETECT, 5 V, each 30 × 4 mm), sprung pins on the dock, two 10 × 3 mm magnets, and an AprilTag for the last metre. The dock ties DETECT to GND, and the body reads it on IO4 with a pull-up (LOW = seated) — interfaces.md (lines 35–37, 64–66, 76, 98–101)
- The original spec chose an 18650 "UPS" board over a power bank, because banks auto-off at low load and may not pass power through — reference/spec_snapshot_2026-10-15.txt (line 463)
- The hexapod rests "all the way down on its belly, with no power to the motors until it moves again" — plans/new-bodies.md (section 7, Decided)

### Inferences
**(a) Dock feeds the bank's USB-C through the body (recommended).**
- Dock: a 2- or 3-port USB-C PD charger (45–65 W total) plus short USB-C breakout cables to sprung pins. Port A goes to the bank. Port P goes to the phone path (section 4). An optional port B could feed a 9 V body bus if Pebble must stand or move while docked.
- Body: a normally-open switch for VBUS_A and CC_A. Back-to-back MOSFETs suit VBUS (bidirectional, 9 V, 2.5–3 A); a small analog switch or relay suits CC. It connects the bank's USB-C either to the body's PD sink (CH224Q, off-dock) or to the dock pads (on-dock), never both. The sink's Rd and VBUS path are cut first, then the dock side closes. The bank then sees an Rp source and charges.
- The dock pins stay dead until Pebble sits on them. A USB-C source keeps VBUS at 0 V until it sees a sink's Rd (about 5.1 kΩ) on CC. A coin or a metal desk shorting CC to GND looks like 0 Ω, not Rd, so the charger stays off. (Type-C cold-socket rule, from spec knowledge, not sourced this session.)
- Pins: VBUS_A, CC_A, VBUS_P, CC_P, GND, GND (6), plus optional DETECT (or use CC attach and a Hall sensor on the dock magnet).
- Why it's simple: no PD firmware, no dual-role controller, and the charger and the bank negotiate between themselves. The body's job is one switch and the timing.
- The costs: motors are off while charging, which suits a robot that rests on its belly. Undocking needs a sequence: open the dock switch, close the sink path, get the 9 V contract, precharge the supercaps, then stand up.
- **Alternative (a2), one dock input:** the body sinks 15–20 V from a single dock port, then a body-side PD *source* controller charges the bank at 9 V. Fewer pins, but it adds a dual-role or source PD controller and a buck converter to the body. Not recommended unless the pin count must drop.

**(b) A separate battery in the body (2S Li-ion plus buck-boost charger), instead of the bank:**
- Pros: native power-path pass-through (it charges while running), no auto-off, no PD negotiation for motor power, no 2.5 A ceiling. A 2S pack gives a 6.0–8.4 V bus, and a pouch cell can deliver 60 W bursts directly, so the supercaps could go. The dock needs only VBUS and GND, plus a PD sink on either side.
- Cons: a custom lithium pack, BMS and charger to design, test and document for anyone who builds one. The bank is a finished product with over-voltage, over-temperature, short-circuit and dual-NTC protection. Energy density is similar: 98 g for 18.95 Wh is about 193 Wh/kg, which matches 18650 cells, and the 6 mm slab packs well flat in the belly.
- The owner's choice is defensible: it trades electrical elegance for a sealed, protected, cheap (NZ$79–99), replaceable, flat energy store. The price is two awkward behaviours, auto-off and the single port, both handled in firmware and with one switch.
- A hybrid (bank plus a tiny 2S buffer pack) adds complexity without removing either awkward behaviour. Not recommended.

**(c) Wireless or magnetic-face charging of the bank:** no evidence the bank accepts wireless input (spec: output only), so this is not viable. The magnetic ring could still help align or hold the bank in the belly.

### Gaps
- Candidate 2S charger ICs (TI BQ25798/BQ25792 1–4S buck-boost; Injoinic IP2368 2–6S bidirectional PD) could not be checked this session. Their packages, ratings and prices are unverified.
- Which switch parts to use for VBUS_A (for example a bidirectional load switch, or back-to-back MOSFETs with a driver) and CC_A (an analog switch rated about 6 V): not researched. The bank's behaviour when its port is moved from a sink to a source within seconds is not tested.
- Whether multi-port chargers briefly cut all ports when a second port attaches (common in shared-power GaN chargers) is not confirmed. It matters for the order of contact on docking.

## 4. Charging the phone (Galaxy Z Flip 7) as well

### Takeaway
The Flip 7 has a 4,300 mAh battery, 25 W wired charging (PPS) and 15 W wireless. **The bank can't usefully charge it**: the bank sits face down in the belly, and non-Xiaomi phones get about 5 W from it anyway. "Charge while USB host" works on some Galaxy devices through PD pass-through hubs, but **Samsung documents nothing**, and reports differ by model. **Recommendation:** first test, on the real Flip 7, a cheap off-the-shelf USB-C OTG adapter with PD pass-through placed between the phone and the ESP32-S3, fed from dock port P. If the phone charges and the ESP32 stays enumerated, build that into the body: it keeps the phone as USB host and the current software. Fallback 1: Android Open Accessory (AOA), where the body is USB host and power source, so default Type-C roles charge the phone with no PD swap. Fallback 2: a Qi coil in the cage backrest, but only if a test shows the Flip keeps wireless-charging while its USB port is in host mode.

### Cited Findings
- **Flip 7:** 4,300 mAh, 25 W wired, 15 W wireless, 4.5 W reverse wireless — [Wikipedia: Galaxy Z Flip 7](https://en.wikipedia.org/wiki/Samsung_Galaxy_Z_Flip_7); [PhoneArena battery test](https://www.phonearena.com/news/galaxy-z-flip-7-battery_id170149); [SamMobile](https://www.sammobile.com/news/samsung-boosts-galaxy-z-flip-7-battery-without-making-the-phone-thicker/). PhoneArena's comparison table says 10 W wireless, which contradicts its own review — [PhoneArena compare](https://www.phonearena.com/phones/compare/Samsung-Galaxy-Z-Flip-7,Samsung-Galaxy-Z-Flip-5/phones/12646,12029)
- The earlier Flip 4 was rated USB PD 25 W with PPS, 15 W without PPS — [Wikipedia: Galaxy Z Flip 4](https://en.wikipedia.org/wiki/Samsung_Galaxy_Z_Flip_4)
- The folded Flip 7 is about 85.5 × 75.2 × 13.7 mm and 188 g, and stands hinge up with the USB-C plug at the bottom — plans/new-bodies.md (section 7)
- **Charge while host, community reports (no official Samsung source):** a Galaxy S21 charged and ran a printer at once through a Y-cable; a Galaxy A01 could not — [octo4a discussion #121](https://github.com/feelfreelinux/octo4a/discussions/121). A Galaxy Tab A 10.5 charged through a PD pass-through hub while using Ethernet and USB host — [XDA thread](https://xdaforums.com/t/usb-c-with-otg-with-charging-portables-as-computers-in-2019-and-on.4009559/). A Galaxy Tab A7 stopped charging when a hub was used, and a Samsung moderator said Samsung has no tested USB-C hub for its smartphones — [Samsung EU community](https://eu.community.samsung.com/t5/tablets/samsung-galaxy-tab-a7-how-to-charge-when-using-usb-devices/td-p/2654881); [Samsung r1 community](https://r1.community.samsung.com/t5/tablets/usb-c-hub/td-p/11546211)
- Hubs sold for the Galaxy Z Flip advertise a PD pass-through port that charges the phone while the other ports work. These are seller claims — [Walmart Flip hub listing](https://www.walmart.com/ip/USB-C-Hub-for-Samsung-Galaxy-Z-Flip5-Flip4-Flip-3-5G-5-in-1-Adapter-TYPE-C-PD-Charger-Port-Splitter-for-Galaxy-Z-Flip5-Flip4-Flip-3-5G/5283680155). One listing says the phone needs a PD charger and won't charge from Quick Charge — [Amazon listing](https://www.amazon.com/clp/B0D8248FB9)
- Whether a host phone can sink power is device- and kernel-specific. A postmarketOS fix for Xiaomi miatoll patched the device tree's power-role so PD charging and USB Ethernet work together — [Okazakee/miatoll-usb-pd-ethernet-fix](https://github.com/Okazakee/miatoll-usb-pd-ethernet-fix). Linux TCPM gained sink Fast Role Swap support — [LKML TCPM FRS patch](https://lkml.iu.edu/hypermail/linux/kernel/2008.3/02168.html)
- **AOA:** in accessory mode the Android device is the USB device, and the accessory is the USB host that powers the bus. The accessory must supply at least 5 V 500 mA charging power. AOAv2 needs Android 4.1+, and support depends on the device's hardware — [Android Open Accessory protocol](https://source.android.com/devices/accessories/protocol)
- **Wireless versus wired:** a user reports that plugging in a cable pauses wireless charging on their phone — [Early Bird Club forum](https://forum.earlybird.club/threads/wireless-charging-or-usb-charging.1338118/). The original Pebble spec says most phones can't charge over USB while powering an OTG device, and suggests a Qi pad instead — reference/spec_snapshot_2026-10-15.txt (line 926). The hexapod plan's build order already lists "measure ... whether it can charge wirelessly while powering its USB port" — plans/new-bodies.md (Build order, step 1)
- The bank's wireless output gave a Pixel 11 Pro no more than 5 W — [GSMArena review](https://www.gsmarena.com/xiaomi_ultrathin_magnetic_power_bank_5000_15w_review-news-74788.php)

### Inferences
- **Option 1, PD pass-through, phone stays host (preferred if the test passes):** the body acts as Source plus UFP on the phone's port. Either it presents Rp and then a DR_Swap makes the phone host, or it presents Rd and then a PR_Swap makes the phone the sink. Commodity "OTG + PD charging" adapters already do this. The cheapest build is to embed one adapter's board, or copy its chip, with its PD-in fed from dock port P and its data port wired to the ESP32-S3. While docked, the adapter also powers its downstream port, so the ESP32 and sensors can run from it with the bank switched to charging. Expect a USB re-enumeration when dock power appears or disappears; the link firmware and body reflexes must allow for it. Without PPS, Samsung probably caps charging near 15 W (going by the Flip 4's rating).
- **Option 2, AOA (fallback):** the ESP32-S3 runs as USB host (its OTG port supports host mode) and the body presents Rp at 5 V 3 A. That is the default Type-C source-is-host case, so no PD swap is needed and the phone charges by default. The cost: the Android app moves from the USB host API to the UsbAccessory API, and the ESP32 firmware needs an AOA host driver. It also reverses the plan's "phone is the USB host" decision, so it needs the owner's approval.
- **Option 3, Qi coil in the cage backrest:** geometry is possible, since the Flip's back faces the backrest leaning 30° and a coil there sits a few mm from the phone. It costs a 5–15 W Qi transmitter on the body (estimated 10–20 g with coil), heat next to the phone, and about 60–70 % efficiency. It only helps if the Flip keeps wireless-charging while acting as USB host and sourcing VBUS, which the evidence above makes doubtful. Test before choosing.
- **Option 4, the bank tops up the phone:** not practical. The wireless faces can't line up (bank flat and face down, phone upright), the output is about 5 W, and every Wh moved to the phone comes off motor time.
- **Logic power at rest:** when the bank auto-offs while Pebble rests, the phone (as USB host) sources VBUS to the ESP32 port. If the ESP32 rail is diode-ORed from the bus and from that VBUS, the body stays awake on the phone's battery (under 1 W) and can wake the bank by a CC replug when it needs to move.

### Gaps
- No official Samsung or Android statement covers charging while in USB host mode, or keeping wireless charging on while OTG is active, for the Flip 7. Both must be tested on the real phone.
- No ready-made ESP-IDF or TinyUSB AOA host driver for the ESP32-S3 turned up. Not searched in depth, for lack of budget.
- The PD controller chips inside Flip-compatible pass-through adapters are not known, so the specific chip to copy is not identified.
- Qi transmitter modules (size, mass, 9 V input, 15 W EPP support) were not researched for lack of budget.
- How much current the Flip 7's OTG VBUS supplies is not known; the plan already lists it to measure.

## 5. Supercapacitors for the hop bursts

### Takeaway
Four **Maxwell BCAP0010 P270 S01/X01** (10 F, 2.7 V, ≤30 mΩ, 10 × 30.5 mm, 3.1–3.2 g) in series make 2.5 F, 10.8 V, about 12.6 g. Between 9 and 7 V they hold about 40 J, far more than a 60 W × 0.1 s hop (6 J). A lighter option, four **Eaton HV1020-2R7505-R** (5 F, 40 mΩ, 2.3 g, 9.2 g total), still covers the hop with the bus above about 7.7 V. Lithium-ion capacitors have too much ESR at this size. Put the caps straight on the 9 V bus *behind* a current-limiting eFuse, so the bank never sees more than about 2.3 A, plus a precharge path at power-on and simple balancing.

### Cited Findings
- **Maxwell 2.7 V 10 F (BCAP0010 P270 S01, ESHSR-0010C0-002R7):** max initial DC-ESR 30 mΩ (typical 20 mΩ), 3.1 g, 10.0 mm diameter × 30.5 mm long — [Maxwell datasheet 3001976 (DigiKey mirror)](https://media.digikey.com/pdf/Data%20Sheets/Nesscap%20URL%20links/BCAP0010_P270_S01.pdf); [Maxwell datasheet](https://maxwell.com/wp-content/uploads/2021/08/2_7_10F_ds_3001976_datasheet.pdf)
- **Maxwell XP 10 F (X01):** 10 × 30.5 mm, 30 mΩ max ESR, 3.2 g — [Maxwell XP datasheet 3001977](https://maxwell.com/wp-content/uploads/2021/08/XP_2_7_10F_ds_3001977_datasheet.pdf); stocked at JLCPCB as C4550729 — [JLCPCB part](https://jlcpcb.com/partdetail/5121822-BCAP0010_P270X01/C4550729)
- **Maxwell T01:** 75 mΩ ESR, about 3.5 g, so avoid it for bursts — [Mouser BCAP0010 P270 T01](https://www.mouser.com/ProductDetail/Maxwell-Technologies/BCAP0010-P270-T01?qs=GQp755mzIP2TfG2h%2ByGJoQ%3D%3D)
- **Eaton HV1020-2R7505-R (5 F, 2.7 V):** ESR 40 mΩ, 2.3 g, leakage 20 µA, −40 to +65 °C, 1,000 h at 65 °C, 3.0 V surge. Size 10.0 × 22.3 mm per the datasheet table, but 10.5 × 21.2 mm per the product page, which conflict — [Eaton product page](https://www.eaton.com/us/en-us/skuPage.HV1020-2R7505-R.html); [Eaton HV datasheet](https://www.eaton.com/content/dam/eaton/products/electronic-components/resources/data-sheet/eaton-hv-supercapacitors-cylindrical-cells-data-sheet.pdf); [DigiKey](https://www.digikey.com/en/products/detail/eaton-electronics-division/HV1020-2R7505-R/3878072). The HV family spans 1–100 F — [Eaton HV datasheet](https://www.eaton.com/content/dam/eaton/products/electronic-components/resources/data-sheet/eaton-hv-supercapacitors-cylindrical-cells-data-sheet.pdf)
- **Lithium-ion capacitors (3.8 V max, 2.2 V min):**
  - Taiyo Yuden LIC1235R3R8406: 40 F, ESR 0.15 Ω — [Taiyo Yuden datasheet (Farnell)](https://www.farnell.com/datasheets/1972296.pdf); [Newark](https://www.newark.com/taiyo-yuden/lic1235r3r8406/lithium-ion-cap-40f-3-8v-20-150mohm/dp/92R5744)
  - Taiyo Yuden LIC1840R3R8107: 100 F, 0.1 Ω, 5 A max discharge — [Newark](https://www.newark.com/taiyo-yuden/lic1840r3r8107/lithium-ion-capacitor-100f-3-8v/dp/92R5745)
  - Vinatech VEL08203R8306G: 30 F, 0.35 Ω, 8 mm diameter — [Newark](https://www.newark.com/vinatech/vel08203r8306g/lithium-ion-capacitor-30f-3-8v/dp/38AJ2228)
  - CAP-XX LY13R8: 10 F, 8 × 14 mm, DC ESR 500 mΩ — [CAP-XX LY13R8 datasheet](https://capcomp.de/files/inhalte/4-manufacturer/CAP-XX/cat7-LICs/datasheets/Standard%20+%20high%20Temperature-HighCap-H+L-Series/LY13R81B025V127R-L_LY13R8-LIC-Datasheet-V1_1.pdf)
  - Eaton HSH0612-3R8805-R: 8 F hybrid, 1.2 Ω at 1 kHz — [DigiKey](https://www.digikey.com/en/products/detail/eaton-electronics-division/HSH0612-3R8805-R/26262345)
  - Licaptech LC0200-380: 200 F, 30 mΩ, far too big — [Licaptech datasheet](https://www.licaptech.com/pdfs/datasheets/lithium-ion/LC0200-380-ASW_Datasheet.pdf)
- **LTC3350 (Analog Devices):** charges and monitors 1–4 series supercaps, with internal active balancing, overvoltage shunts on each cap, and a programmable input current limit that gives the system load priority over charging. 4.5–35 V input, over 10 A charge or backup, AEC-Q100, 38-QFN 5 × 7 mm. Prices: from US$5.15 at 1k (ADI); US$12.54 for one at DigiKey; US$10.90 for one / US$7.76 at 100+ at LCSC (search results, October 2026). Demo board DC1937B — [ADI LTC3350](https://analog.com/en/products/ltc3350); [DigiKey](https://www.digikey.com/en/products/detail/analog-devices-inc/LTC3350IUHF-PBF/5030338); [LCSC C580711](https://www.lcsc.com/product-detail/C580711.html); [Farnell DC1937B](https://pt.farnell.com/analog-devices/dc1937b/demonstration-board-backup-controller/dp/4032722)
- The plan already specifies four 10 F cells (about 15 g) for the 40–60 W push, with firmware keeping the total under 2.5 A — plans/new-bodies.md (section 7, 12 motors)

### Inferences
- **Energy (4 × 10 F, so C = 2.5 F):** E(9→7 V) = ½ × 2.5 × (81 − 49) = 40 J, and E(9→8 V) = 21 J. A 60 W × 0.1 s hop is 6 J, of which the bank supplies about 2 J at 2.3 A × 9 V. Taking all 6 J from the caps drops them to √(81 − 4.8) ≈ 8.73 V. The ESR drop at about 4.6 A from the caps, with 4 × 20–30 mΩ = 80–120 mΩ, adds 0.37–0.55 V. **So the bus dips to about 8.2–8.4 V**, a lot of margin. Ten back-to-back hops at 1 Hz are fine if the bank refills about 4 J per hop at 2.3 A.
- **4 × 5 F Eaton HV1020 (C = 1.25 F, 9.2 g):** 6 J gives 8.45 V, minus about 0.74 V of ESR drop, so about 7.7 V. That's enough if the motor drivers run down to about 7 V, and saves about 3.4 g.
- **Voltage margin:** at 9.45 V (the PD upper limit), each cell averages 2.36 V against 2.7 V rated. Simple resistor balancing is enough at this level: for example 4 × 10 kΩ, about 0.24 mA bleed and about 2 mW. That's ten times the 20 µA leakage, so imbalance stays small. LTC3350-style active balancing isn't needed at this voltage.
- **Peak shaving, recommended:** bank → CH224Q 9 V → **TPS25947 eFuse in active current-limit mode, ILIM about 2.2 A** (±10 % gives at most about 2.42 A, under 2.5 A) → 9 V bus with the supercap stack and motor drivers. During a hop the eFuse holds the bank at its limit while the bus sags, dissipating about (9 − 8.3) V × 2.2 A ≈ 1.5 W for about 0.1–0.3 s. The firmware's 2.5 A budget then becomes a hardware guarantee.
- **Power-on precharge:** charging 2.5 F to 9 V through a linear path always wastes ½CV² ≈ 101 J (51 J for 1.25 F). That is too much for a 2 × 2 mm eFuse even with a slow dV/dt. Options: a 10–15 Ω, 3 W resistor with a bypass MOSFET closed by the ESP32 once the stack is near 9 V (about 25–40 s); or a switching charger (the LTC3350's buck, about US$11 for one). The resistor and bypass is cheaper and lighter.
- **Why the LTC3350 isn't the default:** it is a *backup* controller. System load passes from input to output through its ideal diode, and the caps are tapped only when the input fails. So a hop would still pull more than 2.5 A from the bank unless a current limiter sits upstream. It suits a "bank trips, caps hold up" design, not peak shaving.
- **Lithium-ion capacitors:** 0.15–0.5 Ω per cell, ×3 in series, gives 1–3 V of sag at 5 A. That's worse than EDLCs, and they bring a minimum-voltage (2.2 V) rule. Not recommended here.
- **Reverse-feed:** use an eFuse that blocks reverse current, or an ideal diode, so the charged caps can't back-feed the bank's VBUS when the bank auto-offs or the port is moved to the dock.

### Gaps
- No unit prices were found for BCAP0010 or HV1020 this session.
- Kyocera AVX SCC, KEMET, Vinatech EDLC, Musashi and JM Energy cells were not compared, for lack of budget. A 3.0 V-rated EDLC (some newer Eaton and AVX lines) would give more voltage margin, but this is unconfirmed.
- Whether the TPS25947 blocks reverse current (it may need its sister part with an integrated blocking FET) is unconfirmed. So is its safe operating area for 1.5 W pulses.

## 6. Regulators and protection (9 V → 5 V / 3.3 V, reverse polarity, inrush, motor cut-off)

### Takeaway
The eFuse role is covered by the **TI TPS25947**: 2.7–23 V, 28 mΩ, adjustable 0.5–6 A limit, active limiting or circuit-breaker, dV/dt, 2 × 2 mm QFN. It fits the bank-side current limiter well. For the motor-power cut that the laws need, its 6 A ceiling means splitting the motors across two of them, or using a bigger eFuse. The bucks (5 V for the tilt servo and phone path, 3.3 V for the ESP32-S3 and sensors) couldn't be checked this session; the candidates are listed as unverified.

### Cited Findings
- **TPS25947:** 2.7–23 V (28 V abs max), 28 mΩ, 2 × 2 mm 10-pin QFN. Current limit adjustable 0.5–6 A (±10 % above 1 A). Active current limiting or circuit-breaker, adjustable blanking timer, adjustable output slew (dV/dt). IQ 426 µA typical, 610 µA max. Price not found — [TI TPS25947 (zh-tw)](https://www.ti.com/product/zh-tw/TPS25947); [TI TPS25947 (de)](https://www.ti.com.cn/product/de-de/TPS25947); [Mouser TPS25947 page](https://www.mouser.in/new/texas-instruments/ti-tps25947-efuses/)
- Pebble's laws need all motion to go through permissions, the motion guard and stop handling, and the safety chip cuts the motor drivers on tip-over, a drop edge or a lost heartbeat — CLAUDE.md; plans/new-bodies.md (section 7, Electronics)

### Inferences
- **Two eFuses:** (1) bank → bus, ILIM about 2.2 A, active limiting, reverse blocking. (2) bus → motor drivers, enable pin driven by the safety chip AND the ESP32 (cut on fault, heartbeat loss or rest). Its limit should be set above the burst current (about 6–7 A total at 60 W and 8.5 V). The TPS25947's 6 A ceiling is too low for 60 W bursts at about 8.5 V (about 7 A), so either split the motor supply into two eFuses (three legs each), or use a higher-current eFuse or load switch. Because the caps sit on the bus side, the motor eFuse must carry the full burst.
- **Rest pose power:** with both eFuses off and the bank asleep, standby is the bucks' quiescent current plus the ESP32 in deep sleep, powered from the phone's VBUS (section 4).
- **Reverse polarity:** the USB-C and pogo design is keyed (pins can only meet one way), but the dock pads still need an ideal-diode or eFuse input, so a wrong dock or a metal desk can't push current backwards.

### Gaps
- None of these could be checked this session; all are from background knowledge, unverified, check the datasheets:
  - Pololu D24V10F5 (5 V, about 1 A) and D36V28F5 (5 V, about 3.2 A) step-down modules: sizes about 13–18 mm a side, no-load current about 1 mA or less;
  - TI TPS62933 (3.8–30 V, 3 A, SOT-583, about 12 µA IQ);
  - TI TPS62130 (3–17 V, 3 A, 3 × 3 mm QFN, about 17 µA IQ);
  - TPS2595 (a lower-current eFuse, up to about 4 A).
- No eFuse above 6 A was checked (for example TI TPS25982 or TPS1663, both unverified).

## 7. Dock contacts, dock sensing and the dock's power supply

### Takeaway
The proven Pebble pattern carries over: sprung pins on the dock, flat brass pads on the robot, two magnets and an AprilTag. For the hexapod the natural place is the **belly**, because it settles fully onto its belly at rest, so its own weight (about 8.8 N at 900 g) loads the pins. Dock power: a **2- or 3-port USB-C PD charger, 45–65 W**, whose ports run as raw USB-C lines to the pins. VBUS stays off until the robot's sink is seated, so pins on a metal desk or under a dropped coin are safe. I couldn't check pogo pin current ratings this session.

### Cited Findings
- Pebble's current dock: "Spring pogo pins (3A) on the dock, brass pads on the robot, 2 pairs of 10 × 3mm magnets", about 1.5 mm pogo preload when docked, a 5 V 3 A USB charger feeding the dock — reference/spec_snapshot_2026-10-15.txt (lines 471, 535, 587–604)
- Robot-side pads are three horizontal brass strips 30 × 4 mm (GND z 22, DETECT z 29, 5 V z 36), with the dock pins on the 2.54 mm grid. Dock detect: the dock ties DETECT to GND, and the body reads it on IO4 with an internal pull-up and 1 kΩ in series (LOW = seated) — interfaces.md (lines 36, 64, 76)
- The dock AprilTag (tag36h11 id 0, 48 mm black square) is read out to about 2 m, and yaw is reliable within about 1 m — interfaces.md (line 66)
- The hexapod sits all the way down on its belly at rest, with the motors off — plans/new-bodies.md (section 7, Decided)

### Inferences
- **Layout:** the dock is a low, 1–3 mm tall pad with sprung pins pointing up, inside a shallow locating recess or ramp. Pebble walks over it and sits. The belly carries pads: VBUS_A, CC_A (to the bank), VBUS_P, CC_P (to the phone path), GND × 2, and optionally DETECT. Two magnet pairs pull it into place, and a Hall sensor on a dock magnet gives a second "seated" signal. Belly pads stay electrically dead off-dock (normally-open switches and ideal-diode inputs), so a metal desk shorts nothing. Every pad is recessed or flush, and the GND pads lead, for example by being longer.
- **Current:** VBUS_A carries 9 V × 2.5 A (3 A on the 27 W bank) and VBUS_P 9 V × 2–3 A, so use about 3 A pins with 2 pins per VBUS for margin and lower contact resistance. CC carries micro-amps plus the 300 kHz PD signalling, which pogo contacts handle, as magnetic USB-C cables show.
- **Dock power supply:** bank 22.5 W + phone 15–25 W + body at rest about 1–3 W gives about 40–50 W in all. Use a multi-port GaN USB-C PD charger, 45–65 W, with each C port able to give 9 V ≥ 2.5 A. A single-port 30 W charger only works if the phone isn't charged on the dock.
- **Sensing:** CC attach on either path (the sink sees VBUS), plus DETECT (or Hall), plus the AprilTag pose. The firmware closes the bank-to-dock switch only when all agree.

### Gaps
- Pogo pins were not researched (search budget exhausted): Mill-Max spring-loaded pin series, current ratings, stroke, force, prices; Preci-Dip; magnetic pogo connectors (2-, 4- and 5-pin) and their current ratings; robot-vacuum-style sprung contact plates. From background knowledge, unverified, most single pogo pins are rated about 1–3 A continuous.
- Whether a dropped metal object could ever look like Rd (about 5.1 kΩ) and turn VBUS on: physically unlikely, but not sourced.

## 8. Estimated charge times from the dock

### Takeaway
**Bank:** about 51 min to 80 % and 2 h 12 min to 100 % from flat (measured). **Phone (Flip 7, 4,300 mAh):** about 1.3–2 h at roughly 15 W wired, longer if Pebble is thinking hard while docked. **A typical session** (bank half used) is back to 80 % in about 30–40 min.

### Cited Findings
- Bank self-charge: 16 min to 20 %, 51 min to 80 %, 2 h 12 min to full, peak about 21.3 W — [充电头网 review](https://www.chongdiantou.com/archives/1773106578355.html); "1.5 to a little over 2 hours" — [91mobiles](https://www.91mobiles.com/reviews/xiaomi-ultrathin-magnetic-power-bank-5000mah-review/)
- Flip 7: 4,300 mAh, 25 W wired, 15 W wireless — [Wikipedia](https://en.wikipedia.org/wiki/Samsung_Galaxy_Z_Flip_7). Flip 4: 25 W with PPS, 15 W without — [Wikipedia Flip 4](https://en.wikipedia.org/wiki/Samsung_Galaxy_Z_Flip_4)

### Inferences
- **Phone energy:** about 16–17 Wh, assuming a nominal cell voltage of about 3.85–3.9 V (not sourced). At about 15 W wired with the usual taper, expect roughly 1.3–1.6 h from empty to full. At 25 W PPS, which needs a PPS-capable source, roughly 1.1 h. Through a Qi coil at 15 W nominal (about 10 W into the cell), about 2 h or more. The brain's own load while docked (perhaps 2–4 W, not measured) comes off these rates.
- **Runtime against charge:** about 14 Wh usable gives 1.4–2.8 h walking or about 48 min running, for 2.2 h of charging. A sensible behaviour: go home at 25–30 % and leave at 80 % (about 40 min on the dock).

### Gaps
- No measured Flip 7 charge curve was found. PhoneArena's battery test page exists but its timing figures weren't retrieved — [PhoneArena](https://www.phonearena.com/news/galaxy-z-flip-7-battery_id170149).
- The phone's power draw while running the brain, and the charge rate through a pass-through adapter, need measuring on the real hardware.
