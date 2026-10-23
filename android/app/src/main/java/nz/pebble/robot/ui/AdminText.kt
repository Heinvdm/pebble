package nz.pebble.robot.ui

import nz.pebble.robot.PebbleConfig
import nz.pebble.robot.llm.LlamaPlan
import nz.pebble.robot.llm.ModelFiles
import org.json.JSONObject
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

object AdminText {
    const val LOW_STORAGE = 2L shl 30
    private val DAY = DateTimeFormatter.ofPattern("d MMMM yyyy", Locale.ENGLISH)

    fun brain(status: JSONObject?, now: Long): String {
        val brain = status?.optJSONObject("brain") ?: return "Pebble's brain: the keeper has not reported yet."
        if (now - status.optLong("at") > FaceNote.STALE_MS) return "Pebble's brain: the keeper has not reported for ${(now - status.optLong("at")) / 1000} s; restart the phone if this stays."
        val restarts = brain.optInt("restarts")
        val again = if (restarts > 0) " Started ${restarts + 1} times since the phone started (pauses and setting changes count too)." else ""
        return when {
            brain.optString("want") == "pause" -> "Pebble's brain: paused by you. \"Start Pebble's brain again\" wakes it."
            brain.optString("want") == "hold" -> "Pebble's brain: stopped for a moment while a setting is changed."
            status.optBoolean("resting") -> "Pebble's brain: resting until the phone is charging (the battery ran low)."
            brain.optBoolean("alive") -> {
                val beat = brain.optLong("heartbeat_at")
                "Pebble's brain: running" + (if (beat > 0) ", last sign of life ${maxOf(0L, now - beat) / 1000} s ago." else ", starting up.") + again
            }
            else -> "Pebble's brain: not running: ${brain.optString("why").ifEmpty { "it has not started yet" }}.$again"
        }
    }

    fun model(label: String, m: JSONObject?, file: String, settings: Int = 0): String {
        if (m == null) return "$label: not known yet."
        val name = m.optString("model").takeIf { it.isNotEmpty() && it != "null" } ?: file
        val problem = m.optString("problem")
        return "$label: " + when (m.optString("state")) {
            "ready" -> {
                val context = m.optInt("context")
                val setting = m.optInt("setting", -1)
                "ready, $name" + (if (context > 0) ", a window of ${String.format(Locale.ROOT, "%,d", context)} tokens" else "") + (if (setting >= 0) ", memory setting ${setting + 1}" + (if (settings > 0) " of $settings" else "") else "") + "."
            }
            "busy" -> "$name is not answering for a moment; it is restarted if that lasts 2 minutes."
            "loading" -> "loading $name" + (if (!m.isNull("loading_s")) " (${m.optLong("loading_s")} s so far; a big model takes about a minute)" else "") + "." + (if (problem.isNotEmpty()) " Last time: $problem." else "")
            "waiting", "failed" -> (if (problem.isNotEmpty()) "$problem." else "stopped.") + (if (!m.isNull("retry_in_s")) " Next try in ${m.optLong("retry_in_s")} s." else "")
            "missing" -> "$problem."
            else -> when {
                problem.isEmpty() -> "off."
                m.optString("kind") == ModelFiles.MISSING || m.optString("kind") == ModelFiles.COPYING -> "${problem.replaceFirstChar { it.uppercase() }}."
                else -> "not started: $problem."
            }
        }
    }

    fun bench(b: JSONObject?): String? {
        if (b == null) return null
        if (b.has("measuring")) {
            val minutes = b.optLong("for_s") / 60
            val problem = b.optString("problem").takeIf { it.isNotEmpty() }?.let { " Problem: $it." } ?: ""
            return "  Measuring how fast the main model talks on this phone: step ${b.optInt("step", 1)} of ${b.optInt("steps", 5)}, ${b.optString("what")} (${if (minutes < 1) "under a minute" else "$minutes min"} so far; about 10 to 15 minutes in all, once). Until then Pebble can't hold a conversation.$problem"
        }
        if (b.has("again_in_s")) return "  Measuring how fast it talks did not work; it tries again in about ${(b.optLong("again_in_s") + 59) / 60} min."
        if (!b.has("first_words_ms")) return null
        val drafter = if (b.isNull("drafter")) "none" else b.optString("drafter")
        val slow = if (b.has("meets_targets") && !b.optBoolean("meets_targets")) " That is slower than the aim (first words within 1.5 s, a short answer within 5 s)." else ""
        return "  Measured: first words after about ${secs(b.optDouble("first_words_ms"))} s, a short answer after about ${secs(b.optDouble("answer_ms"))} s; it reads in batches of ${b.optInt("batch")}; the drafter: $drafter.$slow"
    }

    fun ears(state: JSONObject?): String {
        val ears = state?.optJSONObject("ears") ?: return "Ears: not known (the brain is not answering)."
        if (!ears.optBoolean("enabled", true)) return "Ears: switched off (Senses, \"Listen for words\")."
        val st = ears.optJSONObject("state")
        val phone = ears.optJSONObject("phone")
        val engine = phone?.optJSONObject("engine")
        val deaths = engine?.optInt("deaths") ?: 0
        val mode = ears.optString("mode", st?.optString("mode").orEmpty())
        return "Ears: " + when (st?.optString("ears")) {
            "ready" -> when (mode) {
                "words" -> "listening for words, on this phone only."
                "keywords" -> "listening only for its name (quiet hours, or someone asked it to stop listening)."
                else -> "not listening for words (quiet hours, or switched off)."
            }
            "starting", "loading" -> "loading the speech models (a few seconds)."
            "restarting" -> "the speech models stopped and start again ${(engine?.optDouble("restart_in_s") ?: 0.0).let { if (it < 1.0) "in a moment" else "in ${String.format(Locale.ROOT, "%.0f", it)} s" }} (they have stopped $deaths time${if (deaths == 1) "" else "s"}); nothing said meanwhile is lost."
            "resting", "android" -> "Android's own recognizer listens for now" + (phone?.optString("speech_models")?.takeIf { it.isNotEmpty() && it != "in use" }?.let { ", because $it" } ?: "") + "; Pebble tries its own speech models again later."
            "none" -> "this build has no speech models, so Android's own recognizer listens."
            else -> "not known yet."
        }
    }

    fun heat(status: JSONObject?): String {
        val level = status?.optJSONObject("heat")?.optString("level").orEmpty()
        val slow = if (status?.optJSONObject("speed")?.optBoolean("slow") == true) " Answers are coming slower than when it was measured." else ""
        return when (level) {
            "warm" -> "Heat: warm, so Pebble keeps answers short, waits longer between its own thoughts, and its eyes look less often.$slow"
            "hot" -> "Heat: hot, so Pebble answers in one short sentence, puts off its own thinking, and its eyes slow right down until it cools.$slow"
            "cool" -> "Heat: cool.$slow"
            else -> "Heat: not known yet."
        }
    }

    fun linkState(logTail: String): Pair<String, String>? {
        val lines = logTail.lines()
        val start = lines.indexOfLast { "Pebble starting:" in it }
        val since = if (start >= 0) lines.subList(start, lines.size) else lines
        for (line in since.asReversed()) {
            when {
                "link up: " in line -> return "up" to line.substringAfter("link up: ").trim()
                "link down: " in line -> return "down" to line.substringAfter("link down: ").trim()
                "link unavailable: " in line -> return "unavailable" to line.substringAfter("link unavailable: ").trim()
                "no link to the body yet" in line -> return "waiting" to ""
            }
        }
        return if (start >= 0) "starting" to "" else null
    }

    fun link(config: PebbleConfig, noted: JSONObject?, logTail: String, usb: JSONObject?, brainAlive: Boolean): String {
        if (config.link == PebbleConfig.LINK_SIM) return "Link to the body: the simulated body (no robot)."
        val where = when {
            config.link == PebbleConfig.LINK_USB -> "the USB cable"
            config.host != PebbleConfig.AUTO -> "${config.host}:${config.port}"
            noted?.optString("found")?.takeIf { it.isNotEmpty() && it != "null" } != null -> "${noted.optString("found")}:${config.port}, found on the Wi-Fi"
            else -> null
        }
        val usbProblem = usb?.takeIf { !it.optBoolean("open") }?.optString("problem")?.takeIf { it.isNotEmpty() }
        if (!brainAlive) return "Link to the body: not connected while Pebble's brain is not running."
        val (state, detail) = linkState(logTail) ?: ("starting" to "")
        if (state == "down" && detail.startsWith("handshake failed")) return "Link to the body: refused: ${detail.substringAfter(": ")}. Pebble tries again every few seconds; if the keys differ, pair the body over the USB cable."
        return "Link to the body: " + when (state) {
            "up" -> "connected" + (where?.let { " ($it)" } ?: "") + "."
            "unavailable" -> "can't be opened: $detail."
            else -> {
                val lost = if (state == "down") "lost; Pebble keeps trying to connect again" else "not connected yet; Pebble keeps trying"
                val hint = when {
                    config.link == PebbleConfig.LINK_USB -> usbProblem?.let { " The USB cable: $it." } ?: " Check the ESP32 is plugged into the phone and switched on."
                    where == null -> " Pebble could not find the ESP32 on the Wi-Fi by itself: check the robot is switched on and on the same Wi-Fi, or type its address above."
                    else -> " Check the robot is switched on and that $where is its address."
                }
                "$lost.$hint"
            }
        }
    }

    fun seal(answer: String, zone: ZoneId = ZoneId.systemDefault()): String = try {
        val o = JSONObject(answer)
        val s = o.optJSONObject("status")
        when {
            s == null -> o.optString("message").ifEmpty { "The seal could not be read." }
            !s.optBoolean("sealed") -> "Not sealed yet. Seal it after \"Setup finished\" (SETUP.md, step 13)."
            else -> {
                val day = try {
                    OffsetDateTime.parse(s.optString("sealed_at")).atZoneSameInstant(zone).format(DAY)
                } catch (e: Exception) {
                    s.optString("sealed_at")
                }
                val device = when (s.optString("device")) {
                    "opens" -> "Pebble's own key in this phone opens it, so it starts by itself."
                    "does not open" -> "Pebble's key in this phone does not open it: recover it below with two cards or the password."
                    "damaged" -> "Pebble's key in this phone is damaged: recover it below with two cards or the password."
                    "unavailable" -> "this phone's keystore can't be reached right now."
                    else -> "Pebble's key in this phone: ${s.optString("device")}."
                }
                val password = if (s.optBoolean("owner_lock")) "The owner's password opens it too." else "It has no owner's password any more (it was thrown away)."
                "Sealed on $day. $device $password Recovery cards: set ${s.optString("set_id")}."
            }
        }
    } catch (e: Exception) {
        "The seal could not be read."
    }

    fun storage(free: Long): String =
        "Storage: ${LlamaPlan.gb(free)} free" + if (free < LOW_STORAGE) ", which is low: Pebble needs room for its memories, its logs and any new model file." else "."

    fun eyes(state: JSONObject?): String? {
        val eyes = state?.optJSONObject("eyes") ?: return null
        if (!eyes.optBoolean("on") && eyes.optString("camera").let { it.isEmpty() || it == "null" || it == "none" }) {
            return "Eyes: no camera open" + (eyes.optString("problem").takeIf { it.isNotEmpty() }?.let { " ($it)" } ?: "") + "."
        }
        val fps = String.format(Locale.ROOT, "%.1f", eyes.optDouble("fps", 0.0))
        val backends = eyes.optJSONObject("phone")?.optJSONObject("backends")?.let { b -> b.keys().asSequence().sorted().joinToString(", ") { "$it ${b.optString(it)}" } }
        val problem = eyes.optString("problem").takeIf { it.isNotEmpty() }?.let { " Problem: $it." } ?: ""
        return "Eyes: ${eyes.optString("camera")} camera, $fps pictures a second" + (backends?.let { "; fastest ways: $it" } ?: "") + ".$problem"
    }

    fun bodyKey(key: JSONObject?): String {
        if (key == null) return "Body key: not known yet."
        val state = if (key.optBoolean("paired")) "paired" + (key.optString("level").takeIf { it.isNotEmpty() && it != "null" }?.let { ", kept in $it" } ?: "") else "not paired: Pebble will not drive the body until it is paired over the USB cable (Link to the body, below)"
        val said = key.optJSONObject("said")?.optString("message")?.takeIf { it.isNotEmpty() }?.let { " Last pairing: $it" } ?: ""
        return "Body key: $state.$said"
    }

    fun refusedModels(models: JSONObject?): String? {
        if (models == null) return null
        val parts = mutableListOf<String>()
        models.optString("checking").takeIf { it.isNotEmpty() }?.let { parts += "checking $it against Pebble's list" }
        val refused = models.optJSONArray("refused")
        if (refused != null) {
            for (index in 0 until refused.length()) {
                val one = refused.optJSONObject(index) ?: continue
                parts += "refused ${one.optString("name")}: ${one.optString("why")}"
            }
        }
        return if (parts.isEmpty()) null else "Model files: " + parts.joinToString("; ") + "."
    }

    fun lock(lock: JSONObject?, now: Long): String {
        if (lock == null) return "USB debugging: not known yet."
        val until = lock.optLong("adb_until")
        val adb = when {
            lock.optBoolean("debug") -> "allowed, because this is a debug build (never run one on the live robot)"
            until > now -> "allowed for ${maxOf(1L, (until - now) / 60_000)} more minutes"
            lock.optBoolean("adb_open") -> "allowed until the admin PIN is set"
            else -> "off"
        }
        val usb = when (val data = lock.optString("usb_data")) {
            "" -> ""
            "on" -> "; USB data on"
            "off" -> "; USB data off (charging only) while the body is on Wi-Fi"
            else -> "; USB data: $data"
        }
        return "USB debugging: $adb$usb."
    }

    private fun secs(ms: Double): String = if (ms.isNaN()) "?" else String.format(Locale.ROOT, "%.1f", ms / 1000)
}
