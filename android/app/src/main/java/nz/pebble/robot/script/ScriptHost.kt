package nz.pebble.robot.script

class ScriptHost(
    private val pong: () -> Map<String, Any?> = { mapOf("limited" to false) },
    private val extra: (String, Map<*, *>) -> Map<String, Any?>? = { _, _ -> null },
    private val timer: () -> Long = System::nanoTime,
) {
    private val machines = HashMap<String, Machine>()
    private val runs = HashMap<String, Run>()

    var quit = false
        private set

    @Volatile var lastId = ""
        private set

    fun handle(line: String): String? {
        if (line.length > LINE_MOST) return write(mapOf("error" to "line too long"))
        val message = try {
            Json.parse(line)
        } catch (e: JsonError) {
            return write(mapOf("error" to "not JSON"))
        } catch (e: NumberFormatException) {
            return write(mapOf("error" to "not JSON"))
        }
        if (message !is Map<*, *>) return write(mapOf("error" to "not JSON"))
        val op = message["op"]
        val id = message["id"].let { if (!Py.truth(it)) "" else if (it is String) it else Py.repr(it) }
        lastId = id
        try {
            when (op) {
                "quit" -> {
                    quit = true
                    return null
                }
                "ping" -> return write(LinkedHashMap<String, Any?>().apply {
                    put("pong", true)
                    putAll(pong())
                })
                "load" -> {
                    if (!message.containsKey("program")) throw NoSuchElementException("program")
                    val machine = Machine(message["program"], Limits.from(message["limits"]), timer)
                    machines[id] = machine
                    val result = machine.start().go()
                    return if (result is Crash) said(id, result) else write(linkedMapOf("id" to id, "loaded" to true))
                }
                "run" -> {
                    val machine = machines[id] ?: return said(id, Crash("error", "", 0, "the program is not loaded"))
                    val handler = message["handler"].let { if (!Py.truth(it)) "" else if (it is String) it else Py.repr(it) }
                    val args = when (val a = message["args"]) {
                        is List<*> -> ArrayList<Any?>(a)
                        null, false, 0L, 0.0, "" -> ArrayList()
                        is Map<*, *> -> ArrayList<Any?>(a.keys)
                        is String -> ArrayList<Any?>(Py.chars(a))
                        else -> throw IllegalArgumentException("args")
                    }
                    val run = machine.run(handler, args)
                    runs[id] = run
                    return out(id, run.go())
                }
                "reply" -> {
                    val run = runs[id] ?: return said(id, Crash("error", "", 0, "nothing was waiting for a reply"))
                    return out(id, run.go(message["value"]))
                }
                "stop" -> {
                    runs.remove(id)?.stop()
                    return write(linkedMapOf("id" to id, "stopped" to true))
                }
                "drop" -> {
                    machines.remove(id)
                    runs.remove(id)
                    return write(linkedMapOf("id" to id, "dropped" to true))
                }
                else -> {
                    val more = (op as? String)?.let { extra(it, message) } ?: return write(mapOf("error" to "unknown op"))
                    return write(LinkedHashMap<String, Any?>().apply {
                        put("id", id)
                        putAll(more)
                    })
                }
            }
        } catch (full: OutOfMemoryError) {
            runs.remove(id)
            return said(id, Crash("limit", "size", 0, "it used too much memory"))
        } catch (error: Exception) {
            runs.remove(id)
            return said(id, Crash("error", "", 0, "something went wrong (${error.javaClass.simpleName})"))
        }
    }

    private fun out(id: String, outcome: Outcome): String {
        if (outcome !is Call) runs.remove(id)
        return said(id, outcome)
    }

    private fun said(id: String, outcome: Outcome): String {
        val message = LinkedHashMap<String, Any?>()
        message["id"] = id
        message.putAll(messageOf(outcome))
        return write(message)
    }

    private fun write(message: Map<String, Any?>): String = Json.write(message)

    companion object {
        const val LINE_MOST = 1 shl 20

        fun messageOf(outcome: Outcome): Map<String, Any?> = when (outcome) {
            is Call -> linkedMapOf("call" to outcome.name, "args" to outcome.args, "line" to outcome.line)
            is Finish -> linkedMapOf("finish" to true)
            is Crash -> linkedMapOf("crash" to outcome.kind, "what" to outcome.what, "line" to outcome.line, "text" to outcome.text)
            is Done -> linkedMapOf("done" to true)
        }
    }
}
