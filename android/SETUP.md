# Setting up a phone as Pebble

From a used phone in your hand to a running Pebble. Written for a Google Pixel 6 Pro (Google Tensor, 12 GB, stock Android menus); any Android 10 or newer phone with about 8 GB of memory or more works the same way, though other makers name their menus differently.

What you need: the phone and its case, a USB-C cable, the PC with this folder, and the home Wi-Fi.

**Read this first.** Pebble takes over the phone completely (it becomes the phone's "device owner"). The phone does nothing else afterwards. The only ways back are the admin screen (behind your PIN) and a full factory reset. A forgotten PIN means a factory reset.

---

## 1. Build the app on the PC

You need Android Studio (or just its command-line tools and a JDK 17+), with the Android SDK platform 35, NDK 28.2 and CMake 3.31 (`sdkmanager --install "ndk;28.2.13676358" "cmake;3.31.6"`). Gradle finds the SDK through `ANDROID_HOME` or a `local.properties` file with `sdk.dir=...` (Android Studio writes it; never commit it).

```
cd android
llama/build.sh                 (Git Bash, macOS or Linux; builds llama-server once, about 5 minutes)
gradlew assembleRelease -Ppebble.abis=arm64-v8a
```

The APK is `app/build/outputs/apk/release/app-release.apk` (about 480 MB, most of it the speech, eye and sound models). `-Ppebble.abis=arm64-v8a` leaves out the PC emulator's x86_64 parts; the Pixel 6 Pro needs only arm64-v8a. Never copy the APK into this project.

The app packs the eye, sound and speech models from `../brain` when it is built, so fetch them first, from the `brain` folder with its Python: `python -m pebble.eyes.fetch` and `python -m pebble.speech.fetch` (the slow-lane, hazard and sound models are made once on a PC; `brain/README.md` says how, and `python -m pebble.hearing.fetch --check` checks the sound model). The first build also downloads the sherpa-onnx library (speech) from its GitHub release into `android/libs/`, and the floor, end-of-turn and memory-search models into `android/models/`, each checked against a pinned SHA-256.

The release build is signed with your own key (next part). When the build finds it, it says nothing about signing. When it does not, it prints `WARNING: no release signing key found ... the release APK is signed with the DEBUG key`: stop there and fix the key first, because a phone that has Pebble installed with one key refuses updates signed with another.

### Your own signing key (do this once, before the first install)

Android only installs an update that is signed with the same key as the app already on the phone, so every Pebble needs one key that stays the same for its whole life. Make it once and keep it, and a copy of it, somewhere safe outside this project. Anyone who has the key and its password can sign apps your Pebble will accept.

1. Make a folder for it in your home folder: `~/.pebble/signing/` (on Windows `%USERPROFILE%\.pebble\signing\`).
2. Make the key with `keytool`, which comes with every JDK (Android Studio's own is in its `jbr/bin` folder):

   ```
   keytool -genkeypair -v -keystore ~/.pebble/signing/pebble-release.jks -alias pebble -keyalg RSA -keysize 4096 -validity 10000
   ```

   It asks for a password and a name; any name will do.
3. Next to it, write `~/.pebble/signing/keystore.properties`:

   ```
   storeFile=pebble-release.jks
   storePassword=the password you chose
   keyAlias=pebble
   keyPassword=the password you chose
   ```

   `storeFile` may be a full path, or a name relative to this file.

The build looks for that file at `~/.pebble/signing/keystore.properties`, or wherever the environment variable `PEBBLE_SIGNING_PROPERTIES` points. Without it, the release APK is signed with Android's debug key and the build prints a warning; that is fine for trying things out, but changing keys later means uninstalling Pebble (which deletes its self; keep your recovery cards). Check which key signed an APK with `apksigner verify --print-certs app-release.apk` (apksigner is in the SDK's `build-tools` folder). Never put the key or its password inside this project.

## 2. Factory reset the phone

1. If the phone still has a Google account on it, remove it first (Settings → Passwords, passkeys and accounts, or Passwords and accounts on older Android, → the account → Remove account), or make sure you know its password: after a reset, a phone that had an account asks for it again ("Factory Reset Protection").
2. Settings → System → Reset options → **Erase all data (factory reset)** → Erase all data.

## 3. The setup wizard

- Language, then **connect to Pebble's own Wi-Fi** (Pebble needs it for the ESP32 and for copying models). Make that network first, on the router: a guest or IoT network used only by Pebble's phone and its body, cut off from your main network, and with nothing coming in from it. The phone is out of support and will not get fixes any more, so it should not share a network with your PCs. One trap: many routers' "client isolation" (or "AP isolation") also stops devices on the guest network from reaching each other, and then the phone cannot reach the body. Leave isolation between devices on Pebble's network off and keep only the wall between it and your main network; if the router cannot do that, give the body the USB cable instead. Put no SIM card in the phone.
- **Skip** the Google account ("Skip", then "Skip" again), and don't copy apps and data from another phone.
- **Do not set a screen lock** (no PIN, pattern, password, fingerprint or face). Choose "Skip" or "None". Two reasons: Android keeps an app's files locked after every restart until the screen lock is entered, so Pebble could not start by itself; and a device owner cannot switch off a secure lock screen.
- Say no to every optional extra (location, diagnostics, the assistant, extra apps).
- Let the phone install the system update it offers now, if any. Later updates install themselves between 2 and 5 am.

## 4. The voice (before Pebble takes over)

Pebble hears with its own speech models, which are inside the app (sherpa-onnx); nothing to download and no account needed, and nothing you say leaves the phone. It speaks with the phone's own text-to-speech. Make sure an offline English voice is there: Settings → Accessibility → **Text-to-speech output** → the cog next to the engine (Speech Services by Google) → Install voice data → the English voice (your variant). Do it now: once Pebble is in kiosk mode, Android blocks those download screens.

## 5. Developer options and USB debugging

1. Settings → About phone → tap **Build number** (at the bottom) 7 times.
2. A Pixel has no Samsung-style Auto Blocker, so nothing else needs switching off here. (On a Samsung phone with One UI 6 or newer, switch off Settings → Security and privacy → Auto Blocker first: it blocks USB debugging and installs from the PC.)
3. Settings → System → Developer options → **USB debugging** on.
4. Plug the phone into the PC and accept the "Allow USB debugging?" question (tick "Always allow").
5. On the PC: `adb devices` must list the phone as `device`.

`adb` is in the Android SDK's `platform-tools` folder (on Windows usually `%LOCALAPPDATA%\Android\Sdk\platform-tools`). In Git Bash put `export MSYS_NO_PATHCONV=1` in front of the session, or paths like `/sdcard/...` get mangled.

## 6. Install Pebble and make it the device owner

```
adb install app-release.apk
adb shell dpm set-device-owner nz.pebble.robot/.admin.PebbleAdmin
```

The answer must be `Success: Device owner set to package nz.pebble.robot/.admin.PebbleAdmin`. If it says:

- "there are already some accounts on the device": remove all accounts (step 2) or reset again.
- "there are already several users": something made a second user or profile, on a Pixel usually a private space (Android 15 and newer), a guest or a work profile. `adb shell pm list users` shows them; remove them (Settings → Security and privacy → Private space → Delete private space; Settings → System → Users), or reset again and do not open those features.

Pebble starts in the background straight away (`adb shell dpm list-owners` shows it as the device owner). That is normal; the phone's own home screen stays up until step 10, so steps 7 and 8 can still use Android's settings. As device owner, Pebble gives itself the camera, microphone and notification permissions, so Android asks for none of them. It uses no Bluetooth: the body is reached over Wi-Fi or the USB cable.

## 7. Keep Android from killing Pebble

Pebble already defends itself: it is the phone's home screen and stays on top in kiosk mode, its brain and its watchdog are foreground services, a watchdog restarts the brain when it dies or stops answering, and the model servers are restarted when they die. Android 12 and newer also kill "phantom" child processes (the two llama-server processes are children of the app) when there are too many of them system-wide or when they use a lot of processor time in the background, and the Pixel's Adaptive Battery holds back apps it thinks are rarely used. Switch those off too:

```
adb shell device_config set_sync_disabled_for_tests persistent
adb shell device_config put activity_manager max_phantom_processes 2147483647
adb shell settings put global settings_enable_monitor_phantom_procs false
adb shell dumpsys deviceidle whitelist +nz.pebble.robot
adb shell cmd appops set nz.pebble.robot RUN_ANY_IN_BACKGROUND allow
adb shell am set-standby-bucket nz.pebble.robot active
```

On the phone:

- Settings → System → Developer options → **Disable child process restrictions** on (Android 14 and newer; the same switch as `settings_enable_monitor_phantom_procs`).
- Settings → Apps → Pebble → App battery usage → **Allow background usage** on, then tap it and choose **Unrestricted**.
- Settings → Apps → Pebble → **Pause app activity if unused** off.
- Settings → Battery → Adaptive preferences (Adaptive Battery on older Android) → **Adaptive Battery** off.

### Look after the battery

Pebble's phone sits on the dock charger most of its life, and a battery kept full and warm ages fast and can swell. Apps can't change the charging settings, so set this once now:

- Settings → Battery → **Charging optimization** → **Limit to 80%**. It came with the December 2024 Pixel update (Android 15 QPR1) for the Pixel 6 and later, so update the phone first if the menu is missing. Choose it rather than **Adaptive Charging** (the other choice there), which only holds the charge back overnight to finish by a morning alarm.
- The limit works only while the phone is on; a phone charging while switched off still fills to 100 %.

## 8. Copy the models onto the phone

The language models are not in the app. You copy them into a drop folder on the phone's storage, `/sdcard/Android/data/nz.pebble.robot/files/models/` (the admin screen calls the same folder `/storage/emulated/0/Android/data/nz.pebble.robot/files/models`). Pebble checks each file's SHA-256 fingerprint against the list inside the app, copies the ones it knows into its own storage, where nothing else on the phone can change them, and deletes them from the drop folder. A file it does not know stays in the drop folder, is never opened, and the admin screen says "refused ... its fingerprint is not on Pebble's list". On the PC they are in `android/models/` (git-ignored):

| File | What it is | Size in bytes |
| --- | --- | --- |
| `gemma-4-E4B_q4_0-it.gguf` | the main model: Google's own 4-bit QAT file of Gemma 4 E4B (from `google/gemma-4-E4B-it-qat-q4_0-gguf`) | 5,154,941,280 |
| `LFM2.5-230M-Q8_0.gguf` | the small model (optional and off by default: on the PC it did worse than no model at every job it had; copy it and tick **Use the small model too** under Mind only to try it) | 246,598,496 |
| `mtp-gemma-4-E4B-it-Q8_0.gguf` | Gemma 4's drafter for the main model (optional) | 98,653,280 |

```
adb shell mkdir -p /sdcard/Android/data/nz.pebble.robot/files/models
adb push gemma-4-E4B_q4_0-it.gguf /sdcard/Android/data/nz.pebble.robot/files/models/
adb push mtp-gemma-4-E4B-it-Q8_0.gguf /sdcard/Android/data/nz.pebble.robot/files/models/
adb shell ls -l /sdcard/Android/data/nz.pebble.robot/files/models
```

The names must match exactly, capitals included, and the files go straight into `models/`, not one folder up. The last line lists what arrived: each size must match the table. The main model takes a few minutes to copy; Pebble waits until a file has stopped growing for 15 seconds, then checks it and moves it in (about a minute for the main model; the phone needs about 6.2 GB free while it does), and its face says "still being copied in and checked" meanwhile. The admin screen's "Model files here" then lists it with the same size, and the drop folder is empty again. If a copy is cut short, push it again.

Only the three files in the table are on the list. A different model, or the picture projector below, needs its SHA-256 and size added to `ModelAllow.KNOWN` in `app/src/main/java/nz/pebble/robot/llm/ModelAllow.kt` and a new build of the app.

The **drafter** makes the main model write its answers faster. It is optional: Pebble finds a file with `mtp`, `assistant` or `draft` in its name by itself (or name it on the admin screen under Mind), measures whether it really is faster on this phone, keeps it only then, and goes on without it if the model server will not start with it.

For pictures (Pebble looking at something and talking about it), the main model needs its **picture projector**, the `mmproj` file published next to the model's GGUF files (F16 is the usual choice). It is not on the list yet: add its fingerprint first (above). Then push it into the same folder; Pebble finds a file with `mmproj` in its name by itself (if there are several, the one whose name matches the model's family), or name it on the admin screen under Mind. Pebble counts it in the memory check. Without one, Pebble works the same but cannot look at pictures with its mind.

Or, without a cable, later from the admin screen: "Receive files for 15 minutes" shows a code and the phone's Wi-Fi address (and the exact `curl` line for the main model), then on the PC:

```
curl -T gemma-4-E4B_q4_0-it.gguf -H "x-pebble-code: 123456" "http://192.168.1.23:8899/models/gemma-4-E4B_q4_0-it.gguf"
```

The receiver listens only on the phone's Wi-Fi address, takes one file and then closes, and checks a model's fingerprint as it arrives (an unknown one is not kept). It is plain HTTP: anyone on the same network could watch the file and the code go past, which is one more reason for Pebble's own network. Send the next file after opening the receiver again.

Pebble checks the free space before it accepts a file (the main model needs about 6.2 GB free: the file and 1 GB to spare), and checks the free memory before it starts a model; when either is short it says so on the admin screen and on its face instead of starting.

## 9. Put the phone in its mount

The phone goes in landscape with its **screen facing forward** and its **camera bar on Pebble's right**; seen from behind, the bar is on the right and its lenses are in the upper half. Seen from the front, the phone's top edge (the one that is on top when you hold it upright) is on your **left**. This is Android's ordinary landscape, which the app uses by default. The other way round, the tilt yoke blocks every rear lens's view of the dock's tag, and a camera bar standing more than 1.5 mm out of the case back hits the yoke. Glue the case plate to the back of the case at its centre (it stays clear of the bar), as `interfaces.md` says. Use a slim case: the mount takes at most 168 × 80 × 12 mm, and the Pixel 6 Pro is 163.9 × 75.9 × 8.9 mm bare.

Another phone whose camera only fits the other way round: tick "The phone is mounted the other way round" on the admin screen.

## 10. First start

```
adb shell am start -n nz.pebble.robot/.ui.HomeActivity
```

(or press the phone's Home button: Pebble is now the home screen.)

1. **Welcome to Pebble**: Pebble asks for an **admin PIN** of 6 to 12 digits, twice, then **Save the PIN**. Write it down somewhere safe. (In landscape the keyboard fills the screen while you type; that is Android's.)
2. Pebble switches on kiosk mode: no status bar, no navigation, no lock screen, the screen stays on while the phone is powered, it starts by itself after a restart.
3. "Pebble is waking up..." then the face. The first start takes about a minute longer: the eyes measure which way of running each model is fastest on this phone and remember it. Pebble's brain also starts once more by itself just after the face first shows, to take the camera and microphone.
4. While Pebble can't talk yet, a grey line at the bottom of the face says why, and goes when it can:
   - "Pebble can't talk yet: its language model isn't on this phone. Copy gemma-4-E4B_q4_0-it.gguf into ...": step 8 is not done, or the file has another name or sits in the wrong folder (the admin screen says which).
   - "... is still being copied": wait for `adb push` to finish.
   - "Pebble's mind is loading": about a minute.
   - "Pebble is getting to know this phone: it is timing how fast it can think (step 1 of 5)": the main model measures how fast it reads, how quickly it stops when someone starts talking, how fast it answers cool and after three minutes of steady work, and how much memory is left. About 10 to 15 minutes, once (again after an update with a higher version code, a new model file, or "Measure the eyes again"). Pebble shows its face meanwhile but can't hold a conversation until it is done. The admin screen shows the results.
   - "... damaged or cut short": copy the file again; "... too big for this phone's memory": the admin screen says how much it needs.
5. A small green square in the top-left corner means a camera is open; the small blue mark beside it means Pebble is listening. Both, and the whole face, move by a pixel or two every couple of minutes, so nothing stays lit in one place long enough to mark the screen.

## 11. The admin screen

Tap the **top-left corner five times** within three seconds, then type the PIN. The screen blocks screenshots, so copy anything you need by hand. From the top:

- **Pebble**: a status block, read again every 3 seconds, one line each for Pebble's brain (running, paused, resting, or why not), the main model and the small model (ready, loading, still being copied, not on the phone, too big, damaged, starting again), the talk bench (which step, or what it measured), memory search, the ears (listening, only for its name, starting again after a crash, or Android's recognizer standing in), the eyes (camera and pictures a second), the link to the body (connected, not connected yet, lost, and what to check), heat (cool, warm or hot, and what Pebble does about it), charging, memory, storage (called low under 2 GB), the model files on the phone with their sizes, and the device owner and kiosk. Then **Pause Pebble's brain**, **Start Pebble's brain again** and **Restart the brain and the models**.
- **Link to the body**: Wi-Fi with the address `auto` finds the ESP32 on the home Wi-Fi by itself (it announces `_pebble._tcp`). If that fails (the status says "could not find the ESP32 on the Wi-Fi by itself"), type the ESP32's IP address (your router lists it; best give it a fixed address there). "USB cable" is for the bench: the ESP32 plugged into the phone's USB-C port; Android asks once whether Pebble may use it (tick "Always"). "Simulated body" runs Pebble without a robot.
- **Mind**: language models or the scripted mind; the main model's file name, the picture projector (`auto`, `none` or a file name), the drafter (`auto`, `none` or a file name), **Use the small model too** and the small model's file name.
- **Senses**: **Cameras on**, **Listen for words**, **Keep the wheels off**, **The phone is mounted the other way round**, and a test picture instead of the cameras (leave it blank).
- **Save and restart Pebble**: saves everything above and restarts the brain and the models.
- **Files from the PC**: **Receive files for 15 minutes** and **Stop receiving** (step 8 and step 15).
- **Setup**: see step 12.
- **Pebble's self**: sealing and the recovery cards, see step 13.
- **Around the house**: the home town (a New Zealand town, or a latitude and longitude such as `-41.29, 174.78`) for sunrise, sunset and the almanac; the guest Wi-Fi Pebble may show on its screen as a code (never the main network; it never says the password aloud); whether a child's grown-ups hear when the child gets home, and which grown-ups besides you; the cooking watch; and whether the house is in a tsunami zone. Fill in only what you want to change, then **Save the house settings** (with the owner's spoken passphrase, if one is set; once the self is sealed, the owner's password instead). While Pebble runs it takes them within a few seconds; the screen shows them again after that.
- **Map**: **Show Pebble's map**: the rooms Pebble has mapped, its places, and where it and you have been. It shows while Pebble's brain is running.
- **Eyes**: **Measure the eyes again** makes the eyes, the floor scan, the speech models, the memory search and the language models find their best settings again at the next start (useful after a phone update, or when Pebble has become slow; the language models' part takes about 10 to 15 minutes).
- **Owner proof**: the fingerprint (off on a phone set up this way, see step 16) and **Change the PIN**.
- **Kiosk and phone**: see steps 14 and 17, and **Restart the phone**.
- **Logs**: the last lines of the **Brain log**, **Main model log**, **Small model log** and **Admin screen log** (where the admin screen notes anything that went wrong inside Pebble's own code), then **Close this screen**.

A different camera field of view, rotation or mirror for another phone: write a small JSON file with only those numbers, for example `{"eyes": {"front": {"fov_h_deg": 78, "rotate": 0, "mirror": false}}, "drive": {"cpm": 21.3}}`, and send it with **Receive files for 15 minutes** and `curl -T body.json -H "x-pebble-code: 123456" "http://<phone>:8899/profile"`. Then restart Pebble from the admin screen. The phone keeps only the cameras' `fov_h_deg` (30 to 150), `rotate` (0, 90, 180 or 270) and `mirror`, and `drive.cpm` (0, or 5 to 60) and `drive.wheel_track_mm` (100 to 250); everything else in the file is left out, and it answers with what it kept. The rest of the profile comes from the app. A `body_android.json` in shared storage is no longer read.

The same profile holds the wheels' `drive.cpm`, the encoder counts for each millimetre the wheels roll: 20.7, worked out for the parts list's N20 motors on 43 mm wheels. Navigation and the map are on only while it is above 0, and a wrong value makes Pebble misjudge every distance by the same amount, so measure it once the body is built. Plug the ESP32 into the PC with a USB cable, open its serial port (`pio device monitor` in `firmware/`), push the robot 1 m along a tape measure, and divide the change in the left and right counts of its `S` lines (the second and third numbers after `S`, see `interfaces.md`) by 1000. (Over Wi-Fi the body now sends its status only to a phone that proved the link key, so `nc` sees nothing.) Send the average to the phone as above, and set it in the body too while it is on the cable: `C cpm 21.3`.

**Pair the body (once, and again after the ESP32 is flashed afresh).** The body obeys only a phone that proves a shared key; until they share one, Pebble cannot drive it, and the link line says "the body has no link key yet; pair it over USB". Switch the body on, plug the phone's USB-C into the ESP32's USB-C port (a data cable; Android asks once whether Pebble may use it: tick Always), then admin screen → Link to the body → **Pair the body over the USB cable** → Yes. The phone makes a new random key inside its keystore, gives the body a copy over the cable, and checks that the body proves it. The status block then says "Body key: paired" and "Last pairing: Paired: ...". Unplug the cable. The key never travels over Wi-Fi or Bluetooth, and the phone never shows it. **Forget the body key** undoes it on the phone.

The body's Wi-Fi name and password, its settings and a reboot are taken only over its USB port (`firmware/README.md`). Bluetooth on the body is off; holding its bumper in for 3 seconds while it stands still opens it for 2 minutes, for a PC on the bench (`interfaces.md`, "The Bluetooth pairing window").

## 12. Setup finished

While Pebble is being built and tested it is in **setup**: it keeps no lasting fears, gathers no trust and makes no changes to its personality, so the bumps, falls and strange noises of the workbench leave no mark. Press this only when the body is assembled and tested, and before sealing:

While Pebble is in setup, the Setup section says "Pebble is in setup." and shows the temperament Pebble would be born with (how it describes itself, its traits and first tastes). **Draw Pebble's temperament again** → Yes gives it another draw, as often as you like (with the owner's spoken passphrase, if one is set); Pebble's brain stops for a moment each time. The draw it has when setup ends becomes its own, and nobody can change it after that.

Then: Admin screen → Setup → **Setup finished** (with the owner's spoken passphrase, if one is set) → "Is Pebble's body assembled and tested?" → **Yes**. From then on Pebble remembers everything that happens to it, and today becomes its birthday. This cannot be undone. Sealing (next step) refuses to run while Pebble is still in setup.

Pebble then asks whether the house is in a tsunami zone, near the coast. **Yes** makes it repeat Civil Defence's advice after a long or strong earthquake: long or strong, get gone. **No** leaves that line off; **Not now** leaves the question open (the line stays off). The section then says "Setup is finished ..." and the button goes; when you answered Yes or No, Pebble's brain restarts about a minute later to take the answer. You can change it any time under Around the house.

## 13. Seal Pebble's self

Admin screen → Pebble's self: type the owner's password twice (at least 12 characters) → **Seal Pebble's self** → "Pebble stops for a moment while its self is sealed. Continue?" → **Yes**. Pebble pauses, seals, and shows **three recovery cards**. Write them down by hand (the screen blocks screenshots), check them, and keep them in different places. Any two open the self on a new phone; one alone tells nothing. The section then reads "Sealed on (today). Pebble's own key in this phone opens it, so it starts by itself. The owner's password opens it too. Recovery cards: set ...", and the second password field and the Seal button go. **Show the recovery cards again** shows the same cards, given the password.

Then restart the phone (Kiosk and phone → **Restart the phone**) and check Pebble comes back by itself with its face and, on the admin screen, "Pebble's brain: running": that proves the sealed self opens with the phone's key after a restart.

From then on, Pebble's own key lives in this phone's secure chip (StrongBox, which on the Pixel 6 Pro is its Titan M2 security chip). A copy of the self taken off the phone opens nowhere else (checked: a copy pulled off the emulator, with its wrapped key file, is refused on the PC).

On a new phone (or after a factory reset): install, then admin screen → Pebble's self → type two card codes → **Recover with two cards** (or the password). A self copied from a PC together with its key file: put the key file at the path shown and press **Move Pebble's lock ... into the keystore**.

## 14. adb is off

Once the admin PIN is set (step 10), Pebble switches USB debugging off by itself, and Android then refuses it altogether, even from Developer options. To use adb again (an update with a cable, the logcat in step 18): admin screen → Kiosk and phone → **Allow USB debugging for 30 minutes**, then turn USB debugging on in Developer options if it is off; Pebble switches it off again after 30 minutes (or at once with **Turn USB debugging off now**). Also switch Developer options off when you are done (Settings → System → Developer options → **Use developer options** off).

Pebble also sets these Android rules on the phone (all lifted by "Stop being the device owner"): no USB file transfer, no SD cards or USB drives, no changing the date and time by hand, no network or factory reset from Settings (the recovery-mode reset in step 17 still works), no Bluetooth, no NFC, no ultra-wideband, no 2G, no new users, private spaces or clones, and no safe mode. While the body is on Wi-Fi and adb is not allowed, it also switches the USB port's data off (charging still works) on phones that let an app do that; the admin screen says "USB data off" or that this phone does not allow it. Choosing "USB cable" for the body, pairing or allowing adb switches it back on.

The admin screen closes itself after 2 minutes without a touch, and "Leave kiosk mode for 15 minutes" ends by itself: after 15 minutes Pebble comes back to the front and locks the phone again, wherever you are in Android's settings.

## 15. Updating Pebble later

Over Wi-Fi (no cable, no adb): admin screen → **Receive files for 15 minutes**, then on the PC:

```
curl -T app-release.apk -H "x-pebble-code: 123456" "http://192.168.1.23:8899/update"
```

Pebble installs it silently (only a device owner may) and starts again by itself about a minute later. Android refuses an APK signed with a different key, and Pebble refuses one whose version code is not higher than the app on the phone, so an older build can never be put back over a newer one.

Build each update with a version code one higher than the last (`gradlew assembleRelease -Ppebble.abis=arm64-v8a -Ppebble.versionCode=2`, then 3, and so on; the first install is 1). An update with the same number is refused. A new version code makes Pebble measure itself again (the eyes, the memory search and the 10 to 15 minute talk bench), because new code can change how fast things run.

With a cable: admin screen → **Allow USB debugging for 30 minutes**, turn USB debugging on in Developer options, `adb install -r app-release.apk`, then **Turn USB debugging off now**.

## 16. The PIN, and why not a fingerprint

Pebble uses the admin PIN only, and there is no screen lock. The fingerprint option is built into the admin screen but stays off; on a Pebble set up this way it says it is not available. Android only keeps fingerprints behind a secure screen lock, and step 3 deliberately has none, so that Pebble starts by itself after every restart and kiosk mode can hide the lock screen. (With a screen lock, the phone would stop at its lock screen after every restart until someone typed the phone's PIN.) Sealing always uses the password and the cards, never a fingerprint.

## 17. Leaving kiosk mode, and taking Pebble off the phone

- Admin screen → **Leave kiosk mode for 15 minutes** → **Open Android settings**. Pressing Home goes back to Pebble.
- To remove Pebble: admin screen → **Stop being the device owner (before uninstalling)** → Yes, then uninstall it in Android's settings (or `adb uninstall nz.pebble.robot`). Uninstalling deletes Pebble's self and its key, and the model files in its folder; only the recovery cards bring the self back.
- Forgot the PIN: factory reset. On the Pixel 6 Pro: power off, then hold **Volume Down and Power** (up to 30 seconds) until Fastboot mode shows. Pick "Recovery mode" with the volume buttons and press Power. At "No command", hold Power and tap Volume Up once, then let go of both. Choose "Wipe data/factory reset" (Volume Down moves, Power picks), then "Factory data reset", then "Reboot system now". Then set up again from step 3 and recover the self with two cards.

## 18. The first hour on the phone

Some things only the real Pixel 6 Pro can tell. Go through these once Pebble runs, and write down what each line says (by hand: the admin screen blocks screenshots). Allow USB debugging for 30 minutes first (step 14). On the PC, keep this running meanwhile; it prints every model start, the talk bench's full results and anything Pebble's own code reports:

```
adb logcat -s PebbleKeeper PebbleLlama PebbleTalkBench PebbleBrain PebbleHome PebbleEarsLink PebbleAdmin
```

1. **Device owner and kiosk.** `adb shell dpm list-owners` names Pebble. The face fills the screen in landscape with no bars, the camera's hole hides nothing that matters, and five taps in the top-left corner bring the PIN. Note the phone's screen resolution setting (Settings → Display → Screen resolution); the face works at both.
2. **The model files.** Admin screen, "Model files here": each size matches step 8's table to the byte.
3. **Memory.** "Memory: ... free of" about 11 GB in all. "Main model: ready, gemma-4-E4B_q4_0-it.gguf, a window of 8,192 tokens, memory setting ... of 4" (setting 2 or 3 is expected on 12 GB, depending on how much memory Android reports and whether a picture projector is there; note which). Note it if the line says too big, waiting for memory, or keeps starting again.
4. **The talk bench**, 10 to 15 minutes after the main model first loads: the line on the face goes, and the admin screen says "Measured: first words after about ... s, a short answer after about ... s; it reads in batches of ...; the drafter: ...". The aim is first words within 1.5 s and a short answer within 5 s. The logcat line starting `talk bench:` has the rest, including `cancel_ms` (how long it takes to stop when someone starts talking; it must be under 2500) and whether the drafter loaded with the projector.
5. **Heat.** Talk with Pebble for 15 minutes on the charger. Watch "Heat:" (cool, warm or hot) and feel the back of the phone; note how long it takes to get warm and whether it comes back to cool.
6. **The eyes.** The green square shows. "Eyes: front camera, ... pictures a second; fastest ways: ..." lists what the Tensor chip chose for each model (NNAPI may hand some to its own accelerators). Walk from one side to the other: the face's eyes should follow you the right way round.
7. **The ears.** "Ears: listening for words, on this phone only." Say "Pebble" from across the room, then talk to it while it is talking: it should hear its name, stop talking for you, and not hear its own voice. Note how far away it still hears you.
8. **Memory search.** "Memory search: the sentence model on core 2: a question about ... ms, a memory about ... ms". A question over 500 ms makes it step down to the stand-in.
9. **The link to the body.** With the ESP32 switched on and on the home Wi-Fi: "Link to the body: connected (..., found on the Wi-Fi)". If it says it could not find the ESP32, type its address under Link to the body. With the USB cable: Android asks once whether Pebble may use it; tick Always.
10. **A restart.** Kiosk and phone → **Restart the phone**. The face is back within about a minute without anyone touching the phone, the admin screen says "Pebble's brain: running", and a sealed self still opens.
11. **Charging.** The battery stops at 80 % on the charger (step 7), and overnight "last sign of life" stays a few seconds old (nothing put Pebble to sleep).
12. **The face.** Tap, stroke and hold the face; Pebble notices each. Set a guest Wi-Fi under Around the house and ask Pebble for it: the code fills the screen and another phone's camera joins the network from it.
13. **Files over Wi-Fi.** **Receive files for 15 minutes** shows a code and the phone's address; send a small file with the `curl` line it shows, then **Stop receiving**.

Later, with a debug build (`gradlew assembleDebug -Ppebble.abis=arm64-v8a`, signed with the debug key, so only on a phone set up again for it) and its adb commands (README, Building and testing): the 4x lens and the torch (`CLOSEUP`, `TORCH`), the microphone probe and 48 kHz (`MICPROBE`, `HIGHBAND`), the echo check (`ECHO`), the name spotter's gain against 30 minutes of television, the end-of-turn model's speed (`HEAR`), the floor scan's speed (`FLOOR`), and the memory search against the PC (`RECALL`). Measure `drive.cpm` on the real body (step 11).
