package nz.pebble.robot.script

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class ScriptHostTest {
    @Suppress("UNCHECKED_CAST")
    private fun catCounter(): Any? {
        val url = javaClass.classLoader!!.getResource("script/vectors/handlers.json")!!
        val items = (Json.parse(File(url.toURI()).readText(Charsets.UTF_8)) as Map<*, *>)["vectors"] as List<Map<*, *>>
        return items.first { it["name"] == "the cat counter" }["program"]
    }

    private fun said(host: ScriptHost, message: Map<String, Any?>): Map<*, *> = Json.parse(host.handle(Json.write(message))!!) as Map<*, *>

    @Test
    fun theHostSpeaksThePcHostsJsonLines() {
        val host = ScriptHost()
        assertEquals(mapOf("id" to "s", "loaded" to true), said(host, linkedMapOf("op" to "load", "id" to "s", "program" to catCounter())))
        var out = said(host, linkedMapOf("op" to "run", "id" to "s", "handler" to "on_start", "args" to listOf<Any?>()))
        assertEquals("keep", out["call"])
        assertEquals(mapOf("key" to "count", "value" to 0L), out["args"])
        assertEquals(mapOf("id" to "s", "done" to true), said(host, linkedMapOf("op" to "reply", "id" to "s", "value" to null)))
        out = said(host, linkedMapOf("op" to "run", "id" to "s", "handler" to "on_at", "args" to listOf("21:00")))
        assertEquals("kept", out["call"])
        out = said(host, linkedMapOf("op" to "reply", "id" to "s", "value" to 3L))
        assertEquals("say_to", out["call"])
        assertEquals("The cat came 3 times.", (out["args"] as Map<*, *>)["text"])
        assertEquals(mapOf("id" to "s", "finish" to true), said(host, linkedMapOf("op" to "reply", "id" to "s", "value" to "done")))
        assertEquals("nothing was waiting for a reply", said(host, linkedMapOf("op" to "reply", "id" to "s", "value" to null))["text"])
        assertEquals(mapOf("id" to "s", "stopped" to true), said(host, linkedMapOf("op" to "stop", "id" to "s")))
        assertEquals(mapOf("id" to "s", "dropped" to true), said(host, linkedMapOf("op" to "drop", "id" to "s")))
        assertEquals("the program is not loaded", said(host, linkedMapOf("op" to "run", "id" to "s", "handler" to "on_start"))["text"])
        assertNull(host.handle("{\"op\":\"quit\"}"))
        assertTrue(host.quit)
    }

    @Test
    fun badLinesGetTheSameAnswersAsOnThePc() {
        val host = ScriptHost()
        assertEquals(mapOf("error" to "not JSON"), Json.parse(host.handle("{nope")!!))
        assertEquals(mapOf("error" to "unknown op"), Json.parse(host.handle("{\"op\":\"open\",\"id\":\"s\"}")!!))
        assertEquals(mapOf("error" to "line too long"), Json.parse(host.handle("x".repeat(ScriptHost.LINE_MOST + 1))!!))
        val pong = Json.parse(host.handle("{\"op\":\"ping\"}")!!) as Map<*, *>
        assertEquals(true, pong["pong"])
        val broken = said(host, linkedMapOf("op" to "load", "id" to "s", "program" to "not a program"))
        assertEquals("error", broken["crash"])
    }

    @Test
    fun aStoppedRunEndsAndALimitIsACrashNotAnAnswerForever() {
        val host = ScriptHost()
        said(host, linkedMapOf("op" to "load", "id" to "s", "program" to catCounter()))
        assertEquals("keep", said(host, linkedMapOf("op" to "run", "id" to "s", "handler" to "on_start"))["call"])
        assertEquals(true, said(host, linkedMapOf("op" to "stop", "id" to "s"))["stopped"])
        assertEquals("nothing was waiting for a reply", said(host, linkedMapOf("op" to "reply", "id" to "s"))["text"])
        val big = said(host, linkedMapOf("op" to "run", "id" to "s", "handler" to "on_at", "args" to listOf("21:00")))
        assertEquals("kept", big["call"])
        val crash = said(host, linkedMapOf("op" to "reply", "id" to "s", "value" to "x".repeat(2001)))
        assertEquals("limit", crash["crash"])
        assertEquals("text", crash["what"])
    }

    @Test
    fun theGuardStopsAProcessOverItsMemoryOrSilentTooLong() {
        var heap = 10L
        var now = 1_000L
        var garbage = 0L
        var collected = 0
        val guard = ScriptService.Guard(64L, 5_000L, { heap + garbage }, { now }, {
            collected++
            garbage = 0L
        })
        assertNull(guard.check())
        guard.begin()
        now += 4_999L
        assertNull(guard.check())
        now += 2L
        assertEquals(ScriptService.Guard.SILENT, guard.check())
        guard.end()
        assertNull(guard.check())
        garbage = 100L
        assertNull(guard.check())
        assertEquals(1, collected)
        heap = 65L
        assertEquals(ScriptService.Guard.MEMORY, guard.check())
        assertTrue(guard.overMemory())
    }

    @Test
    fun floatsAndTextShowAsPythonShowsThem() {
        val floats = mapOf(1e16 to "1e+16", 1e15 to "1000000000000000.0", 0.0001 to "0.0001", 1e-5 to "1e-05", -0.0 to "-0.0", 1.5e300 to "1.5e+300", 123456789012345678.0 to "1.2345678901234568e+17", 1e22 to "1e+22", 1e23 to "1e+23", 5e-324 to "5e-324", 0.1 to "0.1", 100.0 to "100.0", 0.1 + 0.2 to "0.30000000000000004")
        for ((x, text) in floats) assertEquals(text, Py.floatRepr(x))
        val g = mapOf(50.0 to "50", 0.5 to "0.5", 1e-5 to "1e-05", 1234567.0 to "1.23457e+06", 100000.0 to "100000", 1e6 to "1e+06")
        for ((x, text) in g) assertEquals(text, Py.gFormat(x))
        assertEquals("'it\\'s \"x\"'", Py.textRepr("it's \"x\""))
        assertEquals("\"it's\"", Py.textRepr("it's"))
        assertEquals("'\\x85\\xa0\\u2028\\ue000\\u0378'", Py.textRepr("\u0085  ͸"))
        assertEquals("'a\\x00\\u200bé\\x7f😀\\\\'", Py.textRepr("a\u0000​é\u007f😀\\"))
    }
}
