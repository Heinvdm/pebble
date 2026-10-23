package nz.pebble.robot.eyes

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import android.content.Context
import org.opencv.calib3d.Calib3d
import org.opencv.core.Core
import org.opencv.core.CvType
import org.opencv.core.Mat
import org.opencv.core.MatOfDouble
import org.opencv.core.MatOfPoint2f
import org.opencv.core.MatOfPoint3f
import org.opencv.core.Point
import org.opencv.core.Point3
import org.opencv.core.Scalar
import org.opencv.core.Size
import org.opencv.dnn.Dnn
import org.opencv.dnn.Net
import org.opencv.imgproc.Imgproc
import org.opencv.objdetect.ArucoDetector
import org.opencv.objdetect.DetectorParameters
import org.opencv.objdetect.FaceDetectorYN
import org.opencv.objdetect.Objdetect
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.nio.FloatBuffer
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt
import kotlin.math.tan

class ModelFiles(private val context: Context) {
    private val folder = File(context.noBackupFilesDir, "models")

    fun path(name: String): File {
        folder.mkdirs()
        val target = File(folder, name)
        val size = context.assets.openFd("models/$name").use { it.length }
        if (!target.exists() || target.length() != size) {
            val tmp = File(folder, ".$name.tmp")
            context.assets.open("models/$name").use { input -> tmp.outputStream().use { input.copyTo(it) } }
            tmp.renameTo(target)
        }
        return target
    }

    fun text(name: String): String = context.assets.open("models/$name").bufferedReader().use { it.readText() }
}

class Tensor(val name: String, val shape: LongArray, val data: FloatArray)

interface Runner : AutoCloseable {
    val backend: String
    fun run(chw: FloatArray, height: Int, width: Int): List<Tensor>
}

class OrtRunner(path: File, private val provider: String, threads: Int) : Runner {
    private val env = OrtEnvironment.getEnvironment()
    private val session: OrtSession
    private val input: String
    override val backend = "onnxruntime-$provider"

    init {
        val options = OrtSession.SessionOptions()
        options.setIntraOpNumThreads(threads)
        options.setInterOpNumThreads(1)
        options.setExecutionMode(OrtSession.SessionOptions.ExecutionMode.SEQUENTIAL)
        options.setOptimizationLevel(OrtSession.SessionOptions.OptLevel.ALL_OPT)
        when (provider) {
            "xnnpack" -> options.addXnnpack(mapOf("intra_op_num_threads" to threads.toString()))
            "nnapi" -> options.addNnapi()
        }
        session = env.createSession(path.path, options)
        input = session.inputNames.first()
    }

    override fun run(chw: FloatArray, height: Int, width: Int): List<Tensor> = runBatch(chw, 1, height, width)

    fun runBatch(nchw: FloatArray, count: Int, height: Int, width: Int): List<Tensor> {
        OnnxTensor.createTensor(env, FloatBuffer.wrap(nchw), longArrayOf(count.toLong(), 3, height.toLong(), width.toLong())).use { tensor ->
            session.run(mapOf(input to tensor)).use { result ->
                return result.map { entry ->
                    val value = entry.value as OnnxTensor
                    val buffer = value.floatBuffer
                    val data = FloatArray(buffer.remaining())
                    buffer.get(data)
                    Tensor(entry.key, value.info.shape, data)
                }
            }
        }
    }

    override fun close() = session.close()
}

class CvRunner(path: File) : Runner {
    private val net: Net = Dnn.readNetFromONNX(path.path)
    private val outputs = net.unconnectedOutLayersNames
    override val backend = "opencv-dnn"

    init {
        net.setPreferableBackend(Dnn.DNN_BACKEND_OPENCV)
        net.setPreferableTarget(Dnn.DNN_TARGET_CPU)
    }

    override fun run(chw: FloatArray, height: Int, width: Int): List<Tensor> {
        val blob = Mat(intArrayOf(1, 3, height, width), CvType.CV_32F)
        blob.put(intArrayOf(0, 0, 0, 0), chw)
        net.setInput(blob)
        val found = ArrayList<Mat>()
        net.forward(found, outputs)
        blob.release()
        return found.mapIndexed { index, mat ->
            val dims = IntArray(mat.dims()) { mat.size(it) }
            val data = FloatArray(mat.total().toInt())
            mat.reshape(1, 1).get(0, 0, data)
            mat.release()
            Tensor(outputs.getOrElse(index) { "out$index" }, LongArray(dims.size) { dims[it].toLong() }, data)
        }
    }

    override fun close() = Unit
}

object Pixels {
    fun chw(hwc: FloatArray, height: Int, width: Int): FloatArray {
        val plane = height * width
        val out = FloatArray(plane * 3)
        for (i in 0 until plane) {
            out[i] = hwc[i * 3]
            out[plane + i] = hwc[i * 3 + 1]
            out[2 * plane + i] = hwc[i * 3 + 2]
        }
        return out
    }

    fun floats(mat: Mat): FloatArray {
        val f = Mat()
        mat.convertTo(f, CvType.CV_32FC3)
        val data = FloatArray((f.total() * f.channels()).toInt())
        f.get(0, 0, data)
        f.release()
        return data
    }
}

interface FaceFinder : AutoCloseable {
    val backend: String
    fun find(bgr: Mat): List<Det>
}

class CvFaces(path: File, private val width: Int = 320, score: Float = 0.6f) : FaceFinder {
    private val detector: FaceDetectorYN = FaceDetectorYN.create(path.path, "", Size(320.0, 240.0), score, 0.3f, 50)
    private var size: Size? = null
    override val backend = "opencv-yunet"

    override fun find(bgr: Mat): List<Det> {
        val k = min(1.0, width.toDouble() / bgr.cols())
        val small = Mat()
        if (k < 1.0) Imgproc.resize(bgr, small, Size((bgr.cols() * k).roundToInt().toDouble(), (bgr.rows() * k).roundToInt().toDouble()), 0.0, 0.0, Imgproc.INTER_AREA) else bgr.copyTo(small)
        val now = Size(small.cols().toDouble(), small.rows().toDouble())
        if (size != now) {
            detector.inputSize = now
            size = now
        }
        val faces = Mat()
        detector.detect(small, faces)
        val out = ArrayList<Det>()
        val row = FloatArray(15)
        for (i in 0 until faces.rows()) {
            faces.get(i, 0, row)
            val x0 = max(0f, row[0] / small.cols())
            val y0 = max(0f, row[1] / small.rows())
            val marks = FloatArray(10) { j -> row[4 + j] / (if (j % 2 == 0) small.cols() else small.rows()) }
            out += Det(x0, y0, min(1f - x0, row[2] / small.cols()), min(1f - y0, row[3] / small.rows()), row[14], marks = marks)
        }
        small.release()
        faces.release()
        return out
    }

    override fun close() = Unit
}

class OrtFaces(path: File, provider: String, threads: Int, private val score: Float = 0.6f) : FaceFinder {
    private val runner = OrtRunner(path, provider, threads)
    override val backend = "${runner.backend}-yunet"

    override fun find(bgr: Mat): List<Det> {
        val k = min(SIZE.toDouble() / bgr.cols(), SIZE.toDouble() / bgr.rows())
        val rw = max(1, (bgr.cols() * k).roundToInt())
        val rh = max(1, (bgr.rows() * k).roundToInt())
        val canvas = Mat.zeros(SIZE, SIZE, CvType.CV_8UC3)
        val resized = Mat()
        Imgproc.resize(bgr, resized, Size(rw.toDouble(), rh.toDouble()), 0.0, 0.0, Imgproc.INTER_AREA)
        resized.copyTo(canvas.submat(0, rh, 0, rw))
        val outputs = runner.run(Pixels.chw(Pixels.floats(canvas), SIZE, SIZE), SIZE, SIZE)
        canvas.release()
        resized.release()
        val named = outputs.associateBy { it.name }
        fun part(kind: String) = Decode.YUNET_STRIDES.map { named["${kind}_$it"]?.data ?: FloatArray(0) }
        val found = Decode.yunet(part("cls"), part("obj"), part("bbox"), SIZE, SIZE, score, kps = part("kps"))
        return found.map {
            val x0 = (it.x / rw).coerceIn(0f, 1f)
            val y0 = (it.y / rh).coerceIn(0f, 1f)
            val marks = it.marks?.let { m -> FloatArray(10) { j -> m[j] / (if (j % 2 == 0) rw else rh) } }
            Det(x0, y0, min(1f - x0, it.w / rw), min(1f - y0, it.h / rh), it.score, marks = marks)
        }
    }

    override fun close() = runner.close()

    companion object {
        const val SIZE = 640
    }
}

class NanoDet(private val runner: Runner, private val personScore: Float = 0.4f, private val thingScore: Float = 0.45f) : AutoCloseable {
    val backend get() = runner.backend

    fun find(bgr: Mat): List<Det> {
        val size = Decode.NANODET_SIZE
        val k = min(size.toDouble() / bgr.cols(), size.toDouble() / bgr.rows())
        val rw = max(1, (bgr.cols() * k).roundToInt())
        val rh = max(1, (bgr.rows() * k).roundToInt())
        val resized = Mat()
        Imgproc.resize(bgr, resized, Size(rw.toDouble(), rh.toDouble()), 0.0, 0.0, Imgproc.INTER_AREA)
        val pixels = Pixels.floats(resized)
        resized.release()
        val hwc = FloatArray(size * size * 3)
        for (y in 0 until rh) {
            for (x in 0 until rw) {
                val src = (y * rw + x) * 3
                val dst = (y * size + x) * 3
                for (c in 0 until 3) hwc[dst + c] = (pixels[src + c] - MEAN[c]) / STD[c]
            }
        }
        val outputs = runner.run(Pixels.chw(hwc, size, size), size, size)
        val scores = HashMap<Int, FloatArray>()
        val boxes = HashMap<Int, FloatArray>()
        for (t in outputs) {
            val last = t.shape.last().toInt()
            val n = t.data.size / last
            if (last == Decode.NANODET_CLASSES) scores[n] = t.data
            if (last == 4 * Decode.NANODET_BINS) boxes[n] = t.data
        }
        return Decode.nanodet(scores, boxes, rw, rh, personScore, thingScore).map {
            val x0 = it.x / rw
            val y0 = it.y / rh
            Det(x0, y0, min(1f - x0, it.w / rw), min(1f - y0, it.h / rh), it.score, it.cls)
        }
    }

    override fun close() = runner.close()

    companion object {
        val MEAN = floatArrayOf(103.53f, 116.28f, 123.675f)
        val STD = floatArrayOf(57.375f, 57.12f, 58.395f)
    }
}

class Yoloe(private val runner: Runner, private val size: Int, private val classes: Int, private val score: Float) : AutoCloseable {
    val backend get() = runner.backend

    fun find(bgr: Mat): List<Det> {
        val w = bgr.cols()
        val h = bgr.rows()
        val k = min(size.toDouble() / w, size.toDouble() / h)
        val rw = max(1, (w * k).roundToInt())
        val rh = max(1, (h * k).roundToInt())
        val left = (size - rw) / 2
        val top = (size - rh) / 2
        val canvas = Mat(size, size, CvType.CV_8UC3, Scalar(PAD, PAD, PAD))
        val resized = Mat()
        Imgproc.resize(bgr, resized, Size(rw.toDouble(), rh.toDouble()), 0.0, 0.0, Imgproc.INTER_AREA)
        resized.copyTo(canvas.submat(top, top + rh, left, left + rw))
        Imgproc.cvtColor(canvas, canvas, Imgproc.COLOR_BGR2RGB)
        val pixels = Pixels.floats(canvas)
        canvas.release()
        resized.release()
        for (i in pixels.indices) pixels[i] /= 255f
        val out = runner.run(Pixels.chw(pixels, size, size), size, size).first()
        val channels = out.shape[out.shape.size - 2].toInt()
        val anchors = out.shape.last().toInt()
        return Decode.yoloe(out.data, channels, anchors, classes, score).mapNotNull {
            val x0 = max(0f, ((it.x - left) / k / w).toFloat())
            val y0 = max(0f, ((it.y - top) / k / h).toFloat())
            val x2 = min(1f, ((it.x + it.w - left) / k / w).toFloat())
            val y2 = min(1f, ((it.y + it.h - top) / k / h).toFloat())
            if (x2 <= x0 || y2 <= y0) null else Det(x0, y0, x2 - x0, y2 - y0, it.score, it.cls)
        }
    }

    override fun close() = runner.close()

    companion object {
        const val PAD = 114.0
    }
}

class TagFinder(private val tagId: Int, sizeM: Double) {
    private val detector: ArucoDetector
    private val square: MatOfPoint3f

    init {
        val params = DetectorParameters()
        params._cornerRefinementMethod = Objdetect.CORNER_REFINE_SUBPIX
        detector = ArucoDetector(Objdetect.getPredefinedDictionary(Objdetect.DICT_APRILTAG_36h11), params)
        val half = sizeM / 2
        square = MatOfPoint3f(Point3(-half, half, 0.0), Point3(half, half, 0.0), Point3(half, -half, 0.0), Point3(-half, -half, 0.0))
    }

    fun find(gray: Mat, fovDeg: Double): JSONArray {
        val corners = ArrayList<Mat>()
        val ids = Mat()
        detector.detectMarkers(gray, corners, ids)
        val out = JSONArray()
        if (ids.empty()) return out
        val w = gray.cols().toDouble()
        val h = gray.rows().toDouble()
        val f = (w / 2) / tan(Math.toRadians(fovDeg) / 2)
        val camera = Mat(3, 3, CvType.CV_64F)
        camera.put(0, 0, f, 0.0, w / 2, 0.0, f, h / 2, 0.0, 0.0, 1.0)
        val noDistortion = MatOfDouble()
        for (i in 0 until ids.rows()) {
            val id = ids.get(i, 0)[0].toInt()
            if (id != tagId) continue
            val quad = corners[i]
            val points = Array(4) { j -> quad.get(0, j).let { Point(it[0], it[1]) } }
            val rvecs = ArrayList<Mat>()
            val tvecs = ArrayList<Mat>()
            val errors = Mat()
            val solved = try {
                Calib3d.solvePnPGeneric(square, MatOfPoint2f(*points), camera, noDistortion, rvecs, tvecs, false, Calib3d.SOLVEPNP_IPPE_SQUARE, Mat(), Mat(), errors)
            } catch (e: Exception) {
                0
            }
            if (solved <= 0) continue
            val poses = JSONArray()
            for (k in rvecs.indices) {
                val rotation = Mat()
                Calib3d.Rodrigues(rvecs[k], rotation)
                val t = DoubleArray(3) { tvecs[k].get(it, 0)[0] }
                val n = DoubleArray(3) { rotation.get(it, 2)[0] }
                val r = DoubleArray(9) { rotation.get(it / 3, it % 3)[0] }
                val err = if (errors.total() > k) errors.get(k, 0)?.get(0) ?: 0.0 else 0.0
                poses.put(JSONObject().put("t", JSONArray(t.toList())).put("n", JSONArray(n.toList())).put("r", JSONArray(r.toList())).put("err", err))
                rotation.release()
            }
            var px = 0.0
            for (j in 0 until 4) {
                val a = points[j]
                val b = points[(j + 1) % 4]
                px += Math.hypot(a.x - b.x, a.y - b.y)
            }
            out.put(JSONObject().put("id", id).put("px", px / 4).put("poses", poses))
        }
        corners.forEach { it.release() }
        ids.release()
        return out
    }

    companion object {
        fun threads(count: Int) = Core.setNumThreads(count)
    }
}
