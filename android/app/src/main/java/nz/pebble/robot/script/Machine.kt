package nz.pebble.robot.script

import java.math.BigInteger

sealed class Outcome

class Call(val name: String, val args: LinkedHashMap<String, Any?>, val line: Int) : Outcome()

class Done(val value: Any?) : Outcome()

object Finish : Outcome()

class Crash(val kind: String, val what: String, val line: Int, val text: String) : Outcome()

class Fail(val kind: String, val what: String, val text: String) : RuntimeException(text) {
    override fun fillInStackTrace(): Throwable = this
}

class Finishing : RuntimeException() {
    override fun fillInStackTrace(): Throwable = this
}

class Ret(val value: Any?)

class Machine(program: Any?, val limits: Limits = Limits(), private val timer: () -> Long = System::nanoTime) {
    private val code: Program = Program.from(program)
    val header: Map<Any, Any?> = code.header
    val uses: List<String> = when (val u = header["USES"]) {
        is List<*> -> u.map { if (it is String) it else Py.repr(it) }
        is String -> Py.chars(u)
        else -> emptyList()
    }
    private val funcs = code.funcs
    private val locals: Map<String, Set<String>> = funcs.mapValues { (_, func) -> localsOf(func) }
    val globals = LinkedHashMap<String, Any?>()
    private var frames = ArrayList<LinkedHashMap<String, Any?>>()
    private var names = ArrayList<String>()
    var steps = 0L
    var since = 0L
    var line = 0
    internal var reply: Any? = null

    fun now(): Long = timer()

    private fun localsOf(func: Func): Set<String> {
        val found = HashSet<String>(func.args)
        fun targets(target: Target) {
            when (target) {
                is ManyT -> target.items.forEach { targets(it) }
                is NameT -> found.add(target.n)
                is UnpackT -> found.addAll(target.names)
                is IndexT -> Unit
            }
        }
        fun walk(stmts: List<St>) {
            for (stmt in stmts) {
                when (stmt) {
                    is AssignSt -> targets(stmt.to)
                    is AugSt -> targets(stmt.to)
                    is ForSt -> {
                        targets(stmt.to)
                        walk(stmt.body)
                    }
                    is IfSt -> {
                        walk(stmt.then)
                        walk(stmt.els)
                    }
                    is WhileSt -> walk(stmt.body)
                    else -> Unit
                }
            }
        }
        walk(func.body)
        return found
    }

    fun start(): Run = Run(this) { startGen() }

    private suspend fun SequenceScope<Call>.startGen(): Any? {
        for (name in listOf("ABOUT", "USES", "FOR", "UNTIL", "WANTS")) {
            if (header.containsKey(name)) globals[name] = header[name]
        }
        frames = ArrayList()
        names = ArrayList()
        return blockGen(code.globals)
    }

    fun run(handler: String, args: List<Any?> = emptyList()): Run = Run(this) { handleGen(handler, args) }

    private suspend fun SequenceScope<Call>.handleGen(handler: String, args: List<Any?>): Any? {
        val func = funcs[handler]
        frames = ArrayList()
        names = ArrayList()
        if (func == null) return null
        val params = func.args
        val defaults = func.defaults
        val firstDefault = params.size - defaults.size
        val bound = ArrayList<Any?>()
        for (index in params.indices) {
            when {
                index < args.size -> bound.add(args[index])
                index >= firstDefault -> bound.add(defaults[index - firstDefault])
                else -> bound.add(null)
            }
        }
        return callUser(handler, bound, LinkedHashMap())
    }

    fun clear() {
        frames = ArrayList()
        names = ArrayList()
    }

    fun tick() {
        steps++
        if (steps > limits.steps) throw limit("steps", "it ran more than ${Py.commas(limits.steps)} steps")
        if ((steps and CHECK_TIME_EVERY) == 0L) {
            if (overTime()) throw timeUp()
            if ((steps and CHECK_SIZE_EVERY) == 0L) checkAll()
        }
    }

    private fun overTime(): Boolean {
        val ms = limits.ms ?: return false
        return (timer() - since) / 1_000_000.0 > ms
    }

    private fun timeUp(): Fail = limit("time", "it computed for more than ${Py.gFormat(limits.ms)} ms without stopping")

    fun checkAll() {
        val budget = limits.size
        var used = 0L
        val scopes = ArrayList<Map<String, Any?>>()
        scopes.add(globals)
        scopes.addAll(frames)
        for (scope in scopes) {
            for (value in scope.values) used += measure(value, budget - used)[0]
        }
        if (used > budget) throw limit("size", "its values came to more than ${budget / 1024} KB")
    }

    fun measure(value: Any?, budget: Long = limits.size, forbid: Any? = null): LongArray {
        var total = 0L
        var deepest = 0L
        val items = ArrayList<Any?>()
        val levels = ArrayList<Long>()
        items.add(value)
        levels.add(0L)
        var seen = 0L
        while (items.isNotEmpty()) {
            val item = items.removeAt(items.size - 1)
            var level = levels.removeAt(levels.size - 1)
            seen++
            if ((seen and 4095L) == 0L && overTime()) throw timeUp()
            if (forbid != null && item === forbid) throw err("a list or dict can't hold itself")
            when (item) {
                is String -> total += SCALAR + Py.textLength(item)
                is ArrayList<*>, is Tup -> {
                    total += SCALAR
                    level += 1
                    if (level > deepest) deepest = level
                    if (level > limits.depth) throw limit("depth", "lists and dicts nest at most ${limits.depth} deep")
                    val children = if (item is Tup) item.items else item as List<*>
                    for (child in children) {
                        items.add(child)
                        levels.add(level)
                    }
                }
                is Map<*, *> -> {
                    total += SCALAR
                    level += 1
                    if (level > deepest) deepest = level
                    if (level > limits.depth) throw limit("depth", "lists and dicts nest at most ${limits.depth} deep")
                    for ((key, child) in item) {
                        items.add(key)
                        levels.add(level)
                        items.add(child)
                        levels.add(level)
                    }
                }
                else -> total += SCALAR
            }
            if (total > budget) throw limit("size", "its values came to more than ${limits.size / 1024} KB")
        }
        return longArrayOf(total, deepest)
    }

    private fun text(value: String): String {
        if (Py.textLength(value) > limits.text) throw textLimit()
        return value
    }

    private fun textLimit(): Fail = limit("text", "text is at most ${Py.commas(limits.text)} characters")

    private fun itemsLimit(): Fail = limit("items", "a list or dict holds at most ${limits.items} items")

    private fun count(size: Long) {
        if (size > limits.items) throw itemsLimit()
    }

    private fun made(value: Any?): Any? {
        when (value) {
            is String -> return text(value)
            is ArrayList<*>, is Tup, is Map<*, *> -> {
                count(Py.length(value))
                measure(value)
            }
        }
        return value
    }

    private fun number(value: Any?): Any? {
        if (value is Long && (value < -Py.MAX_INT || value > Py.MAX_INT)) throw tooBig()
        if (value is Double && !value.isFinite()) throw tooBig()
        if (value is BigInteger) throw tooBig()
        return value
    }

    private fun tooBig(): Fail = limit("number", "a number got too big")

    private fun lookup(name: String): Any? {
        if (frames.isNotEmpty()) {
            val frame = frames[frames.size - 1]
            if (frame.containsKey(name)) return frame[name]
            if (name in (locals[names[names.size - 1]] ?: emptySet())) throw err("'$name' is used before it is set")
        }
        if (globals.containsKey(name)) return globals[name]
        if (funcs.containsKey(name)) throw err("'$name' is a function; call it with ()")
        throw err("'$name' is not defined")
    }

    private fun store(name: String, value: Any?) {
        if (frames.isNotEmpty()) frames[frames.size - 1][name] = value else globals[name] = value
    }

    private fun block(stmts: List<St>): Any? {
        for (stmt in stmts) {
            val code = ex(stmt)
            if (code != null) return code
        }
        return null
    }

    private suspend fun SequenceScope<Call>.blockGen(stmts: List<St>): Any? {
        for (stmt in stmts) {
            val code = if (stmt.pure) ex(stmt) else exGen(stmt)
            if (code != null) return code
        }
        return null
    }

    private fun ex(stmt: St): Any? {
        tick()
        stmt.line?.let { line = it }
        when (stmt) {
            is ExprSt -> {
                ev(stmt.v)
                return null
            }
            is AssignSt -> {
                assign(stmt.to, ev(stmt.v), null)
                return null
            }
            is AugSt -> {
                val value = ev(stmt.v)
                augment(stmt, value, evTargetParts(stmt.to))
                return null
            }
            is IfSt -> return block(if (Py.truth(ev(stmt.c))) stmt.then else stmt.els)
            is WhileSt -> {
                while (Py.truth(ev(stmt.c))) {
                    val code = block(stmt.body)
                    if (code === BREAK) break
                    if (code is Ret) return code
                    tick()
                }
                return null
            }
            is ForSt -> {
                val items = iterate(ev(stmt.over))
                for (item in items) {
                    assign(stmt.to, item, null)
                    val code = block(stmt.body)
                    if (code === BREAK) break
                    if (code is Ret) return code
                    tick()
                }
                return null
            }
            is BreakSt -> return BREAK
            is ContinueSt -> return CONTINUE
            is ReturnSt -> return Ret(if (stmt.v != null) ev(stmt.v) else null)
            is OddSt -> throw err("${stmt.kind} is not something a script can do")
        }
    }

    private suspend fun SequenceScope<Call>.exGen(stmt: St): Any? {
        tick()
        stmt.line?.let { line = it }
        when (stmt) {
            is ExprSt -> {
                sub(stmt.v)
                return null
            }
            is AssignSt -> {
                val value = sub(stmt.v)
                val parts = targetPartsGen(stmt.to)
                assign(stmt.to, value, parts)
                return null
            }
            is AugSt -> {
                val value = sub(stmt.v)
                val parts = targetPartsGen(stmt.to)
                augment(stmt, value, parts)
                return null
            }
            is IfSt -> {
                val test = sub(stmt.c)
                return blockGen(if (Py.truth(test)) stmt.then else stmt.els)
            }
            is WhileSt -> {
                while (true) {
                    val test = sub(stmt.c)
                    if (!Py.truth(test)) break
                    val code = blockGen(stmt.body)
                    if (code === BREAK) break
                    if (code is Ret) return code
                    tick()
                }
                return null
            }
            is ForSt -> {
                val items = sub(stmt.over)
                for (item in iterate(items)) {
                    assign(stmt.to, item, null)
                    val code = blockGen(stmt.body)
                    if (code === BREAK) break
                    if (code is Ret) return code
                    tick()
                }
                return null
            }
            is ReturnSt -> {
                val value = if (stmt.v != null) sub(stmt.v) else null
                return Ret(value)
            }
            else -> return ex(stmt)
        }
    }

    private suspend fun SequenceScope<Call>.sub(node: Ex): Any? = if (node.pure) ev(node) else evGen(node)

    private fun evTargetParts(target: Target): Pair<Any?, Any?>? = if (target is IndexT) Pair(ev(target.o), ev(target.i)) else null

    private suspend fun SequenceScope<Call>.targetPartsGen(target: Target): Pair<Any?, Any?>? {
        if (target !is IndexT) return null
        val obj = sub(target.o)
        val index = sub(target.i)
        return Pair(obj, index)
    }

    private fun assign(target: Target, value: Any?, parts: Pair<Any?, Any?>?) {
        when (target) {
            is ManyT -> for (item in target.items) assign(item, value, null)
            is NameT -> store(target.n, value)
            is UnpackT -> {
                val items = when (value) {
                    is ArrayList<*> -> value
                    is Tup -> value.items
                    else -> throw err("can't unpack ${Py.kindWords(value)} into ${target.names.size} names")
                }
                if (items.size != target.names.size) throw err("${target.names.size} names but ${items.size} values")
                for (i in target.names.indices) store(target.names[i], items[i])
            }
            is IndexT -> {
                val (obj, index) = parts ?: Pair(ev(target.o), ev(target.i))
                setItem(obj, index, value)
            }
        }
    }

    @Suppress("UNCHECKED_CAST")
    private fun setItem(obj: Any?, index: Any?, value: Any?) {
        if (obj is ArrayList<*>) {
            val list = obj as ArrayList<Any?>
            if (!Py.isWhole(index)) throw err("a list's position must be a whole number")
            val i = Py.long(index)
            if (i < -list.size || i >= list.size) throw err("position ${Py.repr(index)} is past the end of a list of ${list.size}")
            holds(list, value)
            list[(if (i < 0) i + list.size else i).toInt()] = value
            return
        }
        if (obj is LinkedHashMap<*, *>) {
            val map = obj as LinkedHashMap<Any, Any?>
            key(index)
            if (!map.containsKey(index!!) && map.size + 1 > limits.items) throw itemsLimit()
            holds(map, value)
            map[index] = value
            return
        }
        throw err("can't set an item in ${Py.kindWords(obj)}")
    }

    private fun holds(container: Any, value: Any?) {
        val depth = measure(value, forbid = container)[1]
        if (depth + 1 > limits.depth) throw limit("depth", "lists and dicts nest at most ${limits.depth} deep")
    }

    private fun key(key: Any?) {
        if (!(key is String || key is Long)) throw err("a dict's keys must be text or whole numbers")
    }

    @Suppress("UNCHECKED_CAST")
    private fun augment(stmt: AugSt, value: Any?, parts: Pair<Any?, Any?>?) {
        val target = stmt.to
        val op = stmt.op
        if (target is NameT) {
            val current = lookup(target.n)
            if (op == "+" && current is ArrayList<*>) {
                extend(current as ArrayList<Any?>, value)
                return
            }
            store(target.n, binop(op, current, value))
            return
        }
        val (obj, index) = parts ?: throw IllegalStateException("cannot unpack non-iterable NoneType object")
        val current = getItem(obj, index)
        if (op == "+" && current is ArrayList<*>) {
            extend(current as ArrayList<Any?>, value)
            return
        }
        setItem(obj, index, binop(op, current, value))
    }

    private fun extend(current: ArrayList<Any?>, value: Any?) {
        val items = when (value) {
            is ArrayList<*> -> ArrayList<Any?>(value)
            is Tup -> value.items
            else -> throw err("can't add ${Py.kindWords(value)} to a list")
        }
        count(current.size.toLong() + items.size)
        for (item in items) holds(current, item)
        current.addAll(items)
        measure(current)
    }

    private fun iterate(value: Any?): Iterable<Any?> = when (value) {
        is ArrayList<*> -> ArrayList<Any?>(value)
        is Tup -> ArrayList<Any?>(value.items)
        is String -> Py.chars(value)
        is Map<*, *> -> ArrayList<Any?>(value.keys)
        is PyRange -> Iterable { value.values() }
        else -> throw err("can't loop over ${Py.kindWords(value)}")
    }

    private fun itemsOf(value: Any?): ArrayList<Any?> {
        if (value is PyRange) {
            if (value.size > limits.items) throw itemsLimit()
            val out = ArrayList<Any?>()
            value.values().forEach { out.add(it) }
            return out
        }
        return ArrayList(iterate(value).toList())
    }

    private fun ev(node: Ex): Any? {
        tick()
        when (node) {
            is ConstEx -> return node.v
            is NameEx -> return lookup(node.n)
            is BinEx -> {
                val a = ev(node.a)
                return binop(node.op, a, ev(node.b))
            }
            is UnEx -> return unop(node.op, ev(node.a))
            is BoolEx -> {
                var value: Any? = null
                for (part in node.vs) {
                    value = ev(part)
                    if (node.and != Py.truth(value)) return value
                }
                return value
            }
            is CmpEx -> {
                var left = ev(node.a)
                for (i in 0 until minOf(node.ops.size, node.bs.size)) {
                    val right = ev(node.bs[i])
                    if (!compare(node.ops[i], left, right)) return false
                    left = right
                }
                return true
            }
            is IfEx -> return if (Py.truth(ev(node.c))) ev(node.a) else ev(node.b)
            is CallEx -> {
                node.line?.let { line = it }
                val args = node.args.map { ev(it) }
                val kw = LinkedHashMap<String, Any?>()
                for ((k, v) in node.kw) kw[k] = ev(v)
                return builtin(node.f, args, kw)
            }
            is MethodEx -> {
                node.line?.let { line = it }
                val obj = ev(node.o)
                return method(obj, node.m, node.args.map { ev(it) })
            }
            is IndexEx -> {
                val obj = ev(node.o)
                return getItem(obj, ev(node.i))
            }
            is SliceEx -> {
                val obj = ev(node.o)
                val lo = node.lo?.let { ev(it) }
                val hi = node.hi?.let { ev(it) }
                val st = node.st?.let { ev(it) }
                return slice(obj, lo, hi, st)
            }
            is ListEx -> {
                val items = ArrayList<Any?>()
                for (e in node.items) items.add(ev(e))
                return made(if (node.tuple) Tup(items) else items)
            }
            is DictEx -> {
                val keys = node.keys.map { ev(it) }
                val vals = node.vals.map { ev(it) }
                return dictOf(keys, vals)
            }
            is FStrEx -> return fstr(node.parts)
            is OddEx -> throw err("${node.kind} is not something a script can work out")
        }
    }

    private suspend fun SequenceScope<Call>.evGen(node: Ex): Any? {
        tick()
        when (node) {
            is BinEx -> {
                val a = sub(node.a)
                val b = sub(node.b)
                return binop(node.op, a, b)
            }
            is UnEx -> {
                val a = sub(node.a)
                return unop(node.op, a)
            }
            is BoolEx -> {
                var value: Any? = null
                for (part in node.vs) {
                    value = sub(part)
                    if (node.and != Py.truth(value)) return value
                }
                return value
            }
            is CmpEx -> {
                var left = sub(node.a)
                for (i in 0 until minOf(node.ops.size, node.bs.size)) {
                    val right = sub(node.bs[i])
                    if (!compare(node.ops[i], left, right)) return false
                    left = right
                }
                return true
            }
            is IfEx -> {
                val test = sub(node.c)
                return sub(if (Py.truth(test)) node.a else node.b)
            }
            is CallEx -> {
                val args = ArrayList<Any?>()
                for (a in node.args) args.add(sub(a))
                val kw = LinkedHashMap<String, Any?>()
                for ((k, v) in node.kw) kw[k] = sub(v)
                node.line?.let { line = it }
                val name = node.f
                if (name in Program.BUILTINS) return builtin(name, args, kw)
                if (funcs.containsKey(name)) return callUser(name, args, kw)
                return ability(name, args, kw)
            }
            is MethodEx -> {
                val obj = sub(node.o)
                val args = ArrayList<Any?>()
                for (a in node.args) args.add(sub(a))
                node.line?.let { line = it }
                return method(obj, node.m, args)
            }
            is IndexEx -> {
                val obj = sub(node.o)
                val index = sub(node.i)
                return getItem(obj, index)
            }
            is SliceEx -> {
                val obj = sub(node.o)
                val lo = if (node.lo != null) sub(node.lo) else null
                val hi = if (node.hi != null) sub(node.hi) else null
                val st = if (node.st != null) sub(node.st) else null
                return slice(obj, lo, hi, st)
            }
            is ListEx -> {
                val items = ArrayList<Any?>()
                for (e in node.items) items.add(sub(e))
                return made(if (node.tuple) Tup(items) else items)
            }
            is DictEx -> {
                val keys = ArrayList<Any?>()
                val values = ArrayList<Any?>()
                for (i in 0 until minOf(node.keys.size, node.vals.size)) {
                    keys.add(sub(node.keys[i]))
                    values.add(sub(node.vals[i]))
                }
                return dictOf(keys, values)
            }
            else -> return ev(node)
        }
    }

    private suspend fun SequenceScope<Call>.callUser(name: String, args: List<Any?>, kw: Map<String, Any?>): Any? {
        val func = funcs[name]!!
        val params = func.args
        val defaults = func.defaults
        if (args.size > params.size) throw err("$name() takes ${params.size} arguments but got ${args.size}")
        val frame = LinkedHashMap<String, Any?>()
        for (i in args.indices) frame[params[i]] = args[i]
        for ((k, v) in kw) {
            if (k !in params) throw err("$name() has no argument called $k")
            if (frame.containsKey(k)) throw err("$name() got $k twice")
            frame[k] = v
        }
        val firstDefault = params.size - defaults.size
        for ((index, param) in params.withIndex()) {
            if (!frame.containsKey(param)) {
                if (index >= firstDefault) frame[param] = defaults[index - firstDefault] else throw err("$name() needs $param")
            }
        }
        if (frames.size >= limits.recursion) throw limit("recursion", "functions call each other at most ${limits.recursion} deep")
        frames.add(frame)
        names.add(name)
        val saved = line
        val code = blockGen(func.body)
        frames.removeAt(frames.size - 1)
        names.removeAt(names.size - 1)
        line = saved
        return if (code is Ret) code.value else null
    }

    private fun bind(name: String, args: List<Any?>, kw: Map<String, Any?>): LinkedHashMap<String, Any?> {
        val signature = Abilities.SIGNATURES.getValue(name)
        if (args.size > signature.size) throw err("$name() takes at most ${signature.size} arguments")
        val out = LinkedHashMap<String, Any?>()
        for (i in args.indices) out[signature[i].first] = args[i]
        val params = signature.map { it.first }
        for ((k, v) in kw) {
            if (k !in params) throw err("$name() has no argument called $k")
            if (out.containsKey(k)) throw err("$name() got $k twice")
            out[k] = v
        }
        for ((param, default) in signature) {
            if (!out.containsKey(param)) {
                if (default === Abilities.NEEDED) throw err("$name() needs $param")
                out[param] = default
            }
        }
        val ordered = LinkedHashMap<String, Any?>()
        for (param in params) ordered[param] = out[param]
        return ordered
    }

    private suspend fun SequenceScope<Call>.ability(name: String, args: List<Any?>, kw: Map<String, Any?>): Any? {
        if (name !in Abilities.SIGNATURES) throw err("'$name' is not a function you can use")
        if (!Abilities.allowedBy(uses, name)) throw Fail("uses", name, "$name() is not in USES")
        val bound = bind(name, args, kw)
        for (value in bound.values) measure(value)
        if (name in Abilities.LOCAL) throw Finishing()
        yield(Call(name, bound, line))
        return reply
    }

    fun accept(value: Any?): Any? {
        val v = if (value is Tup) ArrayList(value.items) else value
        plain(v, 0)
        if (v is ArrayList<*> || v is Map<*, *> || v is String) made(v)
        return v
    }

    private fun plain(value: Any?, level: Long) {
        if (level > limits.depth + 1) throw limit("depth", "lists and dicts nest at most ${limits.depth} deep")
        when (value) {
            null, is Boolean, is String -> return
            is Long, is Double, is BigInteger -> {
                number(value)
                return
            }
            is ArrayList<*> -> {
                for (item in value) plain(item, level + 1)
                return
            }
            is Map<*, *> -> {
                for ((k, item) in value) {
                    if (!(k is String || k is Long)) throw err("a reply held a key that is not text")
                    plain(item, level + 1)
                }
                return
            }
            else -> throw err("a reply held something that is not a plain value")
        }
    }

    private fun dictOf(keys: List<Any?>, values: List<Any?>): Any? {
        val out = LinkedHashMap<Any, Any?>()
        for (i in 0 until minOf(keys.size, values.size)) {
            key(keys[i])
            out[keys[i]!!] = values[i]
        }
        return made(out)
    }

    private fun binop(op: String, a: Any?, b: Any?): Any? {
        if (op == "+") {
            if (Py.isNum(a) && Py.isNum(b)) {
                if (Py.isWhole(a) && Py.isWhole(b)) return number(exact { Math.addExact(Py.long(a), Py.long(b)) })
                return number(Py.double(a) + Py.double(b))
            }
            if (a is String && b is String) {
                if (Py.textLength(a).toLong() + Py.textLength(b) > limits.text) throw textLimit()
                return a + b
            }
            if (a is ArrayList<*> && b is ArrayList<*>) {
                if (a.size.toLong() + b.size > limits.items) throw itemsLimit()
                return made(ArrayList<Any?>(a).apply { addAll(b) })
            }
            if (a is Tup && b is Tup) {
                if (a.items.size.toLong() + b.items.size > limits.items) throw itemsLimit()
                return made(Tup(a.items + b.items))
            }
            throw err("can't add ${Py.kindWords(a)} and ${Py.kindWords(b)}")
        }
        if (op == "*") {
            if (Py.isNum(a) && Py.isNum(b)) {
                if (Py.isWhole(a) && Py.isWhole(b)) return number(exact { Math.multiplyExact(Py.long(a), Py.long(b)) })
                return number(Py.double(a) * Py.double(b))
            }
            var x = a
            var y = b
            if ((y is String || y is ArrayList<*> || y is Tup) && Py.isWhole(x)) {
                x = b
                y = a
            }
            if ((x is String || x is ArrayList<*> || x is Tup) && Py.isWhole(y)) {
                val times = maxOf(0L, Py.long(y))
                if (x is String) {
                    if (over(Py.textLength(x).toLong(), times, limits.text)) throw textLimit()
                    return if (x.isEmpty()) "" else x.repeat(times.toInt())
                }
                val items = if (x is Tup) x.items else x as List<*>
                if (over(items.size.toLong(), times, limits.items)) throw itemsLimit()
                val size = measure(x)[0]
                if (over(size, times, limits.size)) throw limit("size", "its values came to more than ${limits.size / 1024} KB")
                val out = ArrayList<Any?>()
                for (n in 0 until times) out.addAll(items)
                return made(if (x is Tup) Tup(out) else out)
            }
            throw err("can't multiply ${Py.kindWords(a)} by ${Py.kindWords(b)}")
        }
        if (!(Py.isNum(a) && Py.isNum(b))) {
            if (op == "%" && a is String) throw err("% doesn't format text here; use an f-string with plain {names}")
            throw err("can't use $op on ${Py.kindWords(a)} and ${Py.kindWords(b)}")
        }
        val whole = Py.isWhole(a) && Py.isWhole(b)
        when (op) {
            "-" -> return if (whole) number(exact { Math.subtractExact(Py.long(a), Py.long(b)) }) else number(Py.double(a) - Py.double(b))
            "/" -> {
                if (Py.cmpNum(b, 0L) == 0) throw err("can't divide by zero")
                return number(Py.double(a) / Py.double(b))
            }
            "//" -> {
                if (Py.cmpNum(b, 0L) == 0) throw err("can't divide by zero")
                return if (whole) number(Math.floorDiv(Py.long(a), Py.long(b))) else number(Py.floatFloorDiv(Py.double(a), Py.double(b)))
            }
            "%" -> {
                if (Py.cmpNum(b, 0L) == 0) throw err("can't divide by zero")
                return if (whole) number(Math.floorMod(Py.long(a), Py.long(b))) else number(Py.floatMod(Py.double(a), Py.double(b)))
            }
            "**" -> return power(a, b)
        }
        throw err("$op is not allowed")
    }

    private fun over(n: Long, times: Long, most: Long): Boolean = n > 0 && times > most / n

    private inline fun exact(block: () -> Long): Long = try {
        block()
    } catch (e: ArithmeticException) {
        throw tooBig()
    }

    private fun power(a: Any?, b: Any?): Any? {
        if (Py.isWhole(a) && Py.isWhole(b) && Py.long(b) >= 0) {
            val base = Py.long(a)
            val exp = Py.long(b)
            when (base) {
                0L -> return if (exp == 0L) 1L else 0L
                1L -> return 1L
                -1L -> return if (exp % 2L == 0L) 1L else -1L
            }
            if (exp * (Math.log(Math.abs(base.toDouble())) / Math.log(2.0)) > 53) throw tooBig()
            return number(BigInteger.valueOf(base).pow(exp.toInt()).let { if (it.bitLength() < 63) it.toLong() else it })
        }
        val x = Py.double(a)
        val y = Py.double(b)
        if (x == 0.0 && y < 0) throw err("can't divide by zero")
        if (x < 0 && y != Math.floor(y)) throw err("that power has no answer in plain numbers")
        val value = StrictMath.pow(x, y)
        if (!value.isFinite()) throw tooBig()
        return number(value)
    }

    private fun unop(op: String, a: Any?): Any? {
        if (op == "not") return !Py.truth(a)
        if (!Py.isNum(a)) throw err("can't use $op on ${Py.kindWords(a)}")
        if (op == "-") return number(if (a is Double) -a else exact { Math.negateExact(Py.long(a)) })
        return number(if (a is Double) a else Py.long(a))
    }

    private fun big(value: Any?) {
        if (value is ArrayList<*> || value is Tup || value is Map<*, *>) measure(value)
    }

    private fun compare(op: String, a: Any?, b: Any?): Boolean {
        if (op == "is") return a == null && b == null
        if (op == "is not") return !(a == null && b == null)
        big(a)
        big(b)
        try {
            when (op) {
                "==" -> return Py.eq(a, b)
                "!=" -> return !Py.eq(a, b)
                "<" -> return Py.order(a, b) < 0
                "<=" -> return Py.order(a, b) <= 0
                ">" -> return Py.order(a, b) > 0
                ">=" -> return Py.order(a, b) >= 0
                "in", "not in" -> {
                    val found = when (b) {
                        is String -> {
                            if (a !is String) throw err("can't look for ${Py.kindWords(a)} in text")
                            b.contains(a)
                        }
                        is ArrayList<*> -> b.any { Py.eq(it, a) }
                        is Tup -> b.items.any { Py.eq(it, a) }
                        is PyRange -> when {
                            Py.isWhole(a) -> b.has(Py.long(a))
                            a is Double -> a == Math.floor(a) && Math.abs(a) < 9.2e18 && b.has(a.toLong())
                            else -> false
                        }
                        is Map<*, *> -> (a is String || a is Long || a is Boolean) && b.containsKey(Py.key(a))
                        else -> throw err("can't look inside ${Py.kindWords(b)}")
                    }
                    return if (op == "in") found else !found
                }
            }
        } catch (e: Incomparable) {
            throw err("can't compare ${Py.kindWords(a)} with ${Py.kindWords(b)}")
        }
        throw err("$op is not allowed")
    }

    @Suppress("UNCHECKED_CAST")
    private fun getItem(obj: Any?, index: Any?): Any? {
        if (obj is ArrayList<*> || obj is Tup || obj is String || obj is PyRange) {
            if (!Py.isWhole(index)) throw err("a position in ${Py.kindWords(obj)} must be a whole number")
            val n = Py.length(obj)
            val i = Py.long(index)
            if (i < -n || i >= n) throw err("position ${Py.repr(index)} is past the end of ${Py.kindWords(obj)} of $n")
            val at = if (i < 0) i + n else i
            return when (obj) {
                is ArrayList<*> -> obj[at.toInt()]
                is Tup -> obj.items[at.toInt()]
                is PyRange -> obj.at(at)
                else -> {
                    val s = obj as String
                    if (s.length == Py.textLength(s)) s.substring(at.toInt(), at.toInt() + 1) else Py.fromPoints(Py.points(s), at.toInt(), 1)
                }
            }
        }
        if (obj is Map<*, *>) {
            if (!(index is String || index is Long)) throw err("a dict's keys are text or whole numbers")
            if (!obj.containsKey(index)) throw err("${Py.short(index)} is not in the dict; use .get() to allow for that")
            return obj[index]
        }
        throw err("can't take an item from ${Py.kindWords(obj)}")
    }

    private fun slice(obj: Any?, lo: Any?, hi: Any?, step: Any?): Any? {
        for (part in listOf(lo, hi, step)) {
            if (part != null && !Py.isWhole(part)) throw err("a slice takes whole numbers")
        }
        if (step != null && Py.long(step) == 0L) throw err("a slice's step can't be zero")
        if (!(obj is ArrayList<*> || obj is Tup || obj is String)) throw err("can't slice ${Py.kindWords(obj)}")
        val by = if (step == null) 1L else Py.long(step)
        val n = Py.length(obj)
        val (start, count) = Py.sliceIndices(n, lo?.let { Py.long(it) }, hi?.let { Py.long(it) }, by).let { it[0] to it[1] }
        val picked = ArrayList<Int>()
        for (k in 0 until count) picked.add((start + k * by).toInt())
        return when (obj) {
            is ArrayList<*> -> ArrayList<Any?>(picked.map { obj[it] })
            is Tup -> Tup(picked.map { obj.items[it] })
            else -> {
                val points = Py.points(obj as String)
                val out = IntArray(picked.size) { points[picked[it]] }
                Py.fromPoints(out)
            }
        }
    }

    private fun fstr(parts: List<Any>): String {
        val out = StringBuilder()
        var size = 0L
        for (part in parts) {
            val piece = if (part is String) part else show(lookup((part as FName).n))
            size += Py.textLength(piece)
            if (size > limits.text) throw textLimit()
            out.append(piece)
        }
        return out.toString()
    }

    private fun show(value: Any?): String {
        if (value is String) return value
        big(value)
        val out = StringBuilder()
        showInto(value, out, longArrayOf(0L), true)
        return out.toString()
    }

    private fun showInto(value: Any?, out: StringBuilder, size: LongArray, top: Boolean = false) {
        val piece: String = when (value) {
            is String -> if (top) value else Py.textRepr(value)
            null, is Boolean, is Long, is Double -> Py.repr(value)
            is PyRange -> value.repr()
            is ArrayList<*> -> {
                add(out, size, "[")
                value.forEachIndexed { index, item ->
                    if (index > 0) add(out, size, ", ")
                    showInto(item, out, size)
                }
                add(out, size, "]")
                return
            }
            is Tup -> {
                add(out, size, "(")
                value.items.forEachIndexed { index, item ->
                    if (index > 0) add(out, size, ", ")
                    showInto(item, out, size)
                }
                add(out, size, if (value.items.size == 1) ",)" else ")")
                return
            }
            is Map<*, *> -> {
                add(out, size, "{")
                var index = 0
                for ((k, item) in value) {
                    if (index++ > 0) add(out, size, ", ")
                    showInto(k, out, size)
                    add(out, size, ": ")
                    showInto(item, out, size)
                }
                add(out, size, "}")
                return
            }
            else -> "?"
        }
        add(out, size, piece)
    }

    private fun add(out: StringBuilder, size: LongArray, piece: String) {
        size[0] += Py.textLength(piece)
        if (size[0] > limits.text) throw textLimit()
        out.append(piece)
    }

    private fun builtin(name: String, args: List<Any?>, kw: Map<String, Any?>): Any? {
        when (name) {
            "len" -> {
                arity(name, args, 1, 1)
                val value = args[0]
                if (value is String || value is ArrayList<*> || value is Tup || value is Map<*, *> || value is PyRange) return Py.length(value)
                throw err("${Py.kindWords(value)} has no length")
            }
            "min", "max" -> {
                if (args.isEmpty()) throw err("$name() needs something to look at")
                val items = if (args.size == 1) itemsOf(args[0]) else ArrayList(args)
                if (items.isEmpty()) throw err("$name() of nothing")
                for (item in items) big(item)
                try {
                    var best = items[0]
                    for (i in 1 until items.size) {
                        val c = Py.order(items[i], best)
                        if (if (name == "min") c < 0 else c > 0) best = items[i]
                    }
                    return best
                } catch (e: Incomparable) {
                    throw err("$name() can't compare those")
                }
            }
            "abs" -> {
                arity(name, args, 1, 1)
                val value = args[0]
                if (!Py.isNum(value)) throw err("abs() of ${Py.kindWords(value)}")
                return number(if (value is Double) Math.abs(value) else Math.abs(Py.long(value)))
            }
            "round" -> {
                arity(name, args, 1, 2)
                val digits = if (args.size > 1) args[1] else kw["ndigits"]
                val value = args[0]
                if (!Py.isNum(value) || (digits != null && !Py.isWhole(digits))) throw err("round() takes a number and a whole number of places")
                if (digits != null && Math.abs(Py.long(digits)) > 15) throw err("round() to at most 15 places")
                if (digits == null) {
                    if (value is Double) {
                        val r = Math.rint(value)
                        if (Math.abs(r) >= 9.2e18) throw tooBig()
                        return number(r.toLong())
                    }
                    return number(Py.long(value))
                }
                val places = Py.long(digits).toInt()
                return if (value is Double) number(Py.roundTo(value, places)) else number(Py.roundWhole(Py.long(value), places))
            }
            "int" -> {
                arity(name, args, 1, 1)
                val value = args[0]
                if (value is String) {
                    val parsed = Py.parseWhole(Py.strip(value, null)) ?: throw err("${Py.short(value)} is not a whole number")
                    return number(if (parsed.bitLength() < 63) parsed.toLong() else parsed)
                }
                if (Py.isNum(value)) {
                    if (value is Double) {
                        if (Math.abs(value) >= 9.2e18) throw tooBig()
                        return number(value.toLong())
                    }
                    return number(Py.long(value))
                }
                throw err("int() of ${Py.kindWords(value)}")
            }
            "float" -> {
                arity(name, args, 1, 1)
                val value = args[0]
                if (value is String) {
                    val out = Py.parseFloat(Py.strip(value, null)) ?: throw err("${Py.short(value)} is not a number")
                    if (!out.isFinite()) throw err("${Py.short(value)} is not a number")
                    return out
                }
                if (Py.isNum(value)) return number(Py.double(value))
                throw err("float() of ${Py.kindWords(value)}")
            }
            "str" -> {
                arity(name, args, 0, 1)
                return if (args.isNotEmpty()) show(args[0]) else ""
            }
            "range" -> {
                arity(name, args, 1, 3)
                if (!args.all { Py.isWhole(it) }) throw err("range() takes whole numbers")
                val parts = args.map { Py.long(it) }
                if (parts.size == 3 && parts[2] == 0L) throw err("range()'s step can't be zero")
                return if (parts.size == 1) PyRange(0L, parts[0], 1L) else PyRange(parts[0], parts[1], if (parts.size > 2) parts[2] else 1L)
            }
            "sorted" -> {
                arity(name, args, 1, 1)
                val items = itemsOf(args[0])
                for (item in items) big(item)
                val reverse = Py.truth(kw["reverse"] ?: false)
                try {
                    if (reverse) items.reverse()
                    val sorted = insertionSort(items)
                    if (reverse) sorted.reverse()
                    return made(sorted)
                } catch (e: Incomparable) {
                    throw err("sorted() can't compare those")
                }
            }
            "sum" -> {
                arity(name, args, 1, 1)
                var total: Any? = 0L
                for (item in itemsOf(args[0])) {
                    if (!Py.isNum(item)) throw err("sum() of ${Py.kindWords(item)}")
                    total = binop("+", total, item)
                }
                return total
            }
            "any", "all" -> {
                arity(name, args, 1, 1)
                val items = itemsOf(args[0])
                return if (name == "any") items.any { Py.truth(it) } else items.all { Py.truth(it) }
            }
            "enumerate" -> {
                arity(name, args, 1, 1)
                val start = if (kw.containsKey("start")) kw["start"] else 0L
                if (!Py.isWhole(start)) throw err("enumerate()'s start is a whole number")
                val first = Py.long(start)
                val out = ArrayList<Any?>()
                itemsOf(args[0]).forEachIndexed { i, item -> out.add(Tup(listOf(first + i, item))) }
                return made(out)
            }
            "zip" -> {
                if (args.isEmpty()) return ArrayList<Any?>()
                val lists = args.map { itemsOf(it) }
                val n = lists.minOf { it.size }
                val out = ArrayList<Any?>()
                for (i in 0 until n) out.add(Tup(lists.map { it[i] }))
                return made(out)
            }
        }
        throw err("'$name' is not a function you can use")
    }

    private fun insertionSort(items: List<Any?>): ArrayList<Any?> {
        val out = ArrayList<Any?>(items.size)
        for (pivot in items) {
            var lo = 0
            var hi = out.size
            while (lo < hi) {
                val mid = (lo + hi) ushr 1
                if (Py.order(pivot, out[mid]) < 0) hi = mid else lo = mid + 1
            }
            out.add(lo, pivot)
        }
        return out
    }

    @Suppress("UNCHECKED_CAST")
    private fun method(obj: Any?, name: String, args: List<Any?>): Any? = when (obj) {
        is ArrayList<*> -> listMethod(obj as ArrayList<Any?>, name, args)
        is Map<*, *> -> dictMethod(obj, name, args)
        is String -> textMethod(obj, name, args)
        else -> throw err("${Py.kindWords(obj)} has no .$name()")
    }

    private fun listMethod(obj: ArrayList<Any?>, name: String, args: List<Any?>): Any? {
        when (name) {
            "append" -> {
                arity(name, args, 1, 1)
                if (obj.size + 1L > limits.items) throw itemsLimit()
                holds(obj, args[0])
                obj.add(args[0])
                return null
            }
            "pop" -> {
                arity(name, args, 0, 1)
                if (obj.isEmpty()) throw err("can't pop from an empty list")
                val index = if (args.isNotEmpty()) args[0] else -1L
                if (!Py.isWhole(index) || Py.long(index) < -obj.size || Py.long(index) >= obj.size) throw err("position ${Py.repr(index)} is past the end of a list of ${obj.size}")
                val i = Py.long(index)
                return obj.removeAt((if (i < 0) i + obj.size else i).toInt())
            }
            "insert" -> {
                arity(name, args, 2, 2)
                if (!Py.isWhole(args[0])) throw err("insert() takes a whole-number position")
                if (obj.size + 1L > limits.items) throw itemsLimit()
                holds(obj, args[1])
                var at = Py.long(args[0])
                if (at < 0) {
                    at += obj.size
                    if (at < 0) at = 0
                }
                if (at > obj.size) at = obj.size.toLong()
                obj.add(at.toInt(), args[1])
                return null
            }
            "remove", "index", "count" -> {
                arity(name, args, 1, 1)
                big(args[0])
                if (name == "count") return obj.count { Py.eq(it, args[0]) }.toLong()
                val at = obj.indexOfFirst { Py.eq(it, args[0]) }
                if (at < 0) throw err("${Py.short(args[0])} is not in the list")
                if (name == "index") return at.toLong()
                obj.removeAt(at)
                return null
            }
        }
        throw err("a list has no .$name()")
    }

    private fun dictMethod(obj: Map<*, *>, name: String, args: List<Any?>): Any? {
        when (name) {
            "get" -> {
                arity(name, args, 1, 2)
                val k = args[0]
                val fallback = if (args.size > 1) args[1] else null
                if (!(k is String || k is Long)) return fallback
                return if (obj.containsKey(k)) obj[k] else fallback
            }
            "keys" -> {
                arity(name, args, 0, 0)
                return ArrayList<Any?>(obj.keys)
            }
            "values" -> {
                arity(name, args, 0, 0)
                return ArrayList<Any?>(obj.values)
            }
            "items" -> {
                arity(name, args, 0, 0)
                return ArrayList<Any?>(obj.entries.map { Tup(listOf(it.key, it.value)) })
            }
        }
        throw err("a dict has no .$name()")
    }

    private fun textMethod(obj: String, name: String, args: List<Any?>): Any? {
        when (name) {
            "lower", "upper" -> {
                arity(name, args, 0, 0)
                return text(if (name == "lower") obj.lowercase(java.util.Locale.ROOT) else obj.uppercase(java.util.Locale.ROOT))
            }
            "strip" -> {
                arity(name, args, 0, 1)
                if (args.isNotEmpty() && args[0] !is String) throw err("strip() takes text")
                return Py.strip(obj, args.getOrNull(0) as String?)
            }
            "split" -> {
                arity(name, args, 0, 2)
                val sep = if (args.isNotEmpty()) args[0] else null
                if (sep != null && (sep !is String || sep.isEmpty())) throw err("split() takes some text to split on")
                val most = if (args.size > 1) args[1] else -1L
                if (!Py.isWhole(most)) throw err("split()'s second argument is a whole number")
                val parts = if (sep == null) Py.splitSpace(obj, Py.long(most)) else Py.splitOn(obj, sep as String, Py.long(most))
                count(parts.size.toLong())
                return parts
            }
            "join" -> {
                arity(name, args, 1, 1)
                val items = itemsOf(args[0])
                if (!items.all { it is String }) throw err("join() takes a list of text")
                val total = items.sumOf { Py.textLength(it as String).toLong() } + Py.textLength(obj).toLong() * maxOf(0, items.size - 1)
                if (total > limits.text) throw textLimit()
                return items.joinToString(obj) { it as String }
            }
            "startswith", "endswith" -> {
                arity(name, args, 1, 1)
                val part = args[0] as? String ?: throw err("$name() takes text")
                return if (name == "startswith") obj.startsWith(part) else obj.endsWith(part)
            }
            "replace" -> {
                arity(name, args, 2, 3)
                val old = args[0]
                val new = args[1]
                if (old !is String || new !is String) throw err("replace() takes text")
                val most = if (args.size > 2) args[2] else -1L
                if (!Py.isWhole(most)) throw err("replace()'s third argument is a whole number")
                val limit = Py.long(most)
                var times = Py.countText(obj, old)
                if (limit >= 0) times = minOf(times, limit)
                if (Py.textLength(obj) + times * (Py.textLength(new) - Py.textLength(old)) > limits.text) throw textLimit()
                return Py.replace(obj, old, new, limit)
            }
        }
        throw err("text has no .$name()")
    }

    private fun arity(name: String, args: List<Any?>, least: Int, most: Int) {
        if (args.size < least) throw err("$name() needs $least argument${if (least != 1) "s" else ""}")
        if (args.size > most) throw err("$name() takes at most $most argument${if (most != 1) "s" else ""}")
    }

    private fun err(text: String): Fail = Fail("error", "", text)

    private fun limit(what: String, text: String): Fail = Fail("limit", what, text)

    companion object {
        const val SCALAR = 8L
        const val CHECK_TIME_EVERY = 255L
        const val CHECK_SIZE_EVERY = 1023L
        val BREAK = Any()
        val CONTINUE = Any()
        private val NOTHING = Any()

        fun nothing(): Any = NOTHING
    }
}

class Run(private val machine: Machine, private val body: (suspend SequenceScope<Call>.() -> Any?)?) {
    private var calls: Iterator<Call>? = null
    private var started = false
    private var over = false
    private var outcome: Outcome? = null
    private var result: Any? = null

    fun go(): Outcome = go(Machine.nothing())

    fun go(reply: Any?): Outcome {
        outcome?.let { if (over) return it }
        try {
            val iterator: Iterator<Call>
            if (!started) {
                started = true
                machine.steps = 0
                machine.since = machine.now()
                val work = body ?: return end(Done(null))
                iterator = sequence<Call> { result = work() }.iterator()
                calls = iterator
            } else {
                iterator = calls ?: return end(Done(null))
                val value = machine.accept(if (reply === Machine.nothing()) null else reply)
                machine.reply = value
                machine.since = machine.now()
            }
            if (!iterator.hasNext()) {
                try {
                    machine.checkAll()
                } catch (fail: Fail) {
                    return end(Crash(fail.kind, fail.what, machine.line, fail.text))
                }
                return end(Done(result))
            }
            val out = iterator.next()
            machine.checkAll()
            return out
        } catch (fail: Fail) {
            return end(Crash(fail.kind, fail.what, machine.line, fail.text))
        } catch (finishing: Finishing) {
            return end(Finish)
        } catch (deep: StackOverflowError) {
            return end(Crash("limit", "recursion", machine.line, "it went too deep"))
        } catch (full: OutOfMemoryError) {
            return end(Crash("limit", "size", machine.line, "it used too much memory"))
        } catch (error: Exception) {
            return end(Crash("error", "", machine.line, "something went wrong (${error.javaClass.simpleName})"))
        }
    }

    private fun end(result: Outcome): Outcome {
        over = true
        outcome = result
        machine.clear()
        calls = null
        return result
    }

    fun stop() {
        if (!over) end(Finish)
    }

    val finished: Boolean
        get() = over
}
