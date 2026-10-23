package nz.pebble.robot.eyes

import android.content.Context
import android.os.Build
import android.util.Log
import nz.pebble.robot.BuildConfig
import org.json.JSONObject
import org.opencv.core.Mat
import java.io.File

object Bench {
    const val TAG = "PebbleEyesBench"
    const val OPENCV = "opencv"
    const val XNNPACK = "onnxruntime-xnnpack"
    const val CPU = "onnxruntime-cpu"
    const val NNAPI = "onnxruntime-nnapi"
    val ALL = listOf(XNNPACK, CPU, OPENCV, NNAPI)
    val DEPTH_BACKENDS = listOf(XNNPACK, CPU, NNAPI)
    const val TOO_SLOW_MS = 1500.0
    const val FACE_MODEL = "face_detection_yunet_2023mar.onnx"
    const val THING_MODEL = "object_detection_nanodet_2022nov.onnx"
    const val SLOW_MODEL = "objects.onnx"
    const val POSE_MODEL = "rtmpose_t_body7_256x192.onnx"
    const val PRINT_MODEL = "prints.onnx"
    const val HAZARD_MODEL = "hazards.onnx"
    const val HAZARD_WORDS = "hazards_vocab.json"
    const val EYES_CHOICE = "eyes-choice.json"
    const val FLOOR_CHOICE = "floor-choice.json"

    class Chosen(val faces: FaceFinder?, val things: NanoDet?, val pose: PoseFinder?, val prints: PrintFinder?, val choices: JSONObject, val timings: JSONObject)

    fun forget(context: Context) {
        File(context.noBackupFilesDir, EYES_CHOICE).delete()
        File(context.noBackupFilesDir, FLOOR_CHOICE).delete()
    }

    fun faceFinder(files: ModelFiles, backend: String, threads: Int): FaceFinder = when (backend) {
        OPENCV -> CvFaces(files.path(FACE_MODEL))
        else -> OrtFaces(files.path(FACE_MODEL), backend.removePrefix("onnxruntime-"), threads)
    }

    fun runner(files: ModelFiles, model: String, backend: String, threads: Int): Runner = when (backend) {
        OPENCV -> CvRunner(files.path(model))
        else -> OrtRunner(files.path(model), backend.removePrefix("onnxruntime-"), threads)
    }

    fun slowFinder(files: ModelFiles, backend: String, threads: Int, classes: Int, score: Float): Yoloe {
        val size = try {
            JSONObject(files.text("objects_vocab.json")).optInt("imgsz", 416)
        } catch (e: Exception) {
            416
        }
        return Yoloe(runner(files, SLOW_MODEL, backend, threads), size, classes, score)
    }

    fun hazardFinder(files: ModelFiles, backend: String, threads: Int, classes: Int, score: Float): Yoloe {
        val size = try {
            JSONObject(files.text(HAZARD_WORDS)).optInt("imgsz", 416)
        } catch (e: Exception) {
            416
        }
        return try {
            Yoloe(runner(files, HAZARD_MODEL, backend, threads), size, classes, score)
        } catch (e: Throwable) {
            if (backend == CPU) throw e
            Log.w(TAG, "the hazard model would not run on $backend; using $CPU", e)
            Yoloe(runner(files, HAZARD_MODEL, CPU, threads), size, classes, score)
        }
    }

    fun depthFinder(context: Context, files: ModelFiles, s: Eyes.Settings): Depth {
        val cache = File(context.noBackupFilesDir, FLOOR_CHOICE)
        val key = "${BuildConfig.VERSION_CODE}/${Build.MODEL}/${Build.SUPPORTED_ABIS.firstOrNull()}/${s.floorThreads}"
        val saved = try {
            if (cache.exists()) JSONObject(cache.readText()).takeIf { it.optString("key") == key && it.optString("choice") in DEPTH_BACKENDS } else null
        } catch (e: Exception) {
            null
        }
        val names = when {
            s.backend in DEPTH_BACKENDS -> listOf(s.backend)
            saved != null -> listOf(saved.getString("choice"))
            else -> listOf(XNNPACK, CPU)
        }
        val path = files.path(Floor.MODEL)
        fun make(name: String) = Depth(OrtRunner(path, name.removePrefix("onnxruntime-"), s.floorThreads))
        if (names.size == 1) {
            val only = names.first()
            return try {
                make(only).also { it.timings = saved?.optJSONObject("timings") ?: JSONObject().put(only, "chosen") }
            } catch (e: Throwable) {
                if (only == CPU) throw e
                Log.w(TAG, "the depth model would not load on $only; using $CPU", e)
                make(CPU).also { it.timings = JSONObject().put(only, "would not load: ${e.message?.take(120)}") }
            }
        }
        val timings = JSONObject()
        val sample = Mat.zeros(Floor.ROWS * 2, Floor.COLS * 2, org.opencv.core.CvType.CV_8UC3)
        var best: String? = null
        var bestMs = Double.MAX_VALUE
        for (name in names) {
            val made = try {
                make(name)
            } catch (e: Throwable) {
                Log.w(TAG, "the depth model would not load on $name", e)
                timings.put(name, "would not load: ${e.message?.take(120)}")
                continue
            }
            try {
                made.run(sample, 0.0)
                val took = timed { made.run(sample, 0.0) }
                timings.put(name, Math.round(took * 10) / 10.0)
                if (took < bestMs) {
                    best = name
                    bestMs = took
                }
            } catch (e: Throwable) {
                timings.put(name, "failed: ${e.message?.take(120)}")
            } finally {
                made.close()
            }
        }
        sample.release()
        val chosen = best ?: throw IllegalStateException("the depth model would not run: $timings")
        try {
            nz.pebble.robot.Atomic.write(cache, JSONObject().put("key", key).put("choice", chosen).put("timings", timings).toString(2).toByteArray())
        } catch (e: Exception) {
            Log.w(TAG, "could not keep the floor scan's choice", e)
        }
        Log.i(TAG, "depth timings (ms): $timings, chose $chosen")
        return make(chosen).also { it.timings = timings }
    }

    fun choose(context: Context, s: Eyes.Settings, files: ModelFiles, sample: Mat): Chosen {
        val cache = File(context.noBackupFilesDir, EYES_CHOICE)
        val key = "${BuildConfig.VERSION_CODE}/${Build.MODEL}/${Build.SUPPORTED_ABIS.firstOrNull()}/${s.threads}/${s.slowThreads}"
        val saved = try {
            if (cache.exists()) JSONObject(cache.readText()).takeIf { it.optString("key") == key } else null
        } catch (e: Exception) {
            null
        }
        val fixed = s.backend != "auto"
        fun names(part: String): List<String> = when {
            fixed -> listOf(s.backend)
            saved?.optJSONObject("choices")?.has(part) == true -> listOf(saved.getJSONObject("choices").getString(part))
            else -> ALL
        }
        val timings = JSONObject()
        val choices = JSONObject()
        val faces = pick("faces", names("faces"), { faceFinder(files, it, s.threads) }, { it.find(sample) }, timings)
        faces?.let { choices.put("faces", it.first) }
        val things = pick("things", names("things"), { NanoDet(runner(files, THING_MODEL, it, s.threads)) }, { it.find(sample) }, timings)
        things?.let { choices.put("things", it.first) }
        val person = Det(0.3f, 0.1f, 0.4f, 0.8f, 1f)
        val pose = if (s.pose) pick("pose", names("pose"), { PoseFinder(runner(files, POSE_MODEL, it, s.threads)) }, { it.points(sample, person) }, timings) else null
        pose?.let { choices.put("pose", it.first) }
        val printNames = names("prints").filter { it != OPENCV }.ifEmpty { listOf(CPU) }
        val prints = if (s.prints) pick("prints", printNames, { PrintFinder(OrtRunner(files.path(PRINT_MODEL), it.removePrefix("onnxruntime-"), s.threads)) }, { it.embed(sample, listOf(doubleArrayOf(0.3, 0.1, 0.4, 0.8))) }, timings) else null
        prints?.let { choices.put("prints", it.first) }
        if (s.slowOn && s.classes > 0) {
            val slow = pick("slow", names("slow"), { slowFinder(files, it, s.slowThreads, s.classes, s.slowScore) }, { it.find(sample) }, timings)
            slow?.let {
                choices.put("slow", it.first)
                it.second.close()
            }
        }
        if (!fixed) {
            try {
                nz.pebble.robot.Atomic.write(cache, JSONObject().put("key", key).put("choices", choices).put("timings", timings).toString(2).toByteArray())
            } catch (e: Exception) {
                Log.w(TAG, "could not keep the eyes' choices", e)
            }
        }
        Log.i(TAG, "eyes timings (ms): $timings")
        return Chosen(faces?.second, things?.second, pose?.second, prints?.second, choices, timings)
    }

    private fun <T : AutoCloseable> pick(label: String, names: List<String>, build: (String) -> T, run: (T) -> Unit, timings: JSONObject): Pair<String, T>? {
        var best: Pair<String, T>? = null
        var bestMs = Double.MAX_VALUE
        for (name in names) {
            val made = try {
                build(name)
            } catch (e: Throwable) {
                timings.put("$label $name", "would not load: ${e.message?.take(120)}")
                continue
            }
            try {
                val first = timed { run(made) }
                if (first > TOO_SLOW_MS && names.size > 1) {
                    timings.put("$label $name", "too slow (${first.toInt()} ms for the first picture)")
                    made.close()
                    continue
                }
                val average = (1..3).map { timed { run(made) } }.average()
                timings.put("$label $name", Math.round(average * 10) / 10.0)
                if (average < bestMs) {
                    best?.second?.close()
                    best = name to made
                    bestMs = average
                } else {
                    made.close()
                }
            } catch (e: Throwable) {
                timings.put("$label $name", "failed: ${e.message?.take(120)}")
                try {
                    made.close()
                } catch (ignored: Throwable) {
                    Log.d(TAG, "closing $name failed")
                }
            }
        }
        return best
    }

    private inline fun timed(block: () -> Unit): Double {
        val started = System.nanoTime()
        block()
        return (System.nanoTime() - started) / 1e6
    }
}
