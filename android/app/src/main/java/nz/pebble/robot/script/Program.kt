package nz.pebble.robot.script

data class Limits(
    val steps: Long = 100_000L,
    val ms: Double? = 50.0,
    val text: Long = 2000L,
    val items: Long = 500L,
    val depth: Long = 4L,
    val size: Long = 256L * 1024L,
    val recursion: Long = 20L,
    val keep: Long = 64L * 1024L,
) {
    companion object {
        fun from(data: Any?): Limits {
            val base = Limits()
            if (data !is Map<*, *> || data.isEmpty()) return base
            fun whole(key: String, fallback: Long): Long = when (val v = data[key]) {
                is Long -> v
                is Boolean -> if (v) 1L else 0L
                is Double -> v.toLong()
                is java.math.BigInteger -> if (v.signum() > 0) Long.MAX_VALUE else Long.MIN_VALUE
                else -> fallback
            }
            val ms = if (data.containsKey("ms")) {
                when (val v = data["ms"]) {
                    null -> null
                    is Long -> v.toDouble()
                    is Double -> v
                    is Boolean -> if (v) 1.0 else 0.0
                    else -> base.ms
                }
            } else {
                base.ms
            }
            return Limits(
                whole("steps", base.steps), ms, whole("text", base.text), whole("items", base.items),
                whole("depth", base.depth), whole("size", base.size), whole("recursion", base.recursion), whole("keep", base.keep),
            )
        }
    }
}

object Abilities {
    val NEEDED = Any()

    val SIGNATURES: Map<String, List<Pair<String, Any?>>> = linkedMapOf(
        "do" to listOf("request" to NEEDED),
        "say" to listOf("text" to NEEDED),
        "say_to" to listOf("who" to NEEDED, "text" to NEEDED),
        "ask" to listOf("who" to NEEDED, "question" to NEEDED, "choices" to null, "wait" to 20L),
        "face" to listOf("expression" to NEEDED),
        "draw" to listOf("scene" to NEEDED),
        "chirp" to listOf("pattern" to NEEDED),
        "hum" to listOf("tune" to NEEDED),
        "look" to listOf(),
        "where" to listOf("thing" to NEEDED),
        "who_here" to listOf(),
        "room" to listOf(),
        "state" to listOf("name" to NEEDED, "value" to null, "who" to null, "place" to null, "thing" to null, "at" to null, "end" to null, "day" to null, "minutes" to null, "level" to null, "what" to null),
        "now" to listOf(),
        "today" to listOf(),
        "feel" to listOf(),
        "dial" to listOf("name" to NEEDED),
        "tune" to listOf("name" to NEEDED, "value" to NEEDED, "why" to ""),
        "keep" to listOf("key" to NEEDED, "value" to NEEDED),
        "kept" to listOf("key" to NEEDED, "default" to null),
        "note" to listOf("text" to NEEDED),
        "wait" to listOf("seconds" to NEEDED),
        "chance" to listOf("p" to NEEDED),
        "pick" to listOf("items" to NEEDED),
        "finish" to listOf(),
    )

    private val GROUPS: Map<String, List<String>> = mapOf(
        "do" to listOf("do"),
        "say" to listOf("say", "say_to"),
        "ask" to listOf("ask"),
        "face" to listOf("face"),
        "draw" to listOf("draw"),
        "chirp" to listOf("chirp"),
        "hum" to listOf("hum"),
        "look" to listOf("look", "where", "who_here", "room", "state"),
        "dial" to listOf("dial"),
        "tune" to listOf("tune"),
    )

    private val GROUP_OF: Map<String, String> = GROUPS.flatMap { (group, names) -> names.map { it to group } }.toMap()
    private val FREE = setOf("keep", "kept", "now", "today", "feel", "note", "wait", "chance", "pick", "finish")
    val LOCAL = setOf("finish")

    fun groupOf(name: String): String = GROUP_OF[name] ?: name

    fun allowedBy(uses: List<String>, name: String): Boolean {
        if (name in FREE) return true
        return uses.any { groupOf(it) == groupOf(name) }
    }
}

sealed class Ex {
    @JvmField var pure = true
}

class ConstEx(val v: Any?) : Ex()
class NameEx(val n: String) : Ex()
class BinEx(val op: String, val a: Ex, val b: Ex) : Ex()
class UnEx(val op: String, val a: Ex) : Ex()
class BoolEx(val and: Boolean, val vs: List<Ex>) : Ex()
class CmpEx(val a: Ex, val ops: List<String>, val bs: List<Ex>) : Ex()
class IfEx(val c: Ex, val a: Ex, val b: Ex) : Ex()
class CallEx(val line: Int?, val f: String, val args: List<Ex>, val kw: List<Pair<String, Ex>>) : Ex()
class MethodEx(val line: Int?, val o: Ex, val m: String, val args: List<Ex>) : Ex()
class IndexEx(val o: Ex, val i: Ex) : Ex()
class SliceEx(val o: Ex, val lo: Ex?, val hi: Ex?, val st: Ex?) : Ex()
class ListEx(val items: List<Ex>, val tuple: Boolean) : Ex()
class DictEx(val keys: List<Ex>, val vals: List<Ex>) : Ex()
class FStrEx(val parts: List<Any>) : Ex()
class FName(val n: String)
class OddEx(val kind: String) : Ex()

sealed class Target
class NameT(val n: String) : Target()
class UnpackT(val names: List<String>) : Target()
class IndexT(val o: Ex, val i: Ex) : Target()
class ManyT(val items: List<Target>) : Target()

sealed class St(val line: Int?) {
    @JvmField var pure = true
}

class ExprSt(line: Int?, val v: Ex) : St(line)
class AssignSt(line: Int?, val to: Target, val v: Ex) : St(line)
class AugSt(line: Int?, val op: String, val to: Target, val v: Ex) : St(line)
class IfSt(line: Int?, val c: Ex, val then: List<St>, val els: List<St>) : St(line)
class WhileSt(line: Int?, val c: Ex, val body: List<St>) : St(line)
class ForSt(line: Int?, val to: Target, val over: Ex, val body: List<St>) : St(line)
class BreakSt(line: Int?) : St(line)
class ContinueSt(line: Int?) : St(line)
class ReturnSt(line: Int?, val v: Ex?) : St(line)
class OddSt(line: Int?, val kind: String) : St(line)

class Func(val name: String, val args: List<String>, val defaults: List<Any?>, val body: List<St>)

class BadProgram(message: String) : Exception(message)

class Program(
    val header: Map<Any, Any?>,
    val globals: List<St>,
    val funcs: LinkedHashMap<String, Func>,
) {
    companion object {
        val BUILTINS = setOf("len", "min", "max", "abs", "round", "int", "float", "str", "range", "sorted", "sum", "any", "all", "enumerate", "zip")

        fun from(data: Any?): Program {
            if (data !is Map<*, *>) throw BadProgram("a program is a dict")
            val header = LinkedHashMap<Any, Any?>()
            (data["header"] as? Map<*, *>)?.forEach { (k, v) -> if (k != null) header[k] = copy(v) }
            val globals = stmts(data["globals"])
            val funcs = LinkedHashMap<String, Func>()
            (data["funcs"] as? Map<*, *>)?.forEach { (name, body) ->
                val func = body as? Map<*, *> ?: throw BadProgram("a function is a dict")
                val args = (func["args"] as? List<*>)?.map { it as? String ?: throw BadProgram("an argument name is text") } ?: emptyList()
                val defaults = (func["defaults"] as? List<*>)?.map { plain(it) } ?: emptyList()
                funcs[name.toString()] = Func(name.toString(), args, defaults, stmts(func["body"]))
            }
            val program = Program(header, globals, funcs)
            for (func in funcs.values) for (stmt in func.body) markStmt(stmt)
            for (stmt in globals) markStmt(stmt)
            return program
        }

        fun copy(value: Any?): Any? = when (value) {
            is List<*> -> ArrayList<Any?>(value.map { copy(it) })
            is Map<*, *> -> LinkedHashMap<Any, Any?>().also { out -> value.forEach { (k, v) -> if (k != null) out[k] = copy(v) } }
            else -> value
        }

        private fun plain(value: Any?): Any? = when (value) {
            null, is Boolean, is Long, is Double, is String -> value
            is java.math.BigInteger -> throw BadProgram("a number in the program is too big")
            else -> throw BadProgram("a constant must be a plain value")
        }

        private fun line(node: Map<*, *>): Int? = when (val l = node["l"]) {
            is Long -> l.toInt()
            is Double -> l.toInt()
            else -> null
        }

        private fun stmts(data: Any?): List<St> {
            if (data == null) return emptyList()
            val list = data as? List<*> ?: throw BadProgram("statements are a list")
            return list.map { stmt(it as? Map<*, *> ?: throw BadProgram("a statement is a dict")) }
        }

        private fun stmt(node: Map<*, *>): St {
            val l = line(node)
            return when (val kind = node["t"] as? String ?: throw BadProgram("a statement needs a kind")) {
                "expr" -> ExprSt(l, expr(node["v"]))
                "assign" -> AssignSt(l, target(node["to"]), expr(node["v"]))
                "aug" -> AugSt(l, node["op"].toString(), target(node["to"]), expr(node["v"]))
                "if" -> IfSt(l, expr(node["c"]), stmts(node["then"]), stmts(node["else"]))
                "while" -> WhileSt(l, expr(node["c"]), stmts(node["body"]))
                "for" -> ForSt(l, target(node["to"]), expr(node["in"]), stmts(node["body"]))
                "break" -> BreakSt(l)
                "continue" -> ContinueSt(l)
                "return" -> ReturnSt(l, node["v"]?.let { expr(it) })
                else -> OddSt(l, kind)
            }
        }

        private fun target(data: Any?): Target {
            if (data is List<*>) return ManyT(data.map { target(it) })
            val node = data as? Map<*, *> ?: throw BadProgram("a target is a dict")
            return when (node["t"]) {
                "name" -> NameT(node["n"] as? String ?: throw BadProgram("a name is text"))
                "unpack" -> UnpackT((node["items"] as? List<*> ?: throw BadProgram("unpacking needs items")).map { ((it as? Map<*, *>)?.get("n") as? String) ?: throw BadProgram("a name is text") })
                "index" -> IndexT(expr(node["o"]), expr(node["i"]))
                else -> throw BadProgram("a target this program can't use")
            }
        }

        private fun exprs(data: Any?): List<Ex> = (data as? List<*> ?: throw BadProgram("expressions are a list")).map { expr(it) }

        private fun expr(data: Any?): Ex {
            val node = data as? Map<*, *> ?: throw BadProgram("an expression is a dict")
            return when (val kind = node["t"] as? String ?: throw BadProgram("an expression needs a kind")) {
                "const" -> ConstEx(plain(node["v"]))
                "name" -> NameEx(node["n"] as? String ?: throw BadProgram("a name is text"))
                "bin" -> BinEx(node["op"].toString(), expr(node["a"]), expr(node["b"]))
                "un" -> UnEx(node["op"].toString(), expr(node["a"]))
                "bool" -> BoolEx(node["op"] == "and", exprs(node["vs"]))
                "cmp" -> CmpEx(expr(node["a"]), (node["ops"] as? List<*> ?: throw BadProgram("a comparison needs its operators")).map { it.toString() }, exprs(node["bs"]))
                "ifx" -> IfEx(expr(node["c"]), expr(node["a"]), expr(node["b"]))
                "call" -> {
                    val kw = (node["kw"] as? Map<*, *>)?.map { (k, v) -> k.toString() to expr(v) } ?: emptyList()
                    CallEx(line(node), node["f"] as? String ?: throw BadProgram("a call needs a name"), exprs(node["args"]), kw)
                }
                "method" -> MethodEx(line(node), expr(node["o"]), node["m"] as? String ?: throw BadProgram("a method needs a name"), exprs(node["args"]))
                "index" -> IndexEx(expr(node["o"]), expr(node["i"]))
                "slice" -> SliceEx(expr(node["o"]), node["lo"]?.let { expr(it) }, node["hi"]?.let { expr(it) }, node["st"]?.let { expr(it) })
                "list" -> ListEx(exprs(node["items"]), false)
                "tuple" -> ListEx(exprs(node["items"]), true)
                "dict" -> DictEx(exprs(node["keys"]), exprs(node["vals"]))
                "fstr" -> FStrEx((node["parts"] as? List<*> ?: throw BadProgram("an f-string needs parts")).map { part ->
                    when (part) {
                        is String -> part
                        is Map<*, *> -> FName(part["n"] as? String ?: throw BadProgram("an f-string field is a name"))
                        else -> throw BadProgram("an f-string part is text or a name")
                    }
                })
                else -> OddEx(kind)
            }
        }

        private fun markStmt(stmt: St): Boolean {
            var pure = true
            when (stmt) {
                is ExprSt -> pure = mark(stmt.v) && pure
                is AssignSt -> {
                    pure = mark(stmt.v) && pure
                    pure = markTarget(stmt.to) && pure
                }
                is AugSt -> {
                    pure = mark(stmt.v) && pure
                    pure = markTarget(stmt.to) && pure
                }
                is IfSt -> {
                    pure = mark(stmt.c) && pure
                    for (inner in stmt.then) pure = markStmt(inner) && pure
                    for (inner in stmt.els) pure = markStmt(inner) && pure
                }
                is WhileSt -> {
                    pure = mark(stmt.c) && pure
                    for (inner in stmt.body) pure = markStmt(inner) && pure
                }
                is ForSt -> {
                    pure = mark(stmt.over) && pure
                    pure = markTarget(stmt.to) && pure
                    for (inner in stmt.body) pure = markStmt(inner) && pure
                }
                is ReturnSt -> stmt.v?.let { pure = mark(it) && pure }
                is BreakSt, is ContinueSt, is OddSt -> Unit
            }
            stmt.pure = pure
            return pure
        }

        private fun markTarget(target: Target): Boolean = when (target) {
            is IndexT -> mark(target.o) and mark(target.i)
            is ManyT -> {
                var pure = true
                for (item in target.items) pure = markTarget(item) && pure
                pure
            }
            else -> true
        }

        private fun mark(node: Ex): Boolean {
            var pure = true
            fun all(nodes: List<Ex>) {
                for (child in nodes) pure = mark(child) && pure
            }
            when (node) {
                is CallEx -> {
                    if (node.f !in BUILTINS) pure = false
                    all(node.args)
                    for ((_, v) in node.kw) pure = mark(v) && pure
                }
                is BinEx -> all(listOf(node.a, node.b))
                is UnEx -> all(listOf(node.a))
                is BoolEx -> all(node.vs)
                is CmpEx -> {
                    all(listOf(node.a))
                    all(node.bs)
                }
                is IfEx -> all(listOf(node.a, node.b, node.c))
                is MethodEx -> {
                    all(listOf(node.o))
                    all(node.args)
                }
                is IndexEx -> all(listOf(node.o, node.i))
                is SliceEx -> all(listOfNotNull(node.o, node.lo, node.hi, node.st))
                is ListEx -> all(node.items)
                is DictEx -> {
                    all(node.keys)
                    all(node.vals)
                }
                is ConstEx, is NameEx, is FStrEx, is OddEx -> Unit
            }
            node.pure = pure
            return pure
        }
    }
}
