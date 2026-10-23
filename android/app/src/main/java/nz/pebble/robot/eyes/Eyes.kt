package nz.pebble.robot.eyes

import android.content.Context
import android.hardware.display.DisplayManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.Display
import android.view.Surface
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.resolutionselector.AspectRatioStrategy
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.lifecycle.LifecycleOwner
import com.chaquo.python.PyObject
import org.json.JSONArray
import org.json.JSONObject
import org.opencv.android.OpenCVLoader
import org.opencv.core.Core
import org.opencv.core.CvType
import org.opencv.core.Mat
import org.opencv.core.MatOfByte
import org.opencv.core.MatOfInt
import org.opencv.core.Size
import org.opencv.imgcodecs.Imgcodecs
import org.opencv.imgproc.Imgproc
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import kotlin.math.ceil
import kotlin.math.max
import kotlin.math.min

class Eyes(private val context: Context, private val owner: LifecycleOwner, private val reverse: Boolean = false, private val torch: Torch? = null) {
    private val pace = nz.pebble.robot.keeper.PaceReader(java.io.File(nz.pebble.robot.Paths(context).run, nz.pebble.robot.keeper.PaceFile.NAME))
    data class CameraSettings(val width: Int, val height: Int, val rotate: Int, val mirror: Boolean, val fov: Double)

    data class Settings(
        val camera: String,
        val enabled: Boolean,
        val cameras: Map<String, CameraSettings>,
        val tagId: Int,
        val tagSize: Double,
        val maxFps: Double,
        val tagsOn: Set<String>,
        val peopleOn: Set<String>,
        val slowOn: Boolean,
        val slowEvery: Double,
        val slowChange: Double,
        val slowScore: Float,
        val slowThreads: Int,
        val classes: Int,
        val backend: String,
        val threads: Int,
        val testImage: String,
        val pose: Boolean = true,
        val poseHz: Double = 5.0,
        val posePeople: Int = 3,
        val prints: Boolean = true,
        val hazardsOn: Boolean = false,
        val hazardEvery: Double = HazardLane.DEFAULT_S,
        val hazardScore: Float = HAZARD_SCORE,
        val hazardThreads: Int = 1,
        val hazardClasses: Int = 0,
        val speakingOn: Boolean = false,
        val speakingFaces: Int = Mouth.MAX_FACES,
        val speakingMinPx: Double = Mouth.MIN_FACE_PX,
        val floorOn: Boolean = false,
        val floorEvery: Double = Floor.EVERY_S,
        val floorGate: String = Floor.MOVING,
        val floorThreads: Int = 2,
        val floorBins: Int = Floor.BINS,
        val floorReach: Double = Floor.REACH_M,
        val heads: Map<String, DoubleArray> = emptyMap(),
    ) {
        companion object {
            const val HAZARD_SCORE = 0.25f

            fun parse(text: String, testImage: String): Settings {
                val o = JSONObject(text)
                val cameras = HashMap<String, CameraSettings>()
                val c = o.getJSONObject("cameras")
                for (name in listOf("front", "rear")) {
                    val s = c.optJSONObject(name) ?: JSONObject()
                    cameras[name] = CameraSettings(s.optInt("width", 640), s.optInt("height", 480), s.optInt("rotate", 0), s.optBoolean("mirror", false), s.optDouble("fov_h_deg", 70.0))
                }
                val slow = o.optJSONObject("slow") ?: JSONObject()
                val detect = o.optJSONObject("detect") ?: JSONObject()
                val hazards = o.optJSONObject("hazards") ?: JSONObject()
                val speaking = o.optJSONObject("speaking") ?: JSONObject()
                val floor = o.optJSONObject("floor") ?: JSONObject()
                fun set(a: JSONArray?): Set<String> = (0 until (a?.length() ?: 0)).map { a!!.getString(it) }.toSet()
                return Settings(
                    camera = o.optString("camera", "front"),
                    enabled = o.optBoolean("enabled", true),
                    cameras = cameras,
                    tagId = o.optInt("tag_id", 0),
                    tagSize = o.optDouble("tag_size_m", 0.048),
                    maxFps = o.optDouble("max_fps", 10.0).coerceIn(1.0, 30.0),
                    tagsOn = set(o.optJSONArray("tags_on")),
                    peopleOn = set(o.optJSONArray("people_on")),
                    slowOn = slow.optBoolean("on", false),
                    slowEvery = slow.optDouble("every_s", 1.0),
                    slowChange = slow.optDouble("change", 0.06),
                    slowScore = slow.optDouble("score", 0.45).toFloat(),
                    slowThreads = slow.optInt("threads", 1).coerceIn(1, 4),
                    classes = slow.optInt("classes", 0),
                    backend = detect.optString("backend", "auto"),
                    threads = detect.optInt("threads", 2).coerceIn(1, 4),
                    testImage = testImage,
                    pose = detect.optBoolean("pose", true),
                    poseHz = detect.optDouble("pose_hz", 5.0).coerceIn(0.5, 15.0),
                    posePeople = detect.optInt("pose_people", 3).coerceIn(1, 6),
                    prints = detect.optBoolean("prints", true),
                    hazardsOn = hazards.optBoolean("on", false),
                    hazardEvery = HazardLane.clamp(hazards.optDouble("every_s", HazardLane.DEFAULT_S)),
                    hazardScore = hazards.optDouble("score", HAZARD_SCORE.toDouble()).toFloat(),
                    hazardThreads = hazards.optInt("threads", 1).coerceIn(1, 4),
                    hazardClasses = hazards.optInt("classes", 0),
                    speakingOn = speaking.optBoolean("on", false),
                    speakingFaces = speaking.optInt("faces", Mouth.MAX_FACES).coerceIn(1, 4),
                    speakingMinPx = speaking.optDouble("min_face_px", Mouth.MIN_FACE_PX).coerceIn(8.0, 400.0),
                    floorOn = floor.optBoolean("on", false),
                    floorEvery = floor.optDouble("every_s", Floor.EVERY_S),
                    floorGate = Floor.gate(floor.optString("gate", Floor.MOVING)),
                    floorThreads = floor.optInt("threads", 2).coerceIn(1, 4),
                    floorBins = floor.optInt("bins", Floor.BINS).coerceIn(4, 128),
                    floorReach = floor.optDouble("reach_m", Floor.REACH_M).let { if (it.isFinite()) it.coerceIn(0.2, 8.0) else Floor.REACH_M },
                    heads = heads(o.optJSONObject("head")),
                )
            }

            fun heads(o: JSONObject?): Map<String, DoubleArray> {
                val out = HashMap<String, DoubleArray>()
                for (name in listOf("front", "rear")) {
                    val a = o?.optJSONArray(name) ?: continue
                    if (a.length() != 3) continue
                    val values = DoubleArray(3) { a.optDouble(it, Double.NaN) }
                    if (values.all { it.isFinite() }) out[name] = values
                }
                return out
            }
        }
    }

    private val main = Handler(Looper.getMainLooper())
    private val worker: ExecutorService = Executors.newSingleThreadExecutor { Thread(it, "pebble-eyes").apply { priority = Thread.NORM_PRIORITY + 1 } }
    private val files = ModelFiles(context)
    @Volatile private var sink: PyObject? = null
    @Volatile private var settings: Settings? = null
    @Volatile private var enabled = false
    @Volatile private var want = "front"
    @Volatile private var open: String? = null
    @Volatile private var ready = false
    private var faces: FaceFinder? = null
    private var things: NanoDet? = null
    private var tags: TagFinder? = null
    private var slow: SlowLane? = null
    @Volatile private var hazards: HazardLane? = null
    @Volatile private var floor: FloorLane? = null
    @Volatile private var heads: Map<String, DoubleArray> = emptyMap()
    private val motion = Motion()
    private var pose: PoseFinder? = null
    private var prints: PrintFinder? = null
    private var proposer: Pair<Float, Yoloe>? = null
    private var mouths: MouthReader? = null
    @Volatile private var mouthsOn = false
    @Volatile private var mouthsUntil = 0.0
    @Volatile private var mouthReads = 0L
    @Volatile private var mouthProblem = ""
    private var bodies: List<Det> = emptyList()
    private var poseAt = Double.NEGATIVE_INFINITY
    private val frameLock = Any()
    private var latest: Mat? = null
    private var latestMeta: JSONObject? = null
    private val held = LinkedHashMap<Int, Pair<Mat, JSONObject>>()
    private var heldIds = 0
    @Volatile private var printsTop = 0
    private var provider: ProcessCameraProvider? = null
    @Volatile private var bound: androidx.camera.core.Camera? = null
    @Volatile private var closeLook = false
    private val closeLock = Any()
    private val closeUp = CloseUp(owner)
    private var still: Thread? = null
    @Volatile private var stillStop = false
    private var lastFrame = 0L
    private var sinceBody = 99
    private var bodiesAt = Double.NEGATIVE_INFINITY
    private val ms = HashMap<String, Double>()
    @Volatile private var frames = 0L
    @Volatile private var fps = 0.0
    @Volatile private var problem = ""
    private var choices = JSONObject()
    private var bench = JSONObject()
    private var pendingTestImage = ""

    fun useTestImage(name: String) {
        pendingTestImage = name
    }

    fun setSink(target: PyObject?) {
        sink = target
    }

    fun start(json: String) {
        val parsed = Settings.parse(json, pendingTestImage)
        settings = parsed
        heads = parsed.heads
        enabled = parsed.enabled
        want = if (parsed.camera == "rear") "rear" else "front"
        worker.execute { load(parsed) }
    }

    fun stop() {
        enabled = false
        main.post { closeCamera("stopped") }
        worker.execute {
            slow?.close()
            slow = null
            hazards?.close()
            hazards = null
            floor?.close()
            floor = null
            motion.close()
            faces?.close()
            things?.close()
            pose?.close()
            prints?.close()
            proposer?.second?.close()
            mouths?.close()
            mouths = null
            faces = null
            things = null
            pose = null
            prints = null
            proposer = null
            synchronized(frameLock) {
                held.values.forEach { it.first.release() }
                held.clear()
            }
            forgetLatest()
            ready = false
        }
    }

    private fun forgetLatest() {
        synchronized(frameLock) {
            latest?.release()
            latest = null
            latestMeta = null
        }
    }

    fun shutdown() {
        stop()
        closeUp.shutdown()
        worker.shutdown()
    }

    fun use(camera: String) {
        want = if (camera == "rear") "rear" else "front"
        main.post { openCamera() }
    }

    fun enable(on: Boolean) {
        enabled = on
        if (!on) {
            slow?.forget()
            hazards?.forget()
            floor?.forget()
            worker.execute {
                motion.reset()
                if (!enabled) forgetLatest()
            }
        }
        main.post { if (on) openCamera() else closeCamera("off") }
    }

    fun mouths(on: Boolean, tailS: Double) {
        if (on) {
            mouthsOn = true
        } else {
            mouthsUntil = System.nanoTime() / 1e9 + tailS.coerceIn(0.0, Mouth.MAX_TAIL_S)
            mouthsOn = false
        }
    }

    private fun mouthsWanted(): Boolean = mouthsOn || System.nanoTime() / 1e9 < mouthsUntil

    fun hazardsEvery(seconds: Double) {
        hazards?.setEvery(seconds)
    }

    fun moving(on: Boolean) {
        floor?.setMoving(on)
    }

    fun scanFloor() {
        floor?.want()
    }

    fun head(json: String) {
        heads = Settings.heads(JSONObject(json))
    }

    private fun where(camera: String): FloorLane.Where? {
        val cs = settings?.cameras?.get(camera) ?: return null
        val head = heads[camera] ?: return null
        return FloorLane.Where(cs.fov, head[0], head[1], head[2])
    }

    fun busy(on: Boolean) {
        slow?.setBusy(on)
    }

    fun moved() {
        slow?.moved()
    }

    fun lookClosely(id: Int) {
        val lane = slow
        if (lane == null) send("slow", JSONObject().put("failed", true).put("demand", JSONArray(listOf(id)))) else lane.demand(id)
    }

    private fun load(s: Settings) {
        try {
            if (!OpenCVLoader.initLocal()) throw IllegalStateException("OpenCV did not load")
            TagFinder.threads(s.threads)
            val sample = sample()
            val chosen = Bench.choose(context, s, files, sample)
            choices = chosen.choices
            bench = chosen.timings
            faces = chosen.faces
            things = chosen.things
            pose = chosen.pose
            prints = chosen.prints
            tags = TagFinder(s.tagId, s.tagSize)
            sample.release()
            if (s.slowOn && s.classes > 0) {
                val backend = chosen.choices.optString("slow", "onnxruntime-xnnpack")
                val vocabSize = s.classes
                slow = SlowLane({ Bench.slowFinder(files, backend, s.slowThreads, vocabSize, s.slowScore) }, s.slowEvery, s.slowChange, ::marks, { pace.eyesFactor() }) { send("slow", it) }.also { it.start() }
            }
            if (s.hazardsOn && s.hazardClasses > 0) {
                val backend = chosen.choices.optString("slow", Bench.CPU)
                hazards = HazardLane({ Bench.hazardFinder(files, backend, s.hazardThreads, s.hazardClasses, s.hazardScore) }, s.hazardEvery, ::grab) { send("hazards_seen", it) }.also { it.start() }
            }
            if (s.floorOn) {
                floor = FloorLane({ Bench.depthFinder(context, files, s) }, s.floorEvery, s.floorGate, s.floorBins, s.floorReach, ::grab, ::where) { ask("floor_seen", it) }.also { it.start() }
            }
            ready = true
            Log.i(TAG, "eyes ready: $choices")
        } catch (e: Throwable) {
            problem = "the eyes could not load their models: ${e.message}"
            Log.e(TAG, problem, e)
        }
        main.post { openCamera() }
    }

    private fun sample(): Mat {
        val bytes = context.assets.open("samples/desk.jpg").use { it.readBytes() }
        val image = Imgcodecs.imdecode(MatOfByte(*bytes), Imgcodecs.IMREAD_COLOR)
        if (image.empty()) return Mat.zeros(480, 640, CvType.CV_8UC3)
        val small = Mat()
        Imgproc.resize(image, small, org.opencv.core.Size(640.0, 480.0), 0.0, 0.0, Imgproc.INTER_AREA)
        image.release()
        return small
    }

    private fun displayRotation(): Int = if (reverse) Surface.ROTATION_270 else Surface.ROTATION_90

    private fun openCamera() {
        val s = settings ?: return
        if (!enabled || closeLook) return
        val camera = want
        if (open == camera) return
        closeCamera(null)
        if (s.testImage.isNotEmpty()) {
            startStill(s, camera)
            return
        }
        val future = ProcessCameraProvider.getInstance(context)
        future.addListener({
            try {
                val made = future.get()
                provider = made
                val selector = if (camera == "front") CameraSelector.DEFAULT_FRONT_CAMERA else CameraSelector.DEFAULT_BACK_CAMERA
                if (!made.hasCamera(selector)) {
                    fail(camera, "this phone has no $camera camera")
                    return@addListener
                }
                val cs = s.cameras.getValue(camera)
                val resolution = ResolutionSelector.Builder()
                    .setAspectRatioStrategy(AspectRatioStrategy.RATIO_4_3_FALLBACK_AUTO_STRATEGY)
                    .setResolutionStrategy(ResolutionStrategy(android.util.Size(cs.width, cs.height), ResolutionStrategy.FALLBACK_RULE_CLOSEST_HIGHER_THEN_LOWER))
                    .build()
                val analysis = ImageAnalysis.Builder()
                    .setResolutionSelector(resolution)
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                    .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
                    .setTargetRotation(displayRotation())
                    .build()
                analysis.setAnalyzer(worker) { image -> analyze(image, camera) }
                if (closeLook) return@addListener
                made.unbindAll()
                val opened = made.bindToLifecycle(owner, selector, analysis)
                opened.cameraInfo.cameraState.observe(owner) { state ->
                    val error = state.error
                    if (error != null && open == camera) fail(camera, "the $camera camera reported error ${error.code}${if (error.type == androidx.camera.core.CameraState.ErrorType.CRITICAL) " (it gave up)" else ""}")
                }
                bound = opened
                torch?.cameraChanged(if (camera == "rear") opened else null)
                open = camera
                lastFrame = 0
                send("state", JSONObject().put("state", "open").put("camera", camera))
            } catch (e: Exception) {
                fail(camera, "the $camera camera would not open: ${e.message}")
            }
        }, androidx.core.content.ContextCompat.getMainExecutor(context))
    }

    private fun fail(camera: String, why: String) {
        problem = why
        Log.w(TAG, why)
        closeCamera(null)
        send("state", JSONObject().put("state", "failed").put("camera", camera).put("problem", why))
    }

    private fun closeCamera(reason: String?) {
        stillStop = true
        still?.interrupt()
        still = null
        try {
            provider?.unbindAll()
        } catch (e: Exception) {
            Log.w(TAG, "unbinding the camera failed", e)
        }
        if (bound != null) torch?.cameraChanged(null)
        bound = null
        val was = open
        open = null
        if (was != null || reason != null) send("state", JSONObject().put("state", "closed").put("camera", was ?: JSONObject.NULL).put("why", reason ?: "switching"))
    }

    private fun startStill(s: Settings, camera: String) {
        val bytes = try {
            context.assets.open("samples/${s.testImage}").use { it.readBytes() }
        } catch (e: Exception) {
            fail(camera, "there is no test picture called ${s.testImage}")
            return
        }
        stillStop = false
        open = camera
        send("state", JSONObject().put("state", "open").put("camera", camera).put("source", "test picture ${s.testImage}"))
        still = Thread({
            val picture = Imgcodecs.imdecode(MatOfByte(*bytes), Imgcodecs.IMREAD_COLOR)
            while (!stillStop && enabled && open == camera) {
                val frame = picture.clone()
                worker.execute { process(frame, camera, System.nanoTime()) }
                try {
                    Thread.sleep((1000 / fps(s)).toLong())
                } catch (e: InterruptedException) {
                    break
                }
            }
            picture.release()
        }, "pebble-eyes-still").also { it.start() }
    }

    private fun fps(s: Settings): Double = max(1.0, s.maxFps * pace.eyesFactor())

    private fun analyze(image: ImageProxy, camera: String) {
        try {
            val s = settings ?: return
            if (!enabled || camera != want) return
            val now = System.nanoTime()
            if (now - lastFrame < (1e9 / fps(s)).toLong()) return
            val cs = s.cameras.getValue(camera)
            val bgr = Frames.toBgr(image, image.imageInfo.rotationDegrees + cs.rotate, cs.mirror)
            process(bgr, camera, now)
        } catch (e: Throwable) {
            problem = "looking at a picture failed: ${e.message}"
            Log.w(TAG, problem, e)
        } finally {
            image.close()
        }
    }

    private fun process(bgr: Mat, camera: String, captured: Long) {
        val s = settings
        if (s == null || !enabled || camera != want) {
            bgr.release()
            return
        }
        if (lastFrame != 0L) {
            val gap = max(1e-3, (captured - lastFrame) / 1e9)
            fps = if (fps == 0.0) 1 / gap else fps * 0.85 + 0.15 / gap
        }
        lastFrame = captured
        val t = captured / 1e9
        val out = JSONObject().put("camera", camera).put("t", t).put("w", bgr.cols()).put("h", bgr.rows())
        val cs = s.cameras.getValue(camera)
        if (ready && camera in s.peopleOn) {
            faces?.let { finder ->
                val started = System.nanoTime()
                val found = finder.find(bgr)
                out.put("faces", boxes(found, false))
                add("face", started)
                if (s.speakingOn && mouthsWanted()) readMouths(bgr, found, s)?.let { out.put("mouths", it) }
            }
            things?.let { finder ->
                val budget = 1000.0 / fps(s) - (ms["face"] ?: 0.0) - (if (camera in s.tagsOn) ms["tag"] ?: 0.0 else 0.0)
                val every = ceil((ms["body"] ?: 0.0) / max(5.0, budget)).toInt().coerceIn(1, 8)
                sinceBody++
                if (sinceBody >= every || t - bodiesAt > 1.0) {
                    val started = System.nanoTime()
                    val found = finder.find(bgr)
                    out.put("objects", boxes(found, true))
                    bodies = found.filter { it.cls == Decode.PERSON }
                    add("body", started)
                    bodiesAt = t
                    sinceBody = 0
                }
            }
        }
        val walker = pose
        if (ready && walker != null && camera in s.peopleOn && t - poseAt >= 1.0 / s.poseHz && t - bodiesAt <= 1.2 && bodies.isNotEmpty()) {
            val started = System.nanoTime()
            val found = JSONArray()
            for (body in bodies.sortedByDescending { it.w * it.h }.take(s.posePeople)) {
                val points = walker.points(bgr, body)
                found.put(JSONObject().put("box", JSONArray(listOf(body.x, body.y, body.w, body.h))).put("points", JSONArray(points.map { Math.round(it * 10000) / 10000.0 })))
            }
            out.put("poses", found)
            poseAt = t
            add("pose", started)
        }
        if (ready && camera in s.tagsOn) {
            tags?.let { finder ->
                val started = System.nanoTime()
                val gray = Mat()
                Imgproc.cvtColor(bgr, gray, Imgproc.COLOR_BGR2GRAY)
                out.put("tags", finder.find(gray, cs.fov))
                gray.release()
                add("tag", started)
            }
        }
        if (ready && hazards != null) glow(bgr, out)
        val moved = System.nanoTime()
        try {
            motion.step(bgr, camera, t)?.let { out.put("motion", it.json()) }
            add("motion", moved)
        } catch (e: Throwable) {
            problem = "measuring how the picture moved failed: ${e.message}"
            Log.w(TAG, problem, e)
        }
        out.put("ms", JSONObject(ms.mapValues { Math.round(it.value * 10) / 10.0 }))
        frames++
        synchronized(frameLock) {
            val keep = latest ?: Mat().also { latest = it }
            bgr.copyTo(keep)
            latestMeta = JSONObject().put("camera", camera).put("t", t).put("w", bgr.cols()).put("h", bgr.rows()).put("fov", cs.fov)
        }
        send("feed", out)
        val lane = slow
        if (ready && lane != null && enabled) lane.offer(bgr, camera, t) else bgr.release()
    }

    private fun readMouths(bgr: Mat, found: List<Det>, s: Settings): JSONArray? {
        val picked = Mouth.pick(found, bgr.cols(), s.speakingMinPx, s.speakingFaces)
        if (picked.isEmpty()) return null
        val reader = mouths ?: loadMouths() ?: return null
        val started = System.nanoTime()
        val rows = JSONArray()
        for (i in picked) {
            val shape = try {
                reader.read(bgr, Mouth.pixels(found[i].marks!!, bgr.cols(), bgr.rows()))
            } catch (e: Throwable) {
                mouthProblem = "reading a mouth failed: ${e.message}"
                Log.w(TAG, mouthProblem, e)
                null
            }
            mouthReads++
            rows.put(if (shape == null) JSONArray(listOf(i)) else JSONArray(listOf(i, Math.round(shape[0] * 1e6) / 1e6, Math.round(shape[1] * 1e6) / 1e6)))
        }
        add("mouth", started)
        return rows
    }

    private fun loadMouths(): MouthReader? {
        if (mouthProblem.startsWith(NO_MOUTHS)) return null
        return try {
            MouthReader(files.path(Mouth.MODEL)).also {
                mouths = it
                mouthProblem = ""
            }
        } catch (e: Throwable) {
            mouthProblem = "$NO_MOUTHS: ${e.message}"
            Log.w(TAG, mouthProblem, e)
            null
        }
    }

    private fun marks(picture: Mat, found: List<Det>): JSONObject? {
        val finder = prints ?: return null
        val top = printsTop
        if (top <= 0 || found.isEmpty()) return null
        val rows = found.indices.sortedByDescending { found[it].w * found[it].h }.take(top)
        val vecs = finder.embed(picture, rows.map { doubleArrayOf(found[it].x.toDouble(), found[it].y.toDouble(), found[it].w.toDouble(), found[it].h.toDouble()) })
        return JSONObject().put("print_rows", JSONArray(rows)).put("prints", JSONArray(vecs.map { v -> JSONArray(v.map { Math.round(it * 1e6) / 1e6 }) }))
    }

    private fun glow(bgr: Mat, out: JSONObject) {
        val started = System.nanoTime()
        val small = Mat()
        Imgproc.resize(bgr, small, Size(Glow.WIDTH.toDouble(), Glow.HEIGHT.toDouble()), 0.0, 0.0, Imgproc.INTER_AREA)
        val hsv = Mat()
        Imgproc.cvtColor(small, hsv, Imgproc.COLOR_BGR2HSV)
        val colours = ByteArray(Glow.CELLS * 3)
        val shades = ByteArray(Glow.CELLS * 3)
        small.get(0, 0, colours)
        hsv.get(0, 0, shades)
        small.release()
        hsv.release()
        out.put("warm", Math.round(Glow.warm(shades) * 1e6) / 1e6).put("glow", Glow.encode(Glow.brightest(colours)))
        add("glow", started)
    }

    private fun grab(): HazardLane.Picture? {
        if (!enabled) return null
        synchronized(frameLock) {
            val m = latest ?: return null
            val meta = latestMeta ?: return null
            val t = meta.optDouble("t", 0.0)
            if (System.nanoTime() / 1e9 - t > FRESH_S) return null
            return HazardLane.Picture(m.clone(), meta.optString("camera"), t)
        }
    }

    fun snapshot(camera: String, maxSide: Int, maxAgeS: Double): ByteArray {
        if (!enabled) return ByteArray(0)
        val picture = synchronized(frameLock) {
            val m = latest ?: return ByteArray(0)
            val meta = latestMeta ?: return ByteArray(0)
            if (camera.isNotEmpty() && meta.optString("camera") != camera) return ByteArray(0)
            if (System.nanoTime() / 1e9 - meta.optDouble("t", 0.0) > maxAgeS) return ByteArray(0)
            m.clone()
        }
        return try {
            Frames.jpeg(picture, maxSide.coerceIn(SNAPSHOT_MIN, SNAPSHOT_MAX), JPEG_QUALITY)
        } catch (e: Throwable) {
            Log.w(TAG, "the picture could not be made into a JPEG", e)
            ByteArray(0)
        } finally {
            picture.release()
        }
    }

    fun closeUp(maxSide: Int, zoom: Double): ByteArray {
        val s = settings ?: return ByteArray(0)
        if (!enabled) return ByteArray(0)
        val asked = Zoom.asked(zoom)
        val side = maxSide.coerceIn(SNAPSHOT_MIN, SNAPSHOT_MAX)
        if (s.testImage.isNotEmpty()) {
            val bytes = try {
                context.assets.open("samples/${s.testImage}").use { it.readBytes() }
            } catch (e: Exception) {
                return ByteArray(0)
            }
            val picture = Imgcodecs.imdecode(MatOfByte(*bytes), Imgcodecs.IMREAD_COLOR)
            return try {
                if (picture.empty()) ByteArray(0) else closeUp.fromPicture(picture, asked, side, "test picture ${s.testImage}")
            } finally {
                picture.release()
            }
        }
        synchronized(closeLock) {
            val made = provider ?: try {
                ProcessCameraProvider.getInstance(context).get(CLOSE_WAIT_S, java.util.concurrent.TimeUnit.SECONDS).also { provider = it }
            } catch (e: Exception) {
                Log.w(TAG, "no camera for a close look", e)
                return ByteArray(0)
            }
            main.post {
                closeLook = true
                closeCamera("a close look")
            }
            try {
                val cs = s.cameras.getValue("rear")
                return closeUp.take(made, asked, side, displayRotation(), cs.rotate, cs.mirror) { torch?.cameraChanged(it) }
            } finally {
                main.post {
                    closeLook = false
                    try {
                        made.unbindAll()
                    } catch (e: Exception) {
                        Log.w(TAG, "unbinding after the close look failed", e)
                    }
                    openCamera()
                }
            }
        }
    }

    fun closeUpInfo(): String = closeUp.info().put("busy", closeLook).toString()

    fun wantPrints(top: Int) {
        printsTop = top.coerceIn(0, 16)
    }

    fun hold(): String {
        val s = settings ?: return "{}"
        val pair = synchronized(frameLock) {
            val m = latest ?: return "{}"
            val id = ++heldIds
            val copy = m.clone()
            val meta = JSONObject(latestMeta.toString()).put("id", id)
            held[id] = copy to meta
            while (held.size > MAX_HELD) {
                val first = held.keys.first()
                held.remove(first)?.first?.release()
            }
            copy to meta
        }
        val meta = pair.second
        val camera = meta.optString("camera")
        val finder = tags
        if (finder != null && camera in s.tagsOn) {
            val gray = Mat()
            Imgproc.cvtColor(pair.first, gray, Imgproc.COLOR_BGR2GRAY)
            meta.put("tags", finder.find(gray, meta.optDouble("fov", 65.0)))
            gray.release()
        }
        return meta.toString()
    }

    fun embed(id: Int, boxesJson: String, size: Int): String {
        val finder = prints ?: return "[]"
        val picture = synchronized(frameLock) { held[id]?.first?.clone() } ?: return "[]"
        val list = JSONArray(boxesJson)
        val boxes = (0 until list.length()).map { i -> list.getJSONArray(i).let { b -> DoubleArray(4) { b.getDouble(it) } } }
        val started = System.nanoTime()
        val vecs = finder.embed(picture, boxes, size.coerceIn(32, 448))
        add("print", started)
        picture.release()
        return JSONArray(vecs.map { v -> JSONArray(v.map { Math.round(it * 1e6) / 1e6 }) }).toString()
    }

    fun propose(id: Int, score: Double): String {
        val s = settings ?: return "[]"
        if (s.classes <= 0) return "[]"
        val picture = synchronized(frameLock) { held[id]?.first?.clone() } ?: return "[]"
        val wanted = score.toFloat().coerceIn(0.05f, 0.9f)
        val current = proposer
        val finder = if (current != null && current.first == wanted) current.second else {
            current?.second?.close()
            Bench.slowFinder(files, choices.optString("slow", Bench.CPU), 1, s.classes, wanted).also { proposer = wanted to it }
        }
        val found = finder.find(picture)
        picture.release()
        return boxes(found, true).toString()
    }

    fun release(id: Int) {
        synchronized(frameLock) { held.remove(id)?.first?.release() }
    }

    private fun add(key: String, started: Long) {
        val took = (System.nanoTime() - started) / 1e6
        val old = ms[key]
        ms[key] = if (old == null) took else old * 0.8 + took * 0.2
    }

    private fun boxes(found: List<Det>, withClass: Boolean): JSONArray = JSONArray(found.map {
        JSONArray(if (withClass) listOf(it.x, it.y, it.w, it.h, it.score, it.cls) else listOf(it.x, it.y, it.w, it.h, it.score))
    })

    private fun send(kind: String, data: JSONObject) {
        ask(kind, data)
    }

    private fun ask(kind: String, data: JSONObject): Boolean {
        val target = sink ?: return false
        return try {
            target.callAttr(kind, data.toString())?.toBoolean() ?: false
        } catch (e: Throwable) {
            Log.w(TAG, "the brain did not take $kind", e)
            false
        }
    }

    fun status(): String = JSONObject()
        .put("enabled", enabled)
        .put("want", want)
        .put("open", open ?: JSONObject.NULL)
        .put("ready", ready)
        .put("fps", Math.round(fps * 10) / 10.0)
        .put("pace", pace.eyesFactor())
        .put("frames", frames)
        .put("ms", JSONObject(ms.mapValues { Math.round(it.value * 10) / 10.0 }))
        .put("problem", problem)
        .put("backends", choices)
        .put("timings", bench)
        .put("slow", JSONObject().put("passes", slow?.passes ?: 0).put("ms", slow?.lastMs ?: 0.0).put("busy", slow?.isBusy ?: false).put("backend", slow?.backend ?: JSONObject.NULL).put("problem", slow?.problem ?: ""))
        .put("speaking", JSONObject().put("on", settings?.speakingOn ?: false).put("reading", mouthsWanted()).put("reads", mouthReads).put("ms", Math.round((ms["mouth"] ?: 0.0) * 10) / 10.0).put("backend", mouths?.backend ?: JSONObject.NULL).put("problem", mouthProblem))
        .put("hazards", hazards?.let { JSONObject().put("passes", it.passes).put("ms", Math.round(it.lastMs * 10) / 10.0).put("every_s", it.everyS).put("backend", it.backend ?: JSONObject.NULL).put("problem", it.problem) } ?: JSONObject.NULL)
        .put("floor", floor?.status() ?: JSONObject.NULL)
        .put("close_up", closeUp.last)
        .put("abi", Build.SUPPORTED_ABIS.firstOrNull())
        .toString()

    companion object {
        const val TAG = "PebbleEyes"
        const val MAX_HELD = 4
        const val FRESH_S = 1.0
        const val SNAPSHOT_MIN = 64
        const val SNAPSHOT_MAX = 4096
        const val JPEG_QUALITY = 85
        const val CLOSE_WAIT_S = 3L
        const val NO_MOUTHS = "the mouth model would not load"
    }
}

object Frames {
    fun toBgr(image: ImageProxy, rotation: Int, mirror: Boolean): Mat {
        val plane = image.planes[0]
        val buffer = plane.buffer
        val width = image.width
        val height = image.height
        val rgba = Mat(height, width, CvType.CV_8UC4)
        val rowStride = plane.rowStride
        if (rowStride == width * 4) {
            val bytes = ByteArray(width * height * 4)
            buffer.rewind()
            buffer.get(bytes, 0, minOf(bytes.size, buffer.remaining()))
            rgba.put(0, 0, bytes)
        } else {
            val row = ByteArray(width * 4)
            for (y in 0 until height) {
                buffer.position(y * rowStride)
                buffer.get(row, 0, row.size)
                rgba.put(y, 0, row)
            }
        }
        val bgr = Mat()
        Imgproc.cvtColor(rgba, bgr, Imgproc.COLOR_RGBA2BGR)
        rgba.release()
        return orient(bgr, rotation, mirror)
    }

    fun orient(image: Mat, rotation: Int, mirror: Boolean): Mat {
        val turn = ((rotation % 360) + 360) % 360
        var out = image
        val code = when (turn) {
            90 -> Core.ROTATE_90_CLOCKWISE
            180 -> Core.ROTATE_180
            270 -> Core.ROTATE_90_COUNTERCLOCKWISE
            else -> -1
        }
        if (code >= 0) {
            val turned = Mat()
            Core.rotate(out, turned, code)
            out.release()
            out = turned
        }
        if (mirror) {
            val flipped = Mat()
            Core.flip(out, flipped, 1)
            out.release()
            out = flipped
        }
        return out
    }

    fun jpeg(image: Mat, maxSide: Int, quality: Int): ByteArray {
        val k = min(1.0, maxSide.toDouble() / max(image.cols(), image.rows()))
        val small = if (k < 1.0) {
            val w = max(1L, Math.round(image.cols() * k)).toDouble()
            val h = max(1L, Math.round(image.rows() * k)).toDouble()
            Mat().also { Imgproc.resize(image, it, Size(w, h), 0.0, 0.0, Imgproc.INTER_AREA) }
        } else {
            image
        }
        val bytes = MatOfByte()
        val ok = Imgcodecs.imencode(".jpg", small, bytes, MatOfInt(Imgcodecs.IMWRITE_JPEG_QUALITY, quality))
        val out = if (ok) bytes.toArray() else ByteArray(0)
        if (small !== image) small.release()
        bytes.release()
        return out
    }
}
