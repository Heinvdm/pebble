package nz.pebble.robot.ui

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.text.InputType
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import org.json.JSONArray
import nz.pebble.robot.Atomic
import nz.pebble.robot.Paths
import nz.pebble.robot.PebbleConfig
import nz.pebble.robot.admin.AdminPin
import nz.pebble.robot.admin.Kiosk
import nz.pebble.robot.admin.OwnerFinger
import nz.pebble.robot.eyes.Bench
import nz.pebble.robot.keeper.KeeperService
import nz.pebble.robot.keeper.SelfOps
import nz.pebble.robot.llm.LlamaPlan
import nz.pebble.robot.llm.LlamaServer
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread

class AdminActivity : Activity() {
    private lateinit var paths: Paths
    private lateinit var kiosk: Kiosk
    private lateinit var column: LinearLayout
    private lateinit var status: TextView
    private lateinit var output: TextView
    private val handler = Handler(Looper.getMainLooper())
    private var birthViews: List<View> = emptyList()
    private var setupViews: List<View> = emptyList()
    private var sealViews: List<View> = emptyList()
    private var lastTouch = System.currentTimeMillis()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        paths = Paths(this).ensure()
        requestedOrientation = HomeActivity.orientation(PebbleConfig.load(paths.config))
        kiosk = Kiosk(this)
        column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(12), dp(16), dp(32))
        }
        val scroll = ScrollView(this).apply {
            setBackgroundColor(Color.rgb(16, 20, 28))
            addView(column)
        }
        setContentView(scroll)
        if (intent.getBooleanExtra(EXTRA_SETUP, false) || !AdminPin(paths.pin).isSet()) buildSetup() else buildMain()
        handler.postDelayed(idle, IDLE_CHECK_MS)
    }

    override fun onUserInteraction() {
        super.onUserInteraction()
        lastTouch = System.currentTimeMillis()
    }

    private val idle = object : Runnable {
        override fun run() {
            if (System.currentTimeMillis() - lastTouch >= IDLE_MS) {
                finish()
                return
            }
            handler.postDelayed(this, IDLE_CHECK_MS)
        }
    }

    private fun dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()

    private fun heading(text: String) {
        column.addView(TextView(this).apply {
            this.text = text
            textSize = 20f
            setTextColor(Color.rgb(230, 238, 250))
            setTypeface(typeface, Typeface.BOLD)
            setPadding(0, dp(18), 0, dp(6))
        })
    }

    private fun line(text: String): TextView = TextView(this).apply {
        this.text = text
        textSize = 15f
        setTextColor(Color.rgb(190, 200, 215))
        setPadding(0, dp(2), 0, dp(4))
        column.addView(this)
    }

    private fun field(hint: String, value: String = "", secret: Boolean = false, number: Boolean = false): EditText = EditText(this).apply {
        this.hint = hint
        setText(value)
        setTextColor(Color.WHITE)
        setHintTextColor(Color.GRAY)
        inputType = when {
            secret && number -> InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_VARIATION_PASSWORD
            secret -> InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            number -> InputType.TYPE_CLASS_NUMBER
            else -> InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
        }
        column.addView(this)
    }

    private fun check(label: String, on: Boolean): CheckBox = CheckBox(this).apply {
        text = label
        isChecked = on
        setTextColor(Color.rgb(220, 228, 240))
        column.addView(this)
    }

    private fun button(label: String, action: () -> Unit): Button = Button(this).apply {
        text = label
        isAllCaps = false
        setOnClickListener { action() }
        column.addView(this, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
    }

    private fun radios(options: List<Pair<String, String>>, chosen: String): RadioGroup {
        val group = RadioGroup(this)
        options.forEachIndexed { index, (key, label) ->
            group.addView(RadioButton(this).apply {
                id = View.generateViewId()
                tag = key
                text = label
                setTextColor(Color.rgb(220, 228, 240))
                isChecked = key == chosen
            })
        }
        column.addView(group)
        return group
    }

    private fun picked(group: RadioGroup): String = group.findViewById<RadioButton>(group.checkedRadioButtonId)?.tag as? String ?: ""

    private fun say(text: String) = runOnUiThread { Toast.makeText(this, text, Toast.LENGTH_LONG).show() }

    private fun buildSetup() {
        heading("Welcome to Pebble")
        line("Choose an admin PIN of 6 to 12 digits. It guards this screen and the way out of kiosk mode. It is not the password that seals Pebble's self. If you forget it, the only way back is a full reset of the phone.")
        val first = field("New PIN", secret = true, number = true)
        val second = field("The same PIN again", secret = true, number = true)
        button("Save the PIN") {
            val a = first.text.toString()
            if (a != second.text.toString()) return@button say("The two PINs are different.")
            if (!AdminPin.valid(a)) return@button say("The PIN needs 6 to 12 digits.")
            thread {
                AdminPin(paths.pin).set(a)
                runOnUiThread {
                    say("PIN saved.")
                    finish()
                }
            }
        }
    }

    private fun buildMain() {
        val config = PebbleConfig.load(paths.config)
        heading("Pebble")
        status = line("Reading Pebble's state...")
        status.typeface = Typeface.MONOSPACE
        status.textSize = 12f
        button("Pause Pebble's brain") { KeeperService.start(this, KeeperService.ACTION_PAUSE) }
        button("Start Pebble's brain again") { KeeperService.start(this, KeeperService.ACTION_RESUME) }
        button("Restart the brain and the models") { KeeperService.start(this, KeeperService.ACTION_RELOAD) }

        heading("Link to the body")
        val link = radios(listOf(PebbleConfig.LINK_WIFI to "Wi-Fi to the ESP32", PebbleConfig.LINK_USB to "USB cable to the ESP32 (bench)", PebbleConfig.LINK_SIM to "Simulated body (no robot)"), config.link)
        line("ESP32 address: \"auto\" finds it on the home Wi-Fi by itself; or type its IP address, for example 192.168.1.50.")
        val host = field("auto or 192.168.1.50", config.host)
        val port = field("Port", config.port.toString(), number = true)
        line("The body obeys only a phone that proves a shared key. Pairing gives the body and this phone a new key over the USB cable: plug this phone into the ESP32's USB-C port with the body switched on, then press Pair. Pebble's brain stops for a moment.")
        button("Pair the body over the USB cable") {
            confirm("Pair the body now? The body must be plugged into this phone's USB port and switched on.") {
                KeeperService.start(this, KeeperService.ACTION_PAIR_BODY)
                say("Pairing. The status above says how it went, within about ten seconds.")
            }
        }
        button("Forget the body key") {
            confirm("Forget the body key? Pebble will not drive the body until it is paired again.") { KeeperService.start(this, KeeperService.ACTION_FORGET_BODY_KEY) }
        }

        heading("Mind")
        val mind = radios(listOf("llama" to "Language models on this phone", "scripted" to "Scripted mind (no models; for testing)"), config.mind)
        line("Copy model files into ${paths.modelDrop.path}" + (if (paths.modelDrop.path.startsWith(SHARED)) " (with adb: /sdcard${paths.modelDrop.path.removePrefix(SHARED)})" else "") + ". Pebble checks each file's fingerprint against the list inside this app, moves the ones it knows into its own storage, and refuses the rest. The file names below must match exactly, capitals included.")
        val mainModel = field("Main model file", config.mainModel)
        line("Picture projector for the main model (lets it look at pictures): auto finds an mmproj file next to the models; none switches it off.")
        val projector = field("auto, none or the projector's file name", config.mainProjector)
        line("Drafter for the main model (Gemma 4's own drafter; it writes the answer faster): auto finds a file with mtp in its name next to the models and keeps it only if the phone measures it faster; none switches it off.")
        val drafter = field("auto, none or the drafter's file name", config.mainDrafter)
        val sub = check("Use the small model too", config.sub)
        val subModel = field("Small model file", config.subModel)

        heading("Senses")
        val camera = check("Cameras on", config.camera)
        val listen = check("Listen for words (on this phone only; never in quiet hours)", config.listen)
        val dry = check("Keep the wheels off", config.dryRun)
        val reverse = check("The phone is mounted the other way round", config.reverse)
        val picture = field("Test picture instead of the cameras (blank for the cameras; portrait.jpg, desk.jpg or cat.jpg)", config.testImage)

        button("Save and restart Pebble") {
            val typedHost = host.text.toString().trim().ifEmpty { PebbleConfig.AUTO }
            if (!PebbleConfig.validHost(typedHost)) return@button say("That ESP32 address does not look right.")
            val next = config.copy(
                link = picked(link).ifEmpty { config.link },
                host = typedHost,
                port = port.text.toString().toIntOrNull()?.takeIf { it in 1..65535 } ?: config.port,
                mind = picked(mind).ifEmpty { config.mind },
                mainModel = mainModel.text.toString().trim().ifEmpty { config.mainModel },
                mainProjector = projector.text.toString().trim().ifEmpty { PebbleConfig.AUTO }.let { if (it == PebbleConfig.AUTO || it == PebbleConfig.NONE || nz.pebble.robot.Models.validName(it)) it else config.mainProjector },
                mainDrafter = drafter.text.toString().trim().ifEmpty { PebbleConfig.AUTO }.let { if (it == PebbleConfig.AUTO || it == PebbleConfig.NONE || nz.pebble.robot.Models.validName(it)) it else config.mainDrafter },
                sub = sub.isChecked,
                subModel = subModel.text.toString().trim().ifEmpty { config.subModel },
                camera = camera.isChecked,
                listen = listen.isChecked,
                dryRun = dry.isChecked,
                reverse = reverse.isChecked,
                testImage = picture.text.toString().trim(),
            )
            if (!nz.pebble.robot.Models.validName(next.mainModel) || !nz.pebble.robot.Models.validName(next.subModel)) return@button say("Model files must end in .gguf.")
            PebbleConfig.save(paths.config, next)
            KeeperService.start(this, KeeperService.ACTION_RELOAD)
            say("Saved. Pebble restarts with the new settings.")
            if (next.reverse != config.reverse) recreate()
        }

        heading("Files from the PC")
        line("Opens a small receiver on this phone's Wi-Fi address for 15 minutes, guarded by a code, for one model file, app update or body profile; it closes after the first file. It is plain HTTP, so use it only on Pebble's own Wi-Fi.")
        button("Receive files for 15 minutes") { KeeperService.start(this, KeeperService.ACTION_RECEIVE) { putExtra(KeeperService.EXTRA_MINUTES, 15) } }
        button("Stop receiving") { KeeperService.start(this, KeeperService.ACTION_CLOSE_RECEIVER) }

        buildSetupMode()
        buildSeal()
        buildHouse()

        heading("Map")
        line("The rooms Pebble has mapped, its places, and where it and you have been. It shows while Pebble's brain is running.")
        button("Show Pebble's map") { startActivity(Intent(this, MapActivity::class.java)) }

        heading("Eyes")
        button("Measure the eyes again (picks the fastest way to run each model)") {
            Bench.forget(this)
            nz.pebble.robot.brain.SpeechModels.forgetMeasurements(this)
            KeeperService.start(this, KeeperService.ACTION_MEASURE_AGAIN)
            say("The eyes measure themselves when the brain starts, the speech models get a fresh try, the language models measure how fast they answer (about ten minutes, while the main model is away), and the memory search measures itself once the eyes and ears are running.")
        }

        buildOwner()

        heading("Kiosk and phone")
        button("Leave kiosk mode for 15 minutes") {
            Atomic.write(File(paths.run, HomeActivity.KIOSK_PAUSE), (System.currentTimeMillis() + 15 * 60_000L).toString().toByteArray())
            kiosk.leave(this)
            say("Kiosk mode is off for 15 minutes. Pressing Home comes back to Pebble.")
        }
        button("Back to kiosk mode now") {
            File(paths.run, HomeActivity.KIOSK_PAUSE).delete()
            kiosk.applyPolicies()
            finish()
        }
        button("Open Android settings") {
            if (!kiosk.inLockTask()) startActivity(Intent(Settings.ACTION_SETTINGS)) else say("Leave kiosk mode first.")
        }
        line("USB debugging (adb) stays off once the admin PIN is set. It can be let in for ${Kiosk.ADB_MINUTES} minutes at a time; it switches itself off again after that.")
        button("Allow USB debugging for ${Kiosk.ADB_MINUTES} minutes") {
            confirm("Let a computer plugged into this phone use adb for ${Kiosk.ADB_MINUTES} minutes?") {
                say(if (kiosk.allowAdbFor(Kiosk.ADB_MINUTES)) "USB debugging is allowed for ${Kiosk.ADB_MINUTES} minutes. Turn it on in Developer options too." else "Only possible when Pebble is the device owner.")
            }
        }
        button("Turn USB debugging off now") { say(if (kiosk.blockAdbNow()) "USB debugging is off." else "Only possible when Pebble is the device owner.") }
        button("Restart the phone") { confirm("Restart the phone now?") { kiosk.reboot() } }
        button("Stop being the device owner (before uninstalling)") {
            confirm("Pebble will stop being this phone's device owner: no kiosk, no lock-screen control, no silent updates. Continue?") {
                say(if (kiosk.giveUpOwnership()) "Pebble is no longer the device owner." else "That did not work.")
            }
        }

        heading("Logs")
        output = line("")
        output.typeface = Typeface.MONOSPACE
        output.textSize = 11f
        button("Brain log") { showLog(paths.brainLog) }
        button("Main model log") { showLog(File(paths.logs, "llama-main.log")) }
        button("Small model log") { showLog(File(paths.logs, "llama-sub.log")) }
        button("Admin screen log") { showLog(paths.adminLog) }
        button("Close this screen") { finish() }
        handler.post(refresh)
    }

    private fun buildSetupMode() {
        heading("Setup")
        val state = line("Checking...")
        val about = line("While Pebble is being built and tested it keeps no lasting fears, gathers no trust and makes no personality changes. Press this only when the body is assembled and tested, and before sealing. Pebble then wakes up for real, and today becomes its birthday.")
        val passphrase = field("Owner's spoken passphrase (only if one is set)", secret = true)
        val finish = button("Setup finished") {
            confirm("Is Pebble's body assembled and tested? From now on Pebble remembers everything that happens to it, and this cannot be undone.") {
                AlertDialog.Builder(this)
                    .setMessage(TSUNAMI_QUESTION)
                    .setPositiveButton("Yes") { _, _ -> finishSetup(state, passphrase, "yes") }
                    .setNegativeButton("No") { _, _ -> finishSetup(state, passphrase, "no") }
                    .setNeutralButton("Not now") { _, _ -> finishSetup(state, passphrase, "") }
                    .show()
            }
        }
        val birthAbout = line("Pebble's birth draw: the temperament it starts life with, drawn from its own seed. While Pebble is being set up you can ask for another draw; the one it has when setup ends becomes its own for good. It uses the passphrase above, if one is set.")
        val birthState = line("")
        val birthButton = button("Draw Pebble's temperament again") {
            confirm("Draw Pebble's temperament again? The draw it has now cannot be brought back.") {
                val phrase = passphrase.text.toString()
                passphrase.setText("")
                birthState.text = "Drawing. Pebble's brain stops for a moment..."
                thread {
                    val o = parsed(SelfOps.withBrainHeld(this) { SelfOps.admin(this, BIRTH, "again", paths.self.path, phrase) })
                    val birth = o.optJSONObject("birth")
                    runOnUiThread {
                        birthState.text = (if (o.optBoolean("ok")) "" else "Not drawn: ${o.optString("message")}\n") + BirthText.describe(birth)
                        showBirth(true)
                        if (!BirthText.offered(birth)) birthViews.last().visibility = View.GONE
                    }
                }
            }
        }
        birthViews = listOf(birthAbout, birthState, birthButton)
        setupViews = listOf(about, passphrase, finish)
        showBirth(false)
        thread {
            val o = parsed(SelfOps.python(this, "setup_status", paths.self.path))
            val setup = o.optJSONObject("setup")
            val text = when {
                setup == null -> o.optString("message").ifEmpty { "Pebble's setup state could not be read." }
                setup.optBoolean("on") -> "Pebble is in setup."
                setup.optString("born").isNotEmpty() && setup.optString("born") != "null" -> "Setup is finished; Pebble's birthday is ${setup.optString("born")}."
                else -> "Setup is finished."
            }
            val birth = if (setup?.optBoolean("on") == true) parsed(SelfOps.admin(this, BIRTH, "status", paths.self.path)).optJSONObject("birth") else null
            runOnUiThread {
                state.text = text
                birthState.text = BirthText.describe(birth)
                showBirth(BirthText.offered(birth))
                if (setup != null && !setup.optBoolean("on")) showSetup(false)
            }
        }
    }

    private fun showSetup(on: Boolean) {
        for (view in setupViews) view.visibility = if (on) View.VISIBLE else View.GONE
    }

    private fun showBirth(on: Boolean) {
        for (view in birthViews) view.visibility = if (on) View.VISIBLE else View.GONE
    }

    private fun parsed(answer: String): JSONObject = try {
        JSONObject(answer)
    } catch (e: Exception) {
        JSONObject().put("ok", false).put("message", answer)
    }

    private fun finishSetup(state: TextView, passphrase: EditText, tsunami: String) {
        val phrase = passphrase.text.toString()
        passphrase.setText("")
        thread {
            val o = parsed(SelfOps.admin(this, HOUSE, "finish_setup", paths.self.path, phrase, tsunami))
            val restart = o.optBoolean("tsunami_saved") && SelfOps.brainAlive(this)
            if (restart) KeeperService.start(this, KeeperService.ACTION_RESTART_BRAIN) { putExtra(KeeperService.EXTRA_AFTER_MS, SETUP_SEEN_MS) }
            runOnUiThread {
                state.text = (if (o.optBoolean("ok")) "" else "Not done: ") + o.optString("message") + (if (restart) " Pebble's brain starts again in about a minute to take the tsunami answer." else "")
                if (o.optBoolean("ok")) {
                    showBirth(false)
                    showSetup(false)
                }
            }
        }
    }

    private fun buildHouse() {
        heading("Around the house")
        val state = line("Reading...")
        line("While Pebble runs, the settings are handed to it and it takes them within a few seconds. When it is not running, they go straight into its self.")
        line("Home, for sunrise, sunset and the almanac: a New Zealand town, or a latitude and longitude.")
        val home = field("Wellington, or -41.29, 174.78")
        line("Guest Wi-Fi: Pebble can show it on its screen as a code that phones join with. It never says the password aloud. Never give it the main network.")
        val ssid = field("Guest network name")
        val wifiPassword = field("Guest network password (empty for an open network)", secret = true)
        val security = radios(listOf("WPA" to "WPA or WPA2", "WEP" to "WEP (old)", "nopass" to "Open, no password"), "WPA")
        val forget = check("Forget the guest network", false)
        val kids = check("Tell a child's grown-ups when the child gets home", false)
        val guardians = field("Grown-ups besides the owner, by the names Pebble knows, separated by commas")
        val cooking = check("Cooking watch: mention cooking left with nobody in the kitchen", true)
        line(TSUNAMI_QUESTION)
        val tsunami = radios(listOf("yes" to "Yes, a tsunami zone", "no" to "No"), "")
        val passphrase = field("Owner's spoken passphrase (only if one is set)", secret = true)
        val ownerPassword = field("Owner's password, the one that seals the self (only for a sealed self with a spoken passphrase)", secret = true)
        var loaded: JSONObject? = null
        fun show(house: JSONObject?) {
            loaded = house ?: loaded
            val now = loaded ?: return
            kids.isChecked = now.optBoolean("children_arrivals")
            cooking.isChecked = now.optBoolean("cooking_watch")
            val zone = HouseInput.tsunami(now)
            if (zone.isEmpty()) tsunami.clearCheck() else (0 until tsunami.childCount).map { tsunami.getChildAt(it) as RadioButton }.firstOrNull { it.tag == zone }?.let { tsunami.check(it.id) }
        }
        button("Save the house settings") {
            val before = loaded ?: return@button say("The house settings are still being read.")
            val changes = JSONObject()
            val typed = home.text.toString().trim()
            if (typed.isNotEmpty()) {
                val numbers = HouseInput.latLon(typed)
                if (numbers != null) changes.put("lat", numbers.first).put("lon", numbers.second) else changes.put("town", typed)
            }
            if (forget.isChecked) {
                changes.put("wifi", JSONObject.NULL)
            } else if (ssid.text.toString().isNotBlank()) {
                changes.put("wifi", JSONObject().put("ssid", ssid.text.toString().trim()).put("password", wifiPassword.text.toString()).put("security", picked(security).ifEmpty { "WPA" }))
            }
            val names = HouseInput.names(guardians.text.toString())
            if (kids.isChecked != before.optBoolean("children_arrivals") || names.isNotEmpty()) changes.put("children_arrivals", kids.isChecked).put("guardians", JSONArray(names))
            if (cooking.isChecked != before.optBoolean("cooking_watch")) changes.put("cooking_watch", cooking.isChecked)
            val zone = picked(tsunami)
            if (zone.isNotEmpty() && zone != HouseInput.tsunami(before)) changes.put("tsunami", zone == "yes")
            if (changes.length() == 0) return@button say("Nothing has changed.")
            val phrase = passphrase.text.toString()
            val password = ownerPassword.text.toString()
            passphrase.setText("")
            ownerPassword.setText("")
            wifiPassword.setText("")
            state.text = "Saving..."
            thread {
                val running = SelfOps.brainAlive(this)
                val o = if (running) parsed(SelfOps.admin(this, HOUSE, "post", paths.self.path, phrase, password, changes.toString()))
                else parsed(SelfOps.withBrainHeld(this) { SelfOps.admin(this, HOUSE, "save", paths.self.path, phrase, password, changes.toString()) })
                runOnUiThread {
                    if (o.optBoolean("ok")) {
                        home.setText("")
                        ssid.setText("")
                        guardians.setText("")
                        forget.isChecked = false
                    }
                    if (!running || !o.optBoolean("ok")) show(o.optJSONObject("house"))
                    state.text = (if (o.optBoolean("ok")) "" else "Not saved: ") + o.optString("message") + "\n" + HouseInput.describe(o.optJSONObject("house") ?: loaded)
                }
                if (running && o.optBoolean("ok")) {
                    Thread.sleep(POST_SEEN_MS)
                    val again = parsed(SelfOps.admin(this, HOUSE, "status", paths.self.path))
                    runOnUiThread {
                        show(again.optJSONObject("house"))
                        if (again.optBoolean("ok")) state.text = HouseInput.describe(loaded)
                    }
                }
            }
        }
        thread {
            val o = parsed(SelfOps.admin(this, HOUSE, "status", paths.self.path))
            runOnUiThread {
                show(o.optJSONObject("house"))
                state.text = if (o.optBoolean("ok")) HouseInput.describe(loaded) else o.optString("message")
            }
        }
    }

    private fun buildSeal() {
        heading("Pebble's self")
        val sealState = line("Checking...")
        line("Sealing locks Pebble's self with your password, Pebble's own key in this phone's secure chip, and three recovery cards. Write the cards down; no one can show them again without the password. This screen blocks screenshots.")
        val password = field("Owner's password (at least 12 characters)", secret = true)
        val again = field("The password again (only for sealing)", secret = true)
        val cards = line("")
        cards.typeface = Typeface.MONOSPACE
        cards.textSize = 12f
        val seal = button("Seal Pebble's self") {
            val p = password.text.toString()
            if (p.length < 12) return@button say("The password needs at least 12 characters.")
            if (p != again.text.toString()) return@button say("The two passwords are different.")
            confirm("Pebble stops for a moment while its self is sealed. Continue?") {
                password.setText("")
                again.setText("")
                selfCall(sealState, cards, "seal", paths.self.path, p) { sealed -> showSealing(!sealed) }
            }
        }
        sealViews = listOf(again, seal)
        button("Show the recovery cards again") {
            val p = password.text.toString()
            password.setText("")
            selfCall(sealState, cards, "cards", paths.self.path, p)
        }
        line("A new phone: type two cards (their codes), or use the password.")
        val first = field("First card's code")
        val second = field("Second card's code")
        button("Recover with two cards") {
            val a = first.text.toString()
            val b = second.text.toString()
            first.setText("")
            second.setText("")
            selfCall(sealState, cards, "recover", paths.self.path, a, b)
        }
        button("Recover with the password") {
            val p = password.text.toString()
            password.setText("")
            selfCall(sealState, cards, "recover_with_password", paths.self.path, p)
        }
        val keyFile = field("Key file to move into the keystore", File(paths.external, "self.key").path)
        button("Move Pebble's lock from that key file into the keystore") { selfCall(sealState, cards, "move_lock", paths.self.path, keyFile.text.toString()) }
        thread {
            val text = python("status", paths.self.path)
            runOnUiThread {
                sealState.text = AdminText.seal(text)
                showSealing(!sealedIn(text))
            }
        }
    }

    private fun sealedIn(answer: String): Boolean = try {
        JSONObject(answer).optJSONObject("status")?.optBoolean("sealed") == true
    } catch (e: Exception) {
        false
    }

    private fun showSealing(on: Boolean) {
        for (view in sealViews) view.visibility = if (on) View.VISIBLE else View.GONE
    }

    private fun selfCall(state: TextView, cards: TextView, function: String, vararg args: String, after: (Boolean) -> Unit = {}) {
        state.text = "Pausing Pebble..."
        thread {
            val answer = SelfOps.withBrainStopped(this, function, *args)
            val o = parsed(answer)
            val printed = o.optJSONArray("cards")
            val status = python("status", paths.self.path)
            runOnUiThread {
                state.text = (if (o.optBoolean("ok")) "" else "Not done: ") + o.optString("message") + "\n" + AdminText.seal(status)
                cards.text = if (printed != null) (0 until printed.length()).joinToString("\n\n") { printed.getString(it) } else ""
                after(sealedIn(status))
            }
        }
    }

    private fun python(function: String, vararg args: String): String = SelfOps.python(this, function, *args)

    private fun buildOwner() {
        heading("Owner proof")
        val finger = OwnerFinger(this)
        val possible = finger.possible()
        line(if (possible == null) "A fingerprint can open this screen instead of the PIN. Adding or removing any fingerprint in Android settings switches it off until the PIN turns it on again." else "Fingerprint: not available, because $possible.")
        if (possible == null) {
            val on = check("Fingerprint opens this screen", finger.enabled())
            on.setOnCheckedChangeListener { box, wanted ->
                if (wanted) {
                    OwnerGate.askPin(this, "PIN to switch the fingerprint on") {
                        finger.enable()?.let {
                            say(it)
                            box.isChecked = false
                        }
                    }
                } else {
                    finger.disable()
                }
            }
        }
        val first = field("New PIN", secret = true, number = true)
        val second = field("The same new PIN again", secret = true, number = true)
        button("Change the PIN") {
            val a = first.text.toString()
            if (a != second.text.toString()) return@button say("The two PINs are different.")
            if (!AdminPin.valid(a)) return@button say("The PIN needs 6 to 12 digits.")
            OwnerGate.askPin(this, "The current PIN") {
                thread {
                    AdminPin(paths.pin).set(a)
                    finger.disable()
                    say("PIN changed. Switch the fingerprint on again if you use it.")
                }
            }
        }
    }

    private fun confirm(question: String, yes: () -> Unit) {
        AlertDialog.Builder(this).setMessage(question).setPositiveButton("Yes") { _, _ -> yes() }.setNegativeButton("No", null).show()
    }

    private fun showLog(file: File) {
        thread {
            val text = try {
                file.readLines().takeLast(80).joinToString("\n")
            } catch (e: Exception) {
                "No log yet (${file.name})."
            }
            runOnUiThread { output.text = text }
        }
    }

    private val refresh = object : Runnable {
        override fun run() {
            thread {
                val text = describe()
                runOnUiThread { status.text = text }
            }
            handler.postDelayed(this, 3_000)
        }
    }

    private fun describe(): String {
        val out = StringBuilder()
        val now = System.currentTimeMillis()
        val config = PebbleConfig.load(paths.config)
        val s = try {
            JSONObject(File(paths.run, "status.json").readText())
        } catch (e: Exception) {
            null
        }
        val state = try {
            val c = URL("http://127.0.0.1:${PebbleConfig.SCREEN_PORT}/state").openConnection() as HttpURLConnection
            c.connectTimeout = 800
            c.readTimeout = 1500
            JSONObject(c.inputStream.bufferedReader().readText()).also { c.disconnect() }
        } catch (e: Exception) {
            null
        }
        out.append(AdminText.brain(s, now)).append('\n')
        val models = s?.optJSONObject("models")
        if (config.usesModels()) {
            out.append(AdminText.model("Main model", models?.optJSONObject("main"), config.mainModel, LlamaPlan.MAIN_RUNGS.size)).append('\n')
            AdminText.bench(models?.optJSONObject("main")?.optJSONObject("bench"))?.let { out.append(it).append('\n') }
            out.append(AdminText.model("Small model", models?.optJSONObject("sub"), config.subModel, LlamaPlan.SUB_RUNGS.size)).append('\n')
        } else {
            out.append("Language models: off, because the scripted mind is chosen under Mind.\n")
        }
        out.append("Memory search: ").append(nz.pebble.robot.recall.RecallChoice.describe(nz.pebble.robot.recall.RecallChoice(nz.pebble.robot.recall.SentenceModel.choiceFile(this)).raw())).append(".\n")
        if (state != null) {
            out.append(AdminText.ears(state)).append('\n')
            AdminText.eyes(state)?.let { out.append(it).append('\n') }
        } else if (s?.optJSONObject("brain")?.optBoolean("alive") == true) {
            out.append("Ears and eyes: the face page is not answering yet.\n")
        }
        out.append(AdminText.link(config, readJson(File(paths.run, nz.pebble.robot.brain.BrainService.LINK_FILE)), logTail(paths.brainLog), s?.optJSONObject("usb"), s?.optJSONObject("brain")?.optBoolean("alive") == true)).append('\n')
        out.append(AdminText.heat(s)).append('\n')
        val receiver = s?.optJSONObject("receiver")
        if (receiver?.optBoolean("open") == true) {
            val address = receiver.optJSONArray("addresses")?.optString(0) ?: "<this phone>"
            val code = receiver.optString("code")
            out.append("Receiving one file, code ").append(code).append(", plain HTTP on this phone's Wi-Fi address. On the PC:\n")
            out.append("  curl -T ").append(config.mainModel).append(" -H \"x-pebble-code: ").append(code).append("\" \"http://").append(address).append(":8899/models/").append(config.mainModel).append("\"\n")
            out.append("  curl -T app-release.apk -H \"x-pebble-code: ").append(code).append("\" \"http://").append(address).append(":8899/update\"\n")
        } else if (receiver?.optString("problem")?.isNotEmpty() == true) {
            out.append("File receiver: ").append(receiver.optString("problem")).append(".\n")
        }
        out.append(AdminText.bodyKey(s?.optJSONObject("body_key"))).append('\n')
        AdminText.refusedModels(s?.optJSONObject("models_in"))?.let { out.append(it).append('\n') }
        out.append(AdminText.lock(s?.optJSONObject("lock"), System.currentTimeMillis())).append('\n')
        out.append("Charging: ").append(if (s?.optBoolean("charging") == true) "yes" else "no").append('\n')
        val (total, available) = LlamaServer.memory(this)
        out.append("Memory: ").append(LlamaPlan.gb(available)).append(" free of ").append(LlamaPlan.gb(total)).append('\n')
        out.append(AdminText.storage(LlamaServer.freeSpace(paths.models))).append('\n')
        val files = paths.models.listFiles { f -> f.name.endsWith(".gguf") && !f.name.startsWith(".") }?.sortedBy { it.name }.orEmpty()
        out.append("Model files here: ").append(if (files.isEmpty()) "none yet" else files.joinToString(", ") { "${it.name} (${LlamaPlan.gb(it.length())}, ${String.format(java.util.Locale.ROOT, "%,d", it.length())} bytes)" }).append('\n')
        out.append("Device owner: ").append(if (kiosk.isOwner) "yes" else "no (see SETUP.md, step 6)").append(", kiosk ").append(if (kiosk.inLockTask()) "on" else "off")
        return out.toString()
    }

    private fun readJson(file: File): JSONObject? = try {
        if (file.exists()) JSONObject(file.readText()) else null
    } catch (e: Exception) {
        null
    }

    private fun logTail(file: File): String = try {
        java.io.RandomAccessFile(file, "r").use { f ->
            val from = maxOf(0L, f.length() - LOG_TAIL)
            val bytes = ByteArray((f.length() - from).toInt())
            f.seek(from)
            f.readFully(bytes)
            String(bytes, Charsets.UTF_8)
        }
    } catch (e: Exception) {
        ""
    }

    override fun onDestroy() {
        handler.removeCallbacksAndMessages(null)
        super.onDestroy()
    }

    companion object {
        const val EXTRA_SETUP = "setup"
        const val HOUSE = "pebble_admin.house"
        const val POST_SEEN_MS = 6_000L
        const val BIRTH = "pebble_admin.birth"
        const val SETUP_SEEN_MS = 45_000L
        const val LOG_TAIL = 64L * 1024
        const val IDLE_MS = 2 * 60_000L
        const val IDLE_CHECK_MS = 5_000L
        const val SHARED = "/storage/emulated/0"
        const val TSUNAMI_QUESTION = "Is this house in a tsunami zone, near the coast? If you say yes, after a long or strong earthquake Pebble repeats Civil Defence's advice: long or strong, get gone."
    }
}
