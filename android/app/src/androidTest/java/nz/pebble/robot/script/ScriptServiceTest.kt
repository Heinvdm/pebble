package nz.pebble.robot.script

import android.os.IBinder
import android.os.Process
import android.os.SystemClock
import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import nz.pebble.robot.brain.Bridge
import nz.pebble.robot.brain.KeyVault
import nz.pebble.robot.debug.ScriptProbeService
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.net.InetSocketAddress
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread

@RunWith(AndroidJUnit4::class)
class ScriptServiceTest {
    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private val links = ArrayList<ScriptLink>()

    private fun link(service: Class<out ScriptService> = ScriptService::class.java): ScriptLink = ScriptLink(context, service).also { links.add(it) }

    @After
    fun closeLinks() {
        links.forEach { it.closeAll() }
    }

    private fun ask(link: ScriptLink, id: String, message: Map<String, Any?>, waitMs: Long = 3_000L): Map<*, *> =
        Json.parse(link.ask(id, Json.write(message), waitMs)) as Map<*, *>

    @Suppress("UNCHECKED_CAST")
    private fun vectors(): List<Map<*, *>> {
        val assets = InstrumentationRegistry.getInstrumentation().context.assets
        val names = assets.list("vectors")!!.filter { it.endsWith(".json") }.sorted()
        assertTrue(names.size >= 10)
        return names.flatMap { name ->
            val text = assets.open("vectors/$name").use { it.readBytes().toString(Charsets.UTF_8) }
            (Json.parse(text) as Map<*, *>)["vectors"] as List<Map<*, *>>
        }
    }

    private fun hung(): Map<String, Any?> = linkedMapOf(
        "format" to 1L,
        "header" to linkedMapOf("ABOUT" to "a test", "USES" to arrayListOf("say"), "UNTIL" to "ongoing"),
        "globals" to arrayListOf<Any?>(),
        "funcs" to linkedMapOf(
            "on_start" to linkedMapOf(
                "l" to 6L,
                "args" to arrayListOf<Any?>(),
                "defaults" to arrayListOf<Any?>(),
                "body" to arrayListOf(
                    linkedMapOf("t" to "assign", "l" to 7L, "to" to linkedMapOf("t" to "name", "n" to "n"), "v" to linkedMapOf("t" to "const", "v" to 0L)),
                    linkedMapOf(
                        "t" to "while", "l" to 8L, "c" to linkedMapOf("t" to "const", "v" to true),
                        "body" to arrayListOf(linkedMapOf("t" to "aug", "l" to 9L, "op" to "+", "to" to linkedMapOf("t" to "name", "n" to "n"), "v" to linkedMapOf("t" to "const", "v" to 1L))),
                    ),
                ),
            ),
        ),
    )

    @Test
    fun everyVectorReplaysOnThePhonesRuntime() {
        val items = vectors()
        val problems = items.flatMap { replayHere(it) }
        Log.i(TAG, "replayed ${items.size} vectors on this phone's runtime, ${problems.size} problems")
        assertEquals(emptyList<String>(), problems)
    }

    @Test
    fun everyVectorReplaysThroughTheIsolatedService() {
        val link = link()
        val id = link.open(64)
        assertTrue(id.isNotEmpty())
        val items = vectors()
        val problems = ArrayList<String>()
        items.forEachIndexed { index, item ->
            val sid = "v$index"
            val loaded = ask(link, id, linkedMapOf("op" to "load", "id" to sid, "program" to item["program"], "limits" to item["limits"]))
            if (loaded["loaded"] != true) problems.add("${item["name"]}: load gave $loaded")
            (item["runs"] as List<*>).forEachIndexed { r, run ->
                run as Map<*, *>
                val left = ArrayList(run["replies"] as List<*>)
                val calls = ArrayList<Any?>()
                var out = ask(link, id, linkedMapOf("op" to "run", "id" to sid, "handler" to run["handler"], "args" to run["args"]))
                while (out.containsKey("call")) {
                    calls.add(linkedMapOf("call" to out["call"], "args" to out["args"]))
                    out = ask(link, id, linkedMapOf("op" to "reply", "id" to sid, "value" to if (left.isNotEmpty()) left.removeAt(0) else null))
                }
                val outcome = when {
                    out["done"] == true -> linkedMapOf("done" to true)
                    out["finish"] == true -> linkedMapOf("finish" to true)
                    else -> linkedMapOf("crash" to out["crash"], "what" to out["what"], "line" to out["line"])
                }
                if (calls != run["calls"]) problems.add("${item["name"]} run $r: calls $calls != ${run["calls"]}")
                if (outcome != run["outcome"]) problems.add("${item["name"]} run $r: outcome $outcome != ${run["outcome"]}")
            }
            ask(link, id, linkedMapOf("op" to "drop", "id" to sid))
        }
        Log.i(TAG, "replayed ${items.size} vectors through the isolated service, ${problems.size} problems")
        assertEquals(emptyList<String>(), problems)
    }

    @Test
    fun theServiceRunsInItsOwnIsolatedProcess() {
        val link = link()
        val id = link.open(64)
        assertTrue(id.isNotEmpty())
        val pong = ask(link, id, linkedMapOf("op" to "ping"))
        Log.i(TAG, "pong $pong; this process pid ${Process.myPid()} uid ${Process.myUid()}")
        assertEquals(true, pong["isolated"])
        assertEquals(true, pong["limited"])
        assertNotEquals(Process.myPid().toLong(), pong["pid"])
        assertNotEquals(Process.myUid().toLong(), pong["uid"])
        assertTrue("uid ${pong["uid"]}", (pong["uid"] as Long) % 100_000L in 90_000L..99_999L)
        assertEquals(64L, pong["memory_mb"])
        assertTrue((pong["heap_mb"] as Long) < 64L)
        val other = link.open(64)
        val second = ask(link, other, linkedMapOf("op" to "ping"))
        assertNotEquals(pong["pid"], second["pid"])
    }

    @Test
    fun theSandboxCannotReadTheAppsFilesOrReachTheNetwork() {
        val server = ServerSocket()
        server.bind(InetSocketAddress("127.0.0.1", 0))
        thread(isDaemon = true) {
            try {
                while (true) server.accept().close()
            } catch (e: Exception) {
                Log.d(TAG, "the test server closed")
            }
        }
        try {
            val files = File(context.applicationInfo.dataDir, "files")
            File(files, "script-probe-control.txt").writeText("x")
            assertTrue(files.list()!!.isNotEmpty())
            Socket().use { it.connect(InetSocketAddress("127.0.0.1", server.localPort), 1500) }
            val link = link(ScriptProbeService::class.java)
            val id = link.open(64)
            assertTrue(id.isNotEmpty())
            val probe = ask(link, id, linkedMapOf("op" to "probe", "port" to server.localPort.toLong()), 15_000L)
            Log.i(TAG, "probe $probe")
            val keys = listOf("list_files", "read_control", "read_config", "read_key", "list_self", "write_file", "shared_prefs", "keystore", "socket_local", "socket_internet", "dns")
            for (key in keys) assertTrue("$key: ${probe[key]}", (probe[key] as String).startsWith("refused"))
            assertTrue(!File(files, "script-probe.txt").exists())
        } finally {
            server.close()
            File(context.applicationInfo.dataDir, "files/script-probe-control.txt").delete()
        }
    }

    @Test
    fun aSilentProgramIsKilledAfterItsWait() {
        val link = link()
        val id = link.open(64)
        assertTrue(id.isNotEmpty())
        val loaded = ask(link, id, linkedMapOf("op" to "load", "id" to "s", "program" to hung(), "limits" to linkedMapOf("ms" to null, "steps" to 1_000_000_000_000L)))
        assertEquals(true, loaded["loaded"])
        val died = CountDownLatch(1)
        val binder: IBinder = link.binderOf(id)!!
        binder.linkToDeath({ died.countDown() }, 0)
        val started = SystemClock.elapsedRealtime()
        val answer = link.ask(id, Json.write(linkedMapOf("op" to "run", "id" to "s", "handler" to "on_start", "args" to arrayListOf<Any?>())), 3_000L)
        val waited = SystemClock.elapsedRealtime() - started
        assertEquals(ScriptLink.TIMEOUT, answer)
        assertTrue("waited $waited ms", waited in 2_900L..5_000L)
        assertTrue("the process was still alive", died.await(5, TimeUnit.SECONDS))
        Log.i(TAG, "the silent program's process was gone ${SystemClock.elapsedRealtime() - started} ms after it was asked")
        assertEquals(ScriptLink.CLOSED, link.ask(id, "{\"op\":\"ping\"}", 1_000L))
    }

    @Test
    fun aProgramThatComputesPastFiveSecondsEndsItsOwnProcess() {
        val link = link()
        val id = link.open(64)
        assertTrue(id.isNotEmpty())
        ask(link, id, linkedMapOf("op" to "load", "id" to "s", "program" to hung(), "limits" to linkedMapOf("ms" to null, "steps" to 1_000_000_000_000L)))
        val died = CountDownLatch(1)
        link.binderOf(id)!!.linkToDeath({ died.countDown() }, 0)
        val started = SystemClock.elapsedRealtime()
        val answer = Json.parse(link.ask(id, Json.write(linkedMapOf("op" to "run", "id" to "s", "handler" to "on_start", "args" to arrayListOf<Any?>())), 30_000L)) as Map<*, *>
        val waited = SystemClock.elapsedRealtime() - started
        Log.i(TAG, "the service ended itself after $waited ms: $answer")
        assertEquals("limit", answer["crash"])
        assertEquals("time", answer["what"])
        assertTrue("waited $waited ms", waited in 4_900L..8_000L)
        assertTrue(died.await(5, TimeUnit.SECONDS))
    }

    @Test
    fun theTimeLimitStopsAComputationOnItsOwn() {
        val link = link()
        val id = link.open(64)
        ask(link, id, linkedMapOf("op" to "load", "id" to "s", "program" to hung()))
        val answer = ask(link, id, linkedMapOf("op" to "run", "id" to "s", "handler" to "on_start", "args" to arrayListOf<Any?>()))
        assertEquals("limit", answer["crash"])
        assertTrue(answer["what"] == "time" || answer["what"] == "steps")
        assertEquals(true, ask(link, id, linkedMapOf("op" to "ping"))["pong"])
    }

    @Test
    fun starterProgramsRunEndToEndThroughTheBridge() {
        if (!Python.isStarted()) Python.start(AndroidPlatform(context))
        val link = link()
        val bridge = Bridge(KeyVault(context, File(context.cacheDir, "script-test.key")), null, null, null, null, scripts = link)
        val testing = Python.getInstance().getModule("pebble.android.testing")
        val names = (Json.parse(testing.callAttr("starter_stems").toString()) as List<*>).map { it as String }
        assertTrue(names.size >= 15)
        val problems = ArrayList<String>()
        for (name in names) {
            val started = SystemClock.elapsedRealtime()
            val out = Json.parse(testing.callAttr("script_dream", bridge, name).toString()) as Map<*, *>
            Log.i(TAG, "$name through the bridge in ${SystemClock.elapsedRealtime() - started} ms: passed ${out["passed"]}, same calls ${out["same_calls"]}, same words ${out["same_said"]}, ${out["calls"]} calls")
            if (out["engine"] != "phone" || out["passed"] != true || out["here_passed"] != true || out["same_calls"] != true || out["same_said"] != true || out["closed"] != true) problems.add("$name: $out")
        }
        assertEquals(emptyList<String>(), problems)
        val info = Json.parse(link.info()) as Map<*, *>
        assertEquals(0L, info["running"])
        assertEquals(names.size.toLong(), info["opened"])
    }

    private fun replayHere(item: Map<*, *>): List<String> {
        val problems = ArrayList<String>()
        val machine = Machine(item["program"], Limits.from(item["limits"]))
        var out = machine.start().go()
        if (out is Crash) return listOf("${item["name"]}: the top level crashed")
        (item["runs"] as List<*>).forEachIndexed { r, run ->
            run as Map<*, *>
            val left = ArrayList(run["replies"] as List<*>)
            val calls = ArrayList<Any?>()
            val going = machine.run(run["handler"] as String, run["args"] as List<Any?>)
            out = going.go()
            while (out is Call) {
                val call = out as Call
                calls.add(linkedMapOf("call" to call.name, "args" to call.args))
                out = going.go(if (left.isNotEmpty()) left.removeAt(0) else null)
            }
            val outcome = when (val o = out) {
                is Done -> linkedMapOf("done" to true)
                is Finish -> linkedMapOf("finish" to true)
                is Crash -> linkedMapOf("crash" to o.kind, "what" to o.what, "line" to o.line.toLong())
                else -> linkedMapOf("call" to "?")
            }
            if (Json.parse(Json.write(calls)) != run["calls"]) problems.add("${item["name"]} run $r: calls differ")
            if (outcome != run["outcome"]) problems.add("${item["name"]} run $r: outcome $outcome != ${run["outcome"]}")
        }
        return problems
    }

    companion object {
        const val TAG = "PebbleScriptTest"
    }
}
