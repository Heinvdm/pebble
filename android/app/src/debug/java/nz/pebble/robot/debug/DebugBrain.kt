package nz.pebble.robot.debug

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import com.chaquo.python.Kwarg
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import nz.pebble.robot.brain.BrainService
import nz.pebble.robot.eyes.Eyes
import nz.pebble.robot.eyes.Motion
import nz.pebble.robot.recall.Pooling
import nz.pebble.robot.recall.SentenceModel
import nz.pebble.robot.recall.WordPiece
import kotlin.concurrent.thread
import org.json.JSONObject

class DebugBrain : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val bridge = BrainService.bridge
        if (bridge == null) {
            Log.i(TAG, "no brain running in this process")
            return
        }
        val pending = goAsync()
        thread {
            pending.finish()
            try {
                when (intent.action) {
                    "nz.pebble.robot.debug.SENSES" -> {
                        bridge.sensorTap(true)
                        Thread.sleep(3_000)
                        Log.i(TAG, "battery " + bridge.battery())
                        Log.i(TAG, "temperature " + bridge.temperature() + " light " + bridge.light() + " proximity " + bridge.proximity() + " pressure " + bridge.pressure())
                        Log.i(TAG, "motion " + bridge.motion())
                        Log.i(TAG, "sensors " + bridge.sensorInfo())
                        val accel = org.json.JSONObject(bridge.sensorRead("accel", 0, 10_000))
                        Log.i(TAG, "accel rows " + accel.getJSONArray("rows").length() + " total " + accel.getLong("total") + " now_ms " + accel.getDouble("now_ms"))
                        Log.i(TAG, "pressure " + bridge.sensorRead("pressure", 0, 3))
                        Log.i(TAG, "keys " + bridge.keyInfo())
                        Log.i(TAG, "hearing " + bridge.hearingInfo())
                        Log.i(TAG, "heat " + bridge.phoneHeat())
                        Log.i(TAG, "eyes pace " + (org.json.JSONObject(bridge.eyesStatus()).opt("pace") ?: "no eyes") + " fps " + org.json.JSONObject(bridge.eyesStatus()).opt("fps"))
                    }
                    "nz.pebble.robot.debug.ALARM" -> {
                        Log.i(TAG, "siren on: " + bridge.alarmSound(true))
                        Thread.sleep(1_500)
                        Log.i(TAG, "siren off: " + bridge.alarmSound(false))
                        Log.i(TAG, "alarm words: " + bridge.alarmSay("This is a test of Pebble's alarm."))
                    }
                    "nz.pebble.robot.debug.SAY" -> Log.i(TAG, "spoke: " + bridge.speak(intent.getStringExtra("text") ?: "Hello, I am Pebble.", false))
                    "nz.pebble.robot.debug.HEAR" -> {
                        val speech = BrainService.speech
                        intent.getStringExtra("config")?.let { bridge.speechConfig(it) }
                        val reply = intent.getStringExtra("reply")
                        val nameEnd = intent.getStringExtra("name_end_s")?.toDoubleOrNull()
                        speech?.listener = { e ->
                            val kind = e.optString("kind")
                            val shown = JSONObject(e.toString())
                            if (shown.has("print") && !shown.isNull("print")) shown.put("print", "[" + shown.getJSONArray("print").length() + " floats]")
                            Log.i(TAG, "event $shown")
                            val ended = speech?.state()?.optDouble("test_speech_ended_at") ?: 0.0
                            if (kind == "voice_end" && ended > 0) Log.i(TAG, "latency voice_end: " + Math.round((e.optDouble("t") - ended) * 1000) + " ms after the real end of speech (segment end " + Math.round((e.optDouble("end") - ended) * 1000) + " ms)")
                            if (kind == "final" && ended > 0) {
                                Log.i(TAG, "latency final: " + Math.round((e.optDouble("t") - ended) * 1000) + " ms after the real end of speech")
                                if (reply != null) bridge.sayPart("reply-" + e.optInt("segment"), reply, true, false)
                            }
                            if (kind == "spoken" && e.optString("state") == "start" && ended > 0) Log.i(TAG, "latency first sound: " + Math.round((e.optDouble("t") - ended) * 1000) + " ms after the real end of speech")
                            if (kind == "spoken" && e.optString("state") == "stopped") Log.i(TAG, "stop took " + e.optDouble("stop_ms") + " ms, " + e.optInt("chars") + " characters spoken")
                            val loop = speech?.state()?.optDouble("test_loop_started_at") ?: 0.0
                            if (kind == "keyword" && nameEnd != null && loop > 0) Log.i(TAG, "latency keyword: " + Math.round((e.optDouble("t") - (loop + nameEnd)) * 1000) + " ms after the name ended (flushed " + e.optBoolean("flushed") + ", its own estimate " + Math.round((e.optDouble("t") - e.optDouble("end")) * 1000) + " ms)")
                        }
                        Log.i(TAG, "listening probe on: " + bridge.earsState())
                    }
                    "nz.pebble.robot.debug.BARGE" -> {
                        bridge.sayPart("long-1", intent.getStringExtra("text") ?: "This is a long sentence that Pebble says so that it can be cut off in the middle, to measure how fast speech stops.", true, false)
                        Thread.sleep(intent.getIntExtra("after_ms", 1200).toLong())
                        Log.i(TAG, "stop call returned in " + bridge.stopSpeaking() + " ms")
                    }
                    "nz.pebble.robot.debug.SNAP" -> {
                        val started = System.nanoTime()
                        val jpeg = bridge.eyesSnapshot(intent.getStringExtra("camera") ?: "", intent.getIntExtra("max_side", 768), 1.0)
                        val ms = (System.nanoTime() - started) / 1e6
                        val head = if (jpeg.size >= 3) String.format("%02x%02x%02x", jpeg[0], jpeg[1], jpeg[2]) else "none"
                        Log.i(TAG, "snapshot: ${jpeg.size} bytes, starts $head, made in ${Math.round(ms)} ms")
                    }
                    "nz.pebble.robot.debug.ECHO" -> {
                        val speech = BrainService.speech
                        val lines = listOf(
                            "Hello, I am Pebble, and I like to roll around the living room.",
                            "Today I saw a cat, a ball and a slipper under the couch.",
                            "Would you like me to come over and say hello to you?",
                            "I think it is nearly time for me to go back to my dock.",
                            "Thank you for talking to me, it makes my day much better.",
                        )
                        var opened = 0
                        var heardWords = 0
                        var finals = 0
                        speech?.listener = { e ->
                            if (e.optBoolean("pebble_speaking")) {
                                when (e.optString("kind")) {
                                    "voice_start" -> opened++
                                    "final" -> {
                                        finals++
                                        heardWords += e.optString("text").split(" ").count { it.isNotBlank() }
                                    }
                                }
                            }
                        }
                        lines.forEachIndexed { i, line -> bridge.sayPart("echo-$i", line, i == lines.lastIndex, false) }
                        Thread.sleep(intent.getIntExtra("seconds", 25) * 1000L)
                        speech?.listener = null
                        Log.i(TAG, "echo test: ${lines.size} sentences spoken; the voice detector opened $opened times while Pebble spoke; $finals finals with $heardWords words heard from Pebble's own voice; " + bridge.earsState())
                    }
                    "nz.pebble.robot.debug.MOUTHS" -> {
                        if (!org.opencv.android.OpenCVLoader.initLocal()) throw IllegalStateException("OpenCV did not load")
                        val files = nz.pebble.robot.eyes.ModelFiles(context)
                        val faces = nz.pebble.robot.eyes.CvFaces(files.path("face_detection_yunet_2023mar.onnx"))
                        val reader = nz.pebble.robot.eyes.MouthReader(files.path(nz.pebble.robot.eyes.Mouth.MODEL))
                        val root = java.io.File(context.filesDir, intent.getStringExtra("folder") ?: "mouths")
                        var took = 0.0
                        var reads = 0
                        for (kind in root.listFiles()?.filter { it.isDirectory }?.sortedBy { it.name } ?: emptyList()) {
                            for (picture in kind.listFiles()?.filter { it.name.endsWith(".jpg") }?.sortedBy { it.name } ?: emptyList()) {
                                val image = org.opencv.imgcodecs.Imgcodecs.imread(picture.path)
                                val found = faces.find(image).maxByOrNull { it.w * it.h }
                                val marks = found?.marks
                                val shape = if (marks == null) null else {
                                    val started = System.nanoTime()
                                    val got = reader.read(image, nz.pebble.robot.eyes.Mouth.pixels(marks, image.cols(), image.rows()))
                                    took += (System.nanoTime() - started) / 1e6
                                    reads++
                                    got
                                }
                                Log.i(TAG, "mouth ${kind.name}/${picture.name} " + (shape?.joinToString(" ") { String.format(java.util.Locale.ROOT, "%.6f", it) } ?: "none"))
                                image.release()
                            }
                        }
                        Log.i(TAG, "mouths read: $reads, " + String.format(java.util.Locale.ROOT, "%.1f", if (reads > 0) took / reads else 0.0) + " ms each")
                        if (intent.getBooleanExtra("live", false)) {
                            bridge.eyesMouths(true, 0.0)
                            Thread.sleep(intent.getIntExtra("seconds", 5) * 1000L)
                            Log.i(TAG, "live: " + org.json.JSONObject(bridge.eyesStatus()).optJSONObject("speaking"))
                            bridge.eyesMouths(false, 0.0)
                            Thread.sleep(2_000)
                            Log.i(TAG, "after: " + org.json.JSONObject(bridge.eyesStatus()).optJSONObject("speaking"))
                        }
                    }
                    "nz.pebble.robot.debug.VECTORS" -> vectors(bridge, intent)
                    "nz.pebble.robot.debug.RECALL" -> recall(context, bridge, intent)
                    "nz.pebble.robot.debug.CLOSEUP" -> closeUp(context, bridge, intent)
                    "nz.pebble.robot.debug.TORCH" -> torch(bridge, intent)
                    "nz.pebble.robot.debug.HIGHBAND" -> highBand(bridge, intent)
                    "nz.pebble.robot.debug.MICPROBE" -> micProbe(bridge, intent)
                    "nz.pebble.robot.debug.SCORES" -> scores(context, bridge, intent)
                    "nz.pebble.robot.debug.FLOOR" -> floor(bridge, intent)
                    "nz.pebble.robot.debug.MOTION" -> motion(context, bridge, intent)
                    "nz.pebble.robot.debug.DEPTH" -> depth(context, intent)
                    "nz.pebble.robot.debug.EARS" -> {
                        val speech = BrainService.speech
                        Log.i(TAG, "ears before: " + JSONObject(bridge.hearingInfo()).optJSONObject("engine"))
                        if (intent.getBooleanExtra("end", false)) {
                            val nth = intent.getIntExtra("during_voice", 0)
                            if (nth > 0 && speech != null) {
                                val heard = java.util.concurrent.CountDownLatch(nth)
                                val before = speech.listener
                                speech.listener = { e ->
                                    before?.invoke(e)
                                    if (e.optString("kind") == "voice_start") heard.countDown()
                                }
                                heard.await(60, java.util.concurrent.TimeUnit.SECONDS)
                                Thread.sleep(intent.getIntExtra("after_ms", 300).toLong())
                                speech.listener = before
                            }
                            speech?.endEarsForTest()
                            Log.i(TAG, "asked the ears process to end")
                        }
                        Thread.sleep(intent.getIntExtra("seconds", 15) * 1000L)
                        Log.i(TAG, "ears after: " + JSONObject(bridge.hearingInfo()).let { it.optString("speech_engine") + " " + it.optJSONObject("engine") })
                    }
                    "nz.pebble.robot.debug.TAP" -> {
                        bridge.soundTap(true)
                        Thread.sleep(3_000)
                        Log.i(TAG, "sound tap " + bridge.soundInfo())
                        Log.i(TAG, "sound bytes " + bridge.soundRead(0, 16_000).size)
                        val scores = org.json.JSONObject(bridge.soundScores(0))
                        val rows = scores.getJSONArray("rows")
                        val top = if (rows.length() > 0) rows.getJSONArray(rows.length() - 1).getJSONArray(1).let { s -> (0 until s.length()).maxByOrNull { s.getDouble(it) } } else null
                        Log.i(TAG, "sound scores rows " + rows.length() + " total " + scores.getLong("total") + " ms " + scores.optDouble("ms") + " top class " + top + " problem " + scores.optString("problem"))
                        bridge.soundTap(false)
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "${intent.action} failed", e)
            }
        }
    }

    private fun withTap(bridge: nz.pebble.robot.brain.Bridge, block: () -> Unit) {
        val was = JSONObject(bridge.soundInfo()).optBoolean("wanted")
        if (!was) bridge.soundTap(true)
        try {
            block()
        } finally {
            if (!was) bridge.soundTap(false)
        }
    }

    private fun vectors(bridge: nz.pebble.robot.brain.Bridge, intent: Intent) = withTap(bridge) {
        val py = Python.getInstance()
        val labels = py.builtins.callAttr("list", py.builtins.callAttr("range", 521))
        val model = py.getModule("pebble.hearing.events").callAttr("BridgeModel", labels, bridge)
        model.put("want_vectors", true)
        val first = model.callAttr("take_vectors").asList()
        val after = JSONObject(bridge.soundVectors(1L shl 62))
        Log.i(TAG, "vectors: the first read gave ${first.size} rows; the phone now keeps them: total ${after.optLong("total")}, kept ${after.optInt("kept")}, problem [${after.optString("problem")}]")
        Thread.sleep(intent.getIntExtra("seconds", 6) * 1000L)
        val rows = model.callAttr("take_vectors").asList()
        val mono = py.getModule("time").callAttr("monotonic").toDouble()
        for ((i, row) in rows.withIndex()) {
            val values = row.asList()[1].asList().map { it.toDouble() }
            val norm = Math.sqrt(values.sumOf { it * it })
            if (i < 3 || i == rows.size - 1) Log.i(TAG, "vector $i: ${values.size} numbers, length ${String.format(java.util.Locale.ROOT, "%.3f", norm)}, ${String.format(java.util.Locale.ROOT, "%.2f", mono - row.asList()[0].toDouble())} s old, first ${values.take(3).map { String.format(java.util.Locale.ROOT, "%.4f", it) }}")
        }
        Log.i(TAG, "vectors: ${rows.size} rows in ${intent.getIntExtra("seconds", 6)} s through the brain's own reader; status " + model.callAttr("status"))
        val idle = intent.getIntExtra("idle_s", 0)
        if (idle > 0) {
            Thread.sleep(idle * 1000L)
            Log.i(TAG, "vectors after $idle s without asking: kept " + JSONObject(bridge.soundVectors(1L shl 62)).optInt("kept"))
        }
    }

    private fun recall(context: Context, bridge: nz.pebble.robot.brain.Bridge, intent: Intent) {
        val sentences = BrainService.sentences
        if (intent.getBooleanExtra("bench", false)) {
            if (sentences == null) {
                Log.i(TAG, "recall: no sentence model in this process")
                return
            }
            val measure: (PyObject?) -> Unit = {
                Log.i(TAG, "recall bench started: " + sentences.measure(intent.getBooleanExtra("settle", true)) + ", ears " + bridge.earsState())
                val until = System.nanoTime() + intent.getIntExtra("wait_s", 600) * 1_000_000_000L
                while (sentences.measuringNow() && System.nanoTime() < until) Thread.sleep(500)
                Log.i(TAG, "recall bench: " + sentences.choiceJson())
            }
            if (intent.getBooleanExtra("eyes", false)) withEyes(bridge, intent, measure) else measure(null)
            return
        }
        val file = java.io.File(context.getExternalFilesDir(null), intent.getStringExtra("file") ?: "recall_cases.json")
        val fixture = JSONObject(file.readText())
        if (intent.getBooleanExtra("gate", false)) {
            val watch = nz.pebble.robot.llm.LlamaWatch()
            Log.i(TAG, "recall gate: a language model is writing now: ${watch.writing()}; heat ${bridge.phoneHeat()}")
            val all = fixture.getJSONArray("groups").let { it.getJSONObject(it.length() - 3).getJSONArray("texts") }
            fun one(label: String, texts: List<String>, query: Boolean) {
                val started = System.nanoTime()
                val bytes = bridge.recallEmbed(org.json.JSONArray(texts).toString(), query)
                Log.i(TAG, "recall gate: $label ${if (bytes.isEmpty()) "was refused" else "was answered"} after ${Math.round((System.nanoTime() - started) / 1e6)} ms; a language model is writing now: ${watch.writing()}")
            }
            one("a question", listOf("When is Sam's football game?"), true)
            one("a batch of 8 notes", List(8) { all.getString(it) }, false)
            Log.i(TAG, "recall gate info " + bridge.recallInfo())
            return
        }
        if (intent.getBooleanExtra("preempt", false)) {
            val all = fixture.getJSONArray("groups").let { it.getJSONObject(it.length() - 3).getJSONArray("texts") }
            val long = List(32) { (all.getString(it % all.length()) + " ").repeat(8).trim() }
            val after = intent.getIntExtra("after_ms", 300).toLong()
            var batchMs = 0.0
            var answered = false
            val batch = thread {
                val started = System.nanoTime()
                answered = bridge.recallEmbed(org.json.JSONArray(long).toString(), false).isNotEmpty()
                batchMs = (System.nanoTime() - started) / 1e6
            }
            Thread.sleep(after)
            val started = System.nanoTime()
            val asked = intent.getBooleanExtra("ask", true) && bridge.recallEmbed(org.json.JSONArray(listOf("When is Sam's football game?")).toString(), true).isNotEmpty()
            val askedMs = (System.nanoTime() - started) / 1e6
            batch.join(120_000)
            val alone = System.nanoTime()
            bridge.recallEmbed(org.json.JSONArray(long).toString(), false)
            val aloneMs = (System.nanoTime() - alone) / 1e6
            val question = if (intent.getBooleanExtra("ask", true)) "a question asked $after ms into it was ${if (asked) "answered" else "refused"} in ${Math.round(askedMs)} ms" else "no question asked"
            Log.i(TAG, "recall preempt: a batch of 32 long memories; $question; the batch was ${if (answered) "answered" else "refused"} after ${Math.round(batchMs)} ms (${Math.round(aloneMs)} ms on its own); gave way ${JSONObject(bridge.recallInfo()).optLong("gave_way")} times")
            return
        }
        val prefix = fixture.getString("prefix")
        val words = WordPiece.load(context.assets.open(SentenceModel.VOCAB_ASSET).bufferedReader(Charsets.UTF_8).use { it.readText() })
        val tokens = fixture.getJSONArray("tokens")
        var wrong = 0
        for (i in 0 until tokens.length()) {
            val case = tokens.getJSONObject(i)
            val want = case.getJSONArray("ids").let { a -> IntArray(a.length()) { a.getInt(it) } }
            val got = words.ids(if (case.getBoolean("query")) prefix + case.getString("text") else case.getString("text"))
            if (!want.contentEquals(got)) {
                wrong++
                Log.i(TAG, "recall tokens differ for ${JSONObject.quote(case.getString("text"))}: PC ${want.toList()}, phone ${got.toList()}")
            }
        }
        Log.i(TAG, "recall tokens: ${tokens.length() - wrong} of ${tokens.length()} lines give the PC's ids")
        val groups = fixture.getJSONArray("groups")
        var worst = 1.0
        var worstText = ""
        var lines = 0
        for (i in 0 until groups.length()) {
            val group = groups.getJSONObject(i)
            val texts = group.getJSONArray("texts")
            val query = group.getBoolean("query")
            val started = System.nanoTime()
            val bytes = bridge.recallEmbed(texts.toString(), query)
            val ms = (System.nanoTime() - started) / 1e6
            if (bytes.isEmpty()) {
                Log.i(TAG, "recall group $i was refused: " + bridge.recallInfo())
                continue
            }
            val got = Pooling.unpack(bytes)
            val want = Pooling.unpack(java.util.Base64.getDecoder().decode(group.getString("vectors")))
            var low = 1.0
            for (r in want.indices) {
                val cos = Pooling.cosine(got[r], want[r])
                if (cos < low) low = cos
                if (cos < worst) {
                    worst = cos
                    worstText = texts.getString(r).take(60)
                }
            }
            lines += want.size
            Log.i(TAG, "recall group $i: ${want.size} lines${if (query) " (questions)" else ""} in ${Math.round(ms)} ms, lowest cosine against the PC ${String.format(java.util.Locale.ROOT, "%.6f", low)}")
        }
        Log.i(TAG, "recall vectors: $lines lines, lowest cosine against the PC ${String.format(java.util.Locale.ROOT, "%.6f", worst)} (${JSONObject.quote(worstText)})")
        val repeat = intent.getIntExtra("repeat", 10)
        val notes = groups.getJSONObject(groups.length() - 3).getJSONArray("texts")
        fun timed(texts: List<String>, query: Boolean): Double {
            val started = System.nanoTime()
            val bytes = bridge.recallEmbed(org.json.JSONArray(texts).toString(), query)
            return if (bytes.isEmpty()) Double.NaN else (System.nanoTime() - started) / 1e6
        }
        val single = (0 until repeat).map { timed(listOf(notes.getString(it % notes.length())), false) }
        val asked = (0 until repeat).map { timed(listOf(notes.getString(it % notes.length())), true) }
        val batch = List(minOf(32, notes.length())) { notes.getString(it) }
        val batches = (0 until maxOf(1, repeat / 3)).map { timed(batch, false) }
        Log.i(TAG, "recall timing: a note ${median(single)} ms, a question ${median(asked)} ms, a batch of ${batch.size} ${median(batches)} ms (${String.format(java.util.Locale.ROOT, "%.1f", median(batches).toDouble() / batch.size)} ms a note); runs ${single.map { Math.round(it) }} / ${asked.map { Math.round(it) }} / ${batches.map { Math.round(it) }}")
        val py = Python.getInstance()
        val seam = py.getModule("pebble.android.bridge").callAttr("sentences", bridge)
        if (seam == null) {
            Log.i(TAG, "recall seam: the brain found no phone sentence model")
        } else {
            val texts = py.getModule("json").callAttr("loads", org.json.JSONArray(batch).toString())
            val started = System.nanoTime()
            val rows = seam.callAttr("embed", texts, false).asList()
            val ms = (System.nanoTime() - started) / 1e6
            val first = rows.firstOrNull()?.asList()?.map { it.toFloat() }?.toFloatArray()
            val want = Pooling.unpack(java.util.Base64.getDecoder().decode(groups.getJSONObject(groups.length() - 3).getString("vectors")))[0]
            Log.i(TAG, "recall seam: name ${seam.get("name")}, dim ${seam.get("dim")}, related ${seam.get("related")}, ${rows.size} rows of ${first?.size ?: 0} numbers in ${Math.round(ms)} ms through Python, first row's cosine against the PC ${first?.let { String.format(java.util.Locale.ROOT, "%.6f", Pooling.cosine(it, want)) }}")
        }
        Log.i(TAG, "recall info " + bridge.recallInfo())
    }

    private fun median(values: List<Double>): Long {
        val kept = values.filter { !it.isNaN() }.sorted()
        return if (kept.isEmpty()) -1 else Math.round(kept[kept.size / 2])
    }

    private fun closeUp(context: Context, bridge: nz.pebble.robot.brain.Bridge, intent: Intent) {
        if (!JSONObject(bridge.eyesStatus()).optBoolean("enabled")) {
            withEyes(bridge, intent) { closeLook(context, bridge, intent) }
            return
        }
        closeLook(context, bridge, intent)
    }

    private fun closeLook(context: Context, bridge: nz.pebble.robot.brain.Bridge, intent: Intent) {
        val zoom = intent.getStringExtra("zoom")?.toDoubleOrNull() ?: 4.0
        val side = intent.getIntExtra("max_side", 1536)
        Log.i(TAG, "eyes before: " + JSONObject(bridge.eyesStatus()).let { "open ${it.opt("open")}, want ${it.opt("want")}" })
        val started = System.nanoTime()
        val jpeg = bridge.eyesCloseUp(side, zoom)
        val ms = (System.nanoTime() - started) / 1e6
        Log.i(TAG, "close look: ${jpeg.size} bytes in ${Math.round(ms)} ms; " + bridge.eyesCloseUpInfo())
        if (jpeg.isNotEmpty() && intent.getBooleanExtra("save", false)) {
            val file = java.io.File(context.filesDir, "probe/closeup.jpg")
            file.parentFile?.mkdirs()
            file.writeBytes(jpeg)
            Log.i(TAG, "saved the close look in ${file.name} (debug only; delete it after looking)")
        }
        Thread.sleep(intent.getIntExtra("after_ms", 3_000).toLong())
        Log.i(TAG, "eyes after: " + JSONObject(bridge.eyesStatus()).let { "open ${it.opt("open")}, want ${it.opt("want")}, fps ${it.opt("fps")}" })
    }

    private fun torch(bridge: nz.pebble.robot.brain.Bridge, intent: Intent) {
        if (intent.getStringExtra("camera") != null && !JSONObject(bridge.eyesStatus()).optBoolean("enabled")) {
            withEyes(bridge, intent) { light(bridge, intent) }
            return
        }
        light(bridge, intent)
    }

    private fun light(bridge: nz.pebble.robot.brain.Bridge, intent: Intent) {
        Log.i(TAG, "torch before: " + bridge.torchInfo())
        intent.getStringExtra("camera")?.let {
            bridge.eyesUse(it)
            Thread.sleep(3_000)
            Log.i(TAG, "eyes now: " + JSONObject(bridge.eyesStatus()).opt("open"))
        }
        val level = intent.getStringExtra("level")?.toDoubleOrNull() ?: 0.3
        Log.i(TAG, "torch on: " + bridge.torch(true, level, intent.getStringExtra("seconds")?.toDoubleOrNull() ?: 30.0))
        Thread.sleep(intent.getIntExtra("hold_ms", 2_000).toLong())
        Log.i(TAG, "torch while on: " + bridge.torchInfo())
        Log.i(TAG, "torch off: " + bridge.torch(false, level, 0.0))
    }

    private fun highBand(bridge: nz.pebble.robot.brain.Bridge, intent: Intent) {
        if (intent.getBooleanExtra("bench", false)) {
            val seconds = 20
            val random = java.util.Random(1)
            val pcm = ShortArray(48_000 * seconds) { (random.nextGaussian() * 300 + 2_000 * Math.sin(2 * Math.PI * 17_400.0 * it / 48_000)).toInt().toShort() }
            val down = nz.pebble.robot.brain.Decimate(3)
            val out = ShortArray(400)
            var started = System.nanoTime()
            var at = 0
            while (at < pcm.size) {
                down.push(pcm, at, 960, 1, out)
                at += 960
            }
            val decimateMs = (System.nanoTime() - started) / 1e6
            val band = nz.pebble.robot.brain.HighBand { 0.0 }
            val chunk = ShortArray(960)
            started = System.nanoTime()
            at = 0
            while (at < pcm.size) {
                System.arraycopy(pcm, at, chunk, 0, 960)
                band.onWide(chunk, 960, 1, 48_000, false)
                at += 960
            }
            val bandMs = (System.nanoTime() - started) / 1e6
            Log.i(TAG, "bench on $seconds s of 48 kHz sound: bringing it down ${String.format(java.util.Locale.ROOT, "%.1f", decimateMs)} ms (${String.format(java.util.Locale.ROOT, "%.2f", decimateMs / seconds / 10)} % of one core), high band ${String.format(java.util.Locale.ROOT, "%.1f", bandMs)} ms (${String.format(java.util.Locale.ROOT, "%.2f", bandMs / seconds / 10)} % of one core)")
            return
        }
        bridge.highBandMoving(intent.getBooleanExtra("moving", false))
        Thread.sleep(intent.getIntExtra("seconds", 5) * 1000L)
        val state = JSONObject(bridge.highBand(intent.getLongExtra("from", 0L)))
        val rows = state.getJSONArray("rows")
        state.remove("rows")
        Log.i(TAG, "high band: $state")
        var levels = 0
        for (i in 0 until rows.length()) {
            val row = rows.getJSONObject(i)
            if (row.optString("kind") == "levels") levels++ else Log.i(TAG, "high band tone: $row")
        }
        if (rows.length() > 0) Log.i(TAG, "high band: $levels level rows; the last " + rows.getJSONObject(rows.length() - 1))
        Log.i(TAG, "mic plan: " + bridge.micPlan())
    }

    private fun micProbe(bridge: nz.pebble.robot.brain.Bridge, intent: Intent) {
        val started = System.nanoTime()
        val result = JSONObject(bridge.micProbe(intent.getStringExtra("options") ?: "{}"))
        val properties = result.optJSONObject("properties")?.let { p -> JSONObject(p.toString()).put("microphones", p.optJSONArray("microphones")?.length() ?: 0) }
        Log.i(TAG, "mic probe took ${Math.round((System.nanoTime() - started) / 1e9)} s; properties $properties; problem [${result.optString("problem")}]")
        val configs = result.optJSONArray("configs") ?: org.json.JSONArray()
        for (i in 0 until configs.length()) {
            val c = configs.getJSONObject(i)
            val floors = c.optJSONArray("floors")?.optJSONArray(0)
            val shape = if (floors == null) "" else (0 until floors.length() step 2).joinToString(" ") { k -> "${k}k:${Math.round(floors.getDouble(k))}" }
            val text = if (!c.optBoolean("opened")) "refused (${c.optString("why")})" else "rate ${c.optInt("rate")} channels ${c.optInt("channels")} level ${c.opt("level_db")} copied ${c.opt("copied") ?: "-"} cliff ${c.opt("cliff_at_8k") ?: "-"} aec ${c.optString("echo_canceller")} floor $shape"
            Log.i(TAG, "mic probe ${c.optJSONObject("config")}: $text")
        }
        Log.i(TAG, "mic probe clicks: " + result.optJSONObject("clicks"))
        Log.i(TAG, "mic probe sweep: " + result.optJSONObject("sweep"))
        Log.i(TAG, "mic probe suggests: " + result.optJSONObject("suggested"))
    }

    private fun scores(context: Context, bridge: nz.pebble.robot.brain.Bridge, intent: Intent) = withTap(bridge) {
        val speech = BrainService.speech ?: return@withTap
        val tag = intent.getStringExtra("tag") ?: "run"
        Thread.sleep(intent.getIntExtra("seconds", 20) * 1000L)
        val data = JSONObject(bridge.soundScores(0))
        val nowMs = data.getDouble("now_ms")
        val nowS = System.nanoTime() / 1e9
        val loop = speech.state().optDouble("test_loop_started_at")
        val period = intent.getIntExtra("period_s", 15).toDouble()
        val rows = data.getJSONArray("rows")
        val out = org.json.JSONArray()
        for (i in 0 until rows.length()) {
            val row = rows.getJSONArray(i)
            val at = nowS - (nowMs - row.getDouble(0)) / 1000
            val phase = if (loop > 0) (((at - loop) % period) + period) % period else -1.0
            out.put(org.json.JSONArray().put(Math.round(phase * 1000) / 1000.0).put(row.getJSONArray(1)))
        }
        val file = java.io.File(context.filesDir, "probe/scores_$tag.json")
        file.parentFile?.mkdirs()
        file.writeText(JSONObject().put("tag", tag).put("rows", out).put("mic", speech.state().optJSONObject("microphone")).toString())
        Log.i(TAG, "scores: ${out.length()} rows kept in ${file.name} with their place in the test loop")
    }

    private fun brainEyes(bridge: nz.pebble.robot.brain.Bridge): PyObject? {
        val eyes = nz.pebble.robot.brain.Bridge::class.java.getDeclaredField("eyes").apply { isAccessible = true }.get(bridge) ?: throw IllegalStateException("this brain has no eyes")
        return Eyes::class.java.getDeclaredField("sink").apply { isAccessible = true }.get(eyes) as PyObject?
    }

    private fun withEyes(bridge: nz.pebble.robot.brain.Bridge, intent: Intent, block: (PyObject) -> Unit) {
        val running = brainEyes(bridge)
        val sink = running ?: run {
            val py = Python.getInstance()
            val scope = py.builtins.callAttr("dict")
            val code = listOf(
                "from pebble.body.profile import BodyProfile, resolve_profile",
                "from pebble.eyes import eyes_from_config",
                "from pebble.clock import Clock",
                "eyes = eyes_from_config(BodyProfile.load(resolve_profile('android', 'body')).eyes, Clock())",
            ).joinToString("\n")
            py.builtins.callAttr("exec", code, scope)
            Log.i(TAG, "the brain runs other eyes; started the phone's eyes from the android profile for this probe")
            scope.callAttr("get", "eyes")!!
        }
        try {
            val seen = waitFor(intent.getIntExtra("wait_s", 240)) { sink.get("available")?.toBoolean() == true }
            Log.i(TAG, "the phone's eyes see: $seen")
            block(sink)
        } finally {
            if (running == null && !intent.getBooleanExtra("keep", false)) {
                sink.callAttr("close")
                Log.i(TAG, "closed the probe's eyes")
            }
        }
    }

    private fun dumps(value: PyObject?): String {
        val py = Python.getInstance()
        return py.getModule("json").callAttr("dumps", value, Kwarg("default", py.builtins.get("str"))).toString()
    }

    private fun floorStatus(bridge: nz.pebble.robot.brain.Bridge): JSONObject? = JSONObject(bridge.eyesStatus()).optJSONObject("floor")

    private fun waitFor(seconds: Int, check: () -> Boolean): Boolean {
        val until = System.nanoTime() + seconds * 1_000_000_000L
        while (System.nanoTime() < until) {
            if (check()) return true
            Thread.sleep(200)
        }
        return check()
    }

    private fun floor(bridge: nz.pebble.robot.brain.Bridge, intent: Intent) = withEyes(bridge, intent) { sink -> floorWith(bridge, intent, sink) }

    private fun floorWith(bridge: nz.pebble.robot.brain.Bridge, intent: Intent, sink: PyObject) {
        val ready = waitFor(intent.getIntExtra("wait_s", 240)) { floorStatus(bridge)?.let { !it.isNull("backend") || it.optString("problem").isNotEmpty() } ?: false }
        Log.i(TAG, "floor ready $ready: ${floorStatus(bridge)}")
        if (!ready || floorStatus(bridge)?.isNull("backend") != false) return
        val asked = floorStatus(bridge)!!.optInt("passes")
        val started = System.nanoTime()
        sink.callAttr("scan_floor")
        val once = waitFor(120) { floorStatus(bridge)!!.optInt("passes") > asked }
        Log.i(TAG, "one scan asked for: done $once in ${Math.round((System.nanoTime() - started) / 1e6)} ms, ${floorStatus(bridge)}")
        Thread.sleep(400)
        val sight = sink.callAttr("latest", 2.0)
        if (sight == null) {
            Log.i(TAG, "the brain has no fresh sight")
        } else {
            val rays = sight.get("floor")!!.asList()
            val distances = rays.map { it.get("distance_m")!!.toDouble() }
            Log.i(TAG, "sight floor: ${rays.size} rays, nearest ${distances.minOrNull()} m, open ${distances.count { it >= 9.0 }}, floor_at ${sight.get("floor_at")} at ${sight.get("at")}")
            if (rays.isNotEmpty()) Log.i(TAG, "first ray ${rays.first()}, middle ${rays[rays.size / 2]}, last ${rays.last()}")
        }
        val seconds = intent.getIntExtra("seconds", 10)
        val before = floorStatus(bridge)!!.optInt("passes")
        sink.callAttr("set_moving", true)
        val until = System.nanoTime() + seconds * 1_000_000_000L
        var looked = 0
        var withFloor = 0
        var oldest = 0.0
        while (System.nanoTime() < until) {
            val now = sink.callAttr("latest", 1.0)
            val at = now?.get("floor_at")
            looked++
            if (at != null) {
                withFloor++
                oldest = maxOf(oldest, now.get("at")!!.toDouble() - at.toDouble())
            }
            Thread.sleep(50)
        }
        sink.callAttr("set_moving", false)
        Log.i(TAG, "while moving, $withFloor of $looked sights carried a floor scan, the oldest ${String.format(java.util.Locale.ROOT, "%.2f", oldest)} s old")
        val moved = floorStatus(bridge)!!
        val scans = moved.optInt("passes") - before
        Log.i(TAG, "moving for $seconds s: $scans scans, ${String.format(java.util.Locale.ROOT, "%.2f", scans.toDouble() / seconds)} a second, $moved")
        Thread.sleep(3_000)
        val settled = floorStatus(bridge)!!.optInt("passes")
        Thread.sleep(2_000)
        Log.i(TAG, "after stopping: passes $settled then ${floorStatus(bridge)!!.optInt("passes")} (should not grow)")
        Log.i(TAG, "brain floor status " + dumps(sink.callAttr("status").callAttr("get", "floor")))
        Log.i(TAG, "brain motion " + dumps(sink.callAttr("motion")))
        val py = Python.getInstance()
        val loop = py.getModule("pebble.android.main").get("_running")!!.callAttr("get", "loop") ?: throw IllegalStateException("the brain's loop is not running")
        val asyncio = py.getModule("asyncio")
        val printed = System.nanoTime()
        val vec = asyncio.callAttr("run_coroutine_threadsafe", sink.callAttr("place_print"), loop).callAttr("result", 120)
        val ms = Math.round((System.nanoTime() - printed) / 1e6)
        if (vec == null) {
            Log.i(TAG, "place print: none ($ms ms)")
        } else {
            val values = vec.asList().map { it.toDouble() }
            Log.i(TAG, "place print: ${values.size} numbers, length ${String.format(java.util.Locale.ROOT, "%.6f", Math.sqrt(values.sumOf { it * it }))}, made in $ms ms")
            val again = asyncio.callAttr("run_coroutine_threadsafe", sink.callAttr("place_print"), loop).callAttr("result", 120)!!.asList().map { it.toDouble() }
            Log.i(TAG, "place print again: same picture gives similarity ${String.format(java.util.Locale.ROOT, "%.6f", values.zip(again).sumOf { it.first * it.second })}")
        }
        val other = if (sink.callAttr("camera")?.toString() == "rear") "front" else "rear"
        Log.i(TAG, "place print of the $other camera while it is off: " + asyncio.callAttr("run_coroutine_threadsafe", sink.callAttr("place_print", other), loop).callAttr("result", 30))
    }

    private fun depth(context: Context, intent: Intent) {
        if (!org.opencv.android.OpenCVLoader.initLocal()) throw IllegalStateException("OpenCV did not load")
        val files = nz.pebble.robot.eyes.ModelFiles(context)
        val path = intent.getStringExtra("model")?.let { java.io.File(context.filesDir, it) } ?: files.path(nz.pebble.robot.eyes.Floor.MODEL)
        val threads = intent.getIntExtra("threads", 2)
        for (provider in listOf("xnnpack", "cpu")) {
            try {
                nz.pebble.robot.eyes.OrtRunner(path, provider, threads).close()
                Log.i(TAG, "depth model loads on $provider")
            } catch (e: Throwable) {
                Log.i(TAG, "depth model would not load on $provider: ${e.message}")
            }
        }
        val model = nz.pebble.robot.eyes.Depth(nz.pebble.robot.eyes.OrtRunner(path, intent.getStringExtra("provider") ?: "cpu", threads))
        val fov = intent.getStringExtra("fov")?.toDouble() ?: 70.0
        val height = intent.getStringExtra("height")?.toDouble() ?: 0.14
        val pitch = intent.getStringExtra("pitch")?.toDouble() ?: 8.0
        val root = java.io.File(context.filesDir, intent.getStringExtra("folder") ?: "floor")
        val rolled = Regex("_r(-?[0-9.]+)\\.")
        for (picture in root.listFiles()?.filter { it.name.endsWith(".png") || it.name.endsWith(".jpg") }?.sortedBy { it.name } ?: emptyList()) {
            val image = org.opencv.imgcodecs.Imgcodecs.imread(picture.path)
            val roll = rolled.find(picture.name)?.groupValues?.get(1)?.toDouble() ?: 0.0
            model.run(image, roll)
            val started = System.nanoTime()
            val map = model.run(image, roll)
            val middle = System.nanoTime()
            val scan = nz.pebble.robot.eyes.Floor.rays(map, nz.pebble.robot.eyes.Floor.ROWS, nz.pebble.robot.eyes.Floor.COLS, fov, height, pitch)
            val ended = System.nanoTime()
            image.release()
            val buffer = java.nio.ByteBuffer.allocate(map.size * 4).order(java.nio.ByteOrder.LITTLE_ENDIAN)
            buffer.asFloatBuffer().put(map)
            java.io.File(root, picture.nameWithoutExtension + ".depth.bin").writeBytes(buffer.array())
            val rays = org.json.JSONArray()
            scan?.rays?.forEach { rays.put(org.json.JSONArray().put(it.bearing).put(it.distance).put(it.score)) }
            java.io.File(root, picture.nameWithoutExtension + ".rays.json").writeText(JSONObject().put("quality", scan?.quality ?: JSONObject.NULL).put("rays", if (scan == null) JSONObject.NULL else rays).toString())
            Log.i(TAG, "depth ${picture.name} roll $roll: model ${String.format(java.util.Locale.ROOT, "%.1f", (middle - started) / 1e6)} ms, rays ${String.format(java.util.Locale.ROOT, "%.1f", (ended - middle) / 1e6)} ms, quality ${scan?.quality}, nearest ${scan?.rays?.minOfOrNull { it.distance }}")
        }
        model.close()
    }

    private fun motion(context: Context, bridge: nz.pebble.robot.brain.Bridge, intent: Intent) {
        if (!org.opencv.android.OpenCVLoader.initLocal()) throw IllegalStateException("OpenCV did not load")
        val name = intent.getStringExtra("picture") ?: "desk.jpg"
        val bytes = context.assets.open("samples/$name").use { it.readBytes() }
        val image = org.opencv.imgcodecs.Imgcodecs.imdecode(org.opencv.core.MatOfByte(*bytes), org.opencv.imgcodecs.Imgcodecs.IMREAD_COLOR)
        val wide = org.opencv.core.Mat()
        org.opencv.imgproc.Imgproc.resize(image, wide, org.opencv.core.Size(720.0, 480.0), 0.0, 0.0, org.opencv.imgproc.Imgproc.INTER_AREA)
        image.release()
        for (shift in listOf(0, 8, 40)) {
            val a = wide.submat(0, 480, 0, 640).clone()
            val b = wide.submat(0, 480, shift, shift + 640).clone()
            val m = Motion()
            m.step(a, "front", 1.0)
            val step = m.step(b, "front", 1.1)
            m.close()
            a.release()
            b.release()
            Log.i(TAG, "motion $name shift $shift px: " + (step?.let { String.format(java.util.Locale.ROOT, "dx %.4f dy %.4f sure %.4f change %.6f", it.dx, it.dy, it.sure, it.change) } ?: "none"))
        }
        val a = wide.submat(0, 480, 0, 640).clone()
        val m = Motion()
        val rounds = 100
        val started = System.nanoTime()
        for (i in 0 until rounds) m.step(a, "front", 1.0 + i * 0.1)
        Log.i(TAG, "motion step on a 640x480 picture: ${String.format(java.util.Locale.ROOT, "%.2f", (System.nanoTime() - started) / 1e6 / rounds)} ms")
        m.close()
        a.release()
        wide.release()
        if (intent.getBooleanExtra("live", false)) {
            withEyes(bridge, intent) { sink ->
                Thread.sleep(1_000)
                Log.i(TAG, "live motion " + dumps(sink.callAttr("motion")))
            }
        }
    }

    companion object {
        const val TAG = "PebbleDebugBrain"
    }
}
