package nz.pebble.robot.script

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class ScriptVectorsTest {
    @Suppress("UNCHECKED_CAST")
    private fun vectors(): List<Map<*, *>> {
        val url = javaClass.classLoader!!.getResource("script/vectors") ?: error("the vectors were not copied in from brain/pebble/script/vectors")
        val files = File(url.toURI()).listFiles { f -> f.name.endsWith(".json") }!!.sortedBy { it.name }
        assertTrue(files.size >= 10)
        return files.flatMap { (Json.parse(it.readText(Charsets.UTF_8)) as Map<*, *>)["vectors"] as List<Map<*, *>> }
    }

    @Test
    fun everyVectorReplaysAsInPython() {
        val items = vectors()
        assertTrue(items.size >= 80)
        assertEquals(items.size, items.map { it["name"] }.toSet().size)
        val problems = items.flatMap { replay(it) }
        assertEquals(emptyList<String>(), problems)
        println("replayed ${items.size} vectors, ${problems.size} problems")
    }

    @Test
    fun theVectorsReplayTheSameASecondTime() {
        val items = vectors()
        val problems = items.flatMap { replay(it) } + items.flatMap { replay(it) }
        assertEquals(emptyList<String>(), problems)
    }

    @Suppress("UNCHECKED_CAST")
    @Test
    fun aVectorWithAWrongAnswerIsCaught() {
        val item = vectors().first { it["name"] == "whole division" }
        val copy = Json.parse(Json.write(item)) as MutableMap<Any, Any?>
        val run = (copy["runs"] as List<MutableMap<Any, Any?>>)[0]
        ((run["calls"] as List<MutableMap<Any, Any?>>)[1]["args"] as MutableMap<Any, Any?>)["text"] = "-3"
        assertEquals(1, replay(copy).size)
        run["outcome"] = linkedMapOf<Any, Any?>("finish" to true)
        assertEquals(2, replay(copy).size)
    }

    companion object {
        fun replay(item: Map<*, *>): List<String> {
            val name = item["name"]
            val problems = ArrayList<String>()
            val machine = Machine(item["program"], Limits.from(item["limits"]))
            val (_, start) = runOn(machine, null, emptyList(), emptyList())
            if (start.containsKey("crash")) return listOf("$name: the top level crashed $start")
            (item["runs"] as List<*>).forEachIndexed { index, r ->
                val run = r as Map<*, *>
                val (calls, out) = runOn(machine, run["handler"] as String, run["args"] as List<Any?>, run["replies"] as List<Any?>)
                if (calls != run["calls"]) problems.add("$name run $index: calls $calls != ${run["calls"]}")
                if (out != run["outcome"]) problems.add("$name run $index: outcome $out != ${run["outcome"]}")
            }
            return problems
        }

        fun runOn(machine: Machine, handler: String?, args: List<Any?>, replies: List<Any?>): Pair<Any?, Map<Any, Any?>> {
            val run = if (handler == null) machine.start() else machine.run(handler, args)
            var out = run.go()
            val calls = ArrayList<Any?>()
            val left = ArrayList(replies)
            while (out is Call) {
                calls.add(linkedMapOf("call" to out.name, "args" to out.args))
                out = run.go(if (left.isNotEmpty()) left.removeAt(0) else null)
            }
            return Json.parse(Json.write(calls)) to actual(out)
        }

        private fun actual(outcome: Outcome): Map<Any, Any?> = when (outcome) {
            is Done -> linkedMapOf("done" to true)
            is Finish -> linkedMapOf("finish" to true)
            is Crash -> linkedMapOf("crash" to outcome.kind, "what" to outcome.what, "line" to outcome.line.toLong())
            is Call -> linkedMapOf("call" to outcome.name)
        }
    }
}
