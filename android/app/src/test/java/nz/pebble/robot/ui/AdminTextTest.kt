package nz.pebble.robot.ui

import nz.pebble.robot.PebbleConfig
import nz.pebble.robot.llm.ModelFiles
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.ZoneId

class AdminTextTest {
    private val now = 2_000_000L

    private fun keeper(brain: JSONObject, extra: JSONObject.() -> Unit = {}) = JSONObject().put("at", now).put("brain", brain).put("resting", false).apply(extra)

    @Test
    fun aRunningBrainNeverShowsAStaleReason() {
        val text = AdminText.brain(keeper(JSONObject().put("want", "run").put("alive", true).put("heartbeat_at", now - 3_000).put("restarts", 1).put("why", "the brain is starting")), now)
        assertTrue(text, text.startsWith("Pebble's brain: running, last sign of life 3 s ago"))
        assertFalse(text, text.contains("is starting"))
        assertTrue(AdminText.brain(keeper(JSONObject().put("want", "pause").put("alive", false)), now).contains("paused by you"))
        assertTrue(AdminText.brain(keeper(JSONObject().put("want", "run").put("alive", false).put("why", "waiting 5 s before starting the brain again")), now).contains("not running: waiting 5 s"))
        assertTrue(AdminText.brain(null, now).contains("has not reported"))
    }

    @Test
    fun modelsReadAsPlainStates() {
        assertEquals("Main model: ready, gemma-4-E4B_q4_0-it.gguf, a window of 8,192 tokens, memory setting 2 of 4.", AdminText.model("Main model", JSONObject().put("state", "ready").put("model", "gemma-4-E4B_q4_0-it.gguf").put("context", 8192).put("setting", 1), "x.gguf", 4))
        val loading = AdminText.model("Main model", JSONObject().put("state", "loading").put("model", "g.gguf").put("loading_s", 40).put("problem", ""), "g.gguf")
        assertTrue(loading, loading.contains("loading g.gguf (40 s so far"))
        val waiting = AdminText.model("Small model", JSONObject().put("state", "waiting").put("problem", "llama-server for s.gguf stopped: it ran out of memory while loading; it starts again by itself").put("retry_in_s", 5), "s.gguf")
        assertTrue(waiting, waiting.contains("ran out of memory") && waiting.contains("Next try in 5 s"))
        val missing = AdminText.model("Main model", JSONObject().put("state", "off").put("kind", ModelFiles.MISSING).put("problem", "no file named g.gguf for the main model in /x yet; copy it there (SETUP.md, step 8)"), "g.gguf")
        assertTrue(missing, missing.startsWith("Main model: No file named g.gguf"))
        val big = AdminText.model("Main model", JSONObject().put("state", "off").put("kind", ModelFiles.TOO_BIG).put("problem", "g.gguf needs about 5.7 GB"), "g.gguf")
        assertTrue(big, big.contains("not started: g.gguf needs about 5.7 GB"))
    }

    @Test
    fun theBenchSaysWhatStepItIsOnAndWhatItFound() {
        val running = AdminText.bench(JSONObject().put("measuring", "talking, without the drafter, hot").put("step", 4).put("steps", 5).put("what", "how fast it answers after a few minutes of steady work").put("for_s", 420).put("problem", ""))!!
        assertTrue(running, running.contains("step 4 of 5") && running.contains("7 min so far") && running.contains("can't hold a conversation"))
        val done = AdminText.bench(JSONObject().put("first_words_ms", 1234.0).put("answer_ms", 4321.0).put("batch", 64).put("drafter", "on").put("meets_targets", true))!!
        assertTrue(done, done.contains("1.2 s") && done.contains("4.3 s") && done.contains("batches of 64") && done.contains("drafter: on"))
        assertTrue(AdminText.bench(JSONObject().put("again_in_s", 1700))!!.contains("tries again in about 29 min"))
        assertNull(AdminText.bench(null))
    }

    @Test
    fun earsRestartingAndStandingInAreSaid() {
        fun ears(phase: String, engine: JSONObject = JSONObject(), mode: String = "words", models: String = "in use") = JSONObject().put("ears", JSONObject().put("enabled", true).put("mode", mode).put("state", JSONObject().put("ears", phase).put("mode", mode)).put("phone", JSONObject().put("speech_models", models).put("engine", engine)))
        assertEquals("Ears: listening for words, on this phone only.", AdminText.ears(ears("ready")))
        assertTrue(AdminText.ears(ears("ready", mode = "keywords")).contains("only for its name"))
        val restarting = AdminText.ears(ears("restarting", JSONObject().put("deaths", 2).put("restart_in_s", 4.6)))
        assertTrue(restarting, restarting.contains("start again in 5 s") && restarting.contains("stopped 2 times") && restarting.contains("nothing said meanwhile is lost"))
        val resting = AdminText.ears(ears("android", models = "the speech models ended 5 times in 10 minutes"))
        assertTrue(resting, resting.contains("Android's own recognizer") && resting.contains("ended 5 times"))
        assertTrue(AdminText.ears(null).contains("not known"))
    }

    @Test
    fun heatSaysWhatPebbleDoesAboutIt() {
        assertEquals("Heat: cool.", AdminText.heat(JSONObject().put("heat", JSONObject().put("level", "cool"))))
        assertTrue(AdminText.heat(JSONObject().put("heat", JSONObject().put("level", "warm"))).contains("keeps answers short"))
        val hot = AdminText.heat(JSONObject().put("heat", JSONObject().put("level", "hot")).put("speed", JSONObject().put("slow", true)))
        assertTrue(hot, hot.contains("one short sentence") && hot.contains("slower than when it was measured"))
    }

    @Test
    fun theLinkIsReadFromTheBrainsOwnLog() {
        val log = """
            2026-10-20 13:28:38,003 INFO pebble: Pebble starting: self=x link=tcp:pebble.local:7777
            2026-10-20 13:28:39,000 INFO pebble.link.client: link up: tcp:192.168.1.50:7777
            2026-10-20 13:29:38,003 INFO pebble: Pebble starting: self=x link=tcp:192.168.1.50:7777
            2026-10-20 13:29:41,028 WARNING pebble.life.loop: no link to the body yet; carrying on and retrying in the background
        """.trimIndent()
        assertEquals("waiting" to "", AdminText.linkState(log))
        assertEquals("up" to "tcp:192.168.1.50:7777", AdminText.linkState(log + "\n2026-10-20 13:30:00,000 INFO pebble.link.client: link up: tcp:192.168.1.50:7777"))
        assertEquals("down" to "silent", AdminText.linkState(log + "\nx INFO pebble.link.client: link up: a\ny INFO pebble.link.client: link down: silent"))
        assertNull(AdminText.linkState(""))
        val wifi = PebbleConfig()
        val lost = AdminText.link(wifi, JSONObject().put("found", JSONObject.NULL), log, null, true)
        assertTrue(lost, lost.contains("not connected yet") && lost.contains("could not find the ESP32"))
        val typed = AdminText.link(wifi.copy(host = "192.168.1.50"), null, log + "\nz INFO pebble.link.client: link up: tcp:192.168.1.50:7777", null, true)
        assertEquals("Link to the body: connected (192.168.1.50:7777).", typed)
        val usb = AdminText.link(wifi.copy(link = PebbleConfig.LINK_USB), null, log, JSONObject().put("open", false).put("problem", "no ESP32 is plugged into the phone's USB port"), true)
        assertTrue(usb, usb.contains("no ESP32 is plugged"))
        assertTrue(AdminText.link(wifi.copy(link = PebbleConfig.LINK_SIM), null, "", null, true).contains("simulated body"))
        assertTrue(AdminText.link(wifi, null, log, null, false).contains("while Pebble's brain is not running"))
    }

    @Test
    fun aSealedSelfReadsAsPlainWords() {
        val sealed = JSONObject().put("ok", true).put("status", JSONObject().put("sealed", true).put("sealed_at", "2026-10-15T09:16:02+00:00").put("owner_lock", true).put("device", "opens").put("set_id", "XEARTHAW")).toString()
        assertEquals("Sealed on 15 October 2026. Pebble's own key in this phone opens it, so it starts by itself. The owner's password opens it too. Recovery cards: set XEARTHAW.", AdminText.seal(sealed, ZoneId.of("Pacific/Auckland")))
        val lost = JSONObject().put("ok", true).put("status", JSONObject().put("sealed", true).put("sealed_at", "2026-10-15T09:16:02+00:00").put("owner_lock", false).put("device", "does not open").put("set_id", "A")).toString()
        assertTrue(AdminText.seal(lost).contains("recover it below"))
        assertEquals("Not sealed yet. Seal it after \"Setup finished\" (SETUP.md, step 13).", AdminText.seal(JSONObject().put("ok", true).put("status", JSONObject().put("sealed", false)).toString()))
        assertEquals("The seal could not be read.", AdminText.seal("Traceback (most recent call last)"))
    }

    @Test
    fun lowStorageIsCalledLow() {
        assertTrue(AdminText.storage(1L shl 30).contains("which is low"))
        assertEquals("Storage: 40.0 GB free.", AdminText.storage(40L shl 30))
    }

    @Test
    fun theBodyKeyAndTheLockReadAsPlainWords() {
        assertEquals("Body key: paired, kept in StrongBox.", AdminText.bodyKey(JSONObject().put("paired", true).put("level", "StrongBox")))
        assertTrue(AdminText.bodyKey(JSONObject().put("paired", false)).contains("not paired"))
        assertTrue(AdminText.bodyKey(JSONObject().put("paired", true).put("said", JSONObject().put("message", "Not paired: the body did not answer."))).contains("Last pairing: Not paired"))
        val now = 1_000_000L
        assertEquals("USB debugging: off; USB data off (charging only) while the body is on Wi-Fi.", AdminText.lock(JSONObject().put("adb_until", 0).put("adb_open", false).put("usb_data", "off"), now))
        assertTrue(AdminText.lock(JSONObject().put("adb_until", now + 30 * 60_000L).put("adb_open", true), now).contains("allowed for 30 more minutes"))
        assertTrue(AdminText.lock(JSONObject().put("adb_until", 0).put("adb_open", true).put("usb_data", "this phone does not let an app switch USB data off"), now).contains("does not let an app"))
        assertNull(AdminText.refusedModels(JSONObject().put("checking", "").put("refused", org.json.JSONArray())))
        val refused = AdminText.refusedModels(JSONObject().put("checking", "").put("refused", org.json.JSONArray().put(JSONObject().put("name", "evil.gguf").put("why", "its fingerprint is not on Pebble's list of models"))))
        assertEquals("Model files: refused evil.gguf: its fingerprint is not on Pebble's list of models.", refused)
        val log = "a INFO pebble: Pebble starting: self=x\nb WARNING pebble.link.client: link down: handshake failed with tcp:192.168.1.50:7777: the body did not prove the shared key"
        val said = AdminText.link(PebbleConfig(host = "192.168.1.50"), null, log, null, true)
        assertTrue(said, said.startsWith("Link to the body: refused: the body did not prove the shared key."))
    }
}
