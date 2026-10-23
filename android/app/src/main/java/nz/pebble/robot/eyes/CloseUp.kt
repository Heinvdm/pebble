package nz.pebble.robot.eyes

import android.hardware.camera2.CameraCaptureSession
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CaptureRequest
import android.hardware.camera2.CaptureResult
import android.hardware.camera2.TotalCaptureResult
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.util.Size
import androidx.camera.camera2.interop.Camera2CameraInfo
import androidx.camera.camera2.interop.Camera2Interop
import androidx.camera.camera2.interop.ExperimentalCamera2Interop
import androidx.camera.core.Camera
import androidx.camera.core.CameraInfo
import androidx.camera.core.CameraSelector
import androidx.camera.core.CameraState
import androidx.camera.core.FocusMeteringAction
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.ImageProxy
import androidx.camera.core.SurfaceOrientedMeteringPointFactory
import androidx.camera.core.resolutionselector.AspectRatioStrategy
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.lifecycle.LifecycleOwner
import org.json.JSONArray
import org.json.JSONObject
import org.opencv.core.CvType
import org.opencv.core.Mat
import org.opencv.core.Rect
import org.opencv.imgcodecs.Imgcodecs
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference
import kotlin.math.atan
import kotlin.math.max
import kotlin.math.roundToInt

object Zoom {
    const val DEFAULT = 4.0
    const val MOST = 10.0

    fun asked(zoom: Double): Double = if (zoom.isFinite() && zoom > 0) zoom.coerceIn(1.0, MOST) else DEFAULT

    fun crop(asked: Double, reached: Double): Double {
        val got = if (reached.isFinite() && reached > 0) reached else 1.0
        return if (got >= asked - 0.01) 1.0 else asked / got
    }

    fun centre(width: Int, height: Int, factor: Double): IntArray {
        val w = max(1, (width / factor).roundToInt()).coerceAtMost(width)
        val h = max(1, (height / factor).roundToInt()).coerceAtMost(height)
        return intArrayOf((width - w) / 2, (height - h) / 2, w, h)
    }

    fun reduce(longSide: Int, crop: Double, maxSide: Int): Int {
        var best = 1
        for (step in intArrayOf(2, 4, 8)) if (longSide / step / crop >= maxSide) best = step
        return best
    }

    fun fovDeg(focalMm: Double, widthMm: Double): Double = if (focalMm > 0 && widthMm > 0) Math.toDegrees(2 * atan(widthMm / (2 * focalMm))) else Double.NaN
}

@androidx.annotation.OptIn(markerClass = [ExperimentalCamera2Interop::class])
class CloseUp(private val owner: LifecycleOwner) {
    private val main = Handler(Looper.getMainLooper())
    private val callbacks = Executors.newSingleThreadExecutor { Thread(it, "pebble-close-up") }
    @Volatile var last: JSONObject = JSONObject()
        private set
    @Volatile private var lenses: JSONArray? = null
    @Volatile private var range: JSONArray? = null

    fun info(): JSONObject = JSONObject()
        .put("lenses", lenses ?: JSONObject.NULL)
        .put("zoom_range", range ?: JSONObject.NULL)
        .put("last", last)

    fun fromPicture(picture: Mat, asked: Double, maxSide: Int, source: String): ByteArray {
        val started = System.nanoTime()
        val box = Zoom.centre(picture.cols(), picture.rows(), asked)
        val part = Mat(picture, Rect(box[0], box[1], box[2], box[3]))
        val out = Frames.jpeg(part, maxSide, QUALITY)
        part.release()
        last = JSONObject().put("asked", asked).put("lens_zoom", 1.0).put("digital", asked).put("lens", source).put("width", box[2]).put("height", box[3]).put("ms", Math.round((System.nanoTime() - started) / 1e5) / 10.0).put("bytes", out.size).put("problem", "")
        return out
    }

    fun take(provider: ProcessCameraProvider, asked: Double, maxSide: Int, rotation: Int, turn: Int, mirror: Boolean, rear: (Camera?) -> Unit): ByteArray {
        val started = System.nanoTime()
        val active = AtomicReference<String?>(null)
        val watcher = object : CameraCaptureSession.CaptureCallback() {
            override fun onCaptureCompleted(session: CameraCaptureSession, request: CaptureRequest, result: TotalCaptureResult) {
                result.get(CaptureResult.LOGICAL_MULTI_CAMERA_ACTIVE_PHYSICAL_ID)?.let { active.set(it) }
            }
        }
        val builder = ImageCapture.Builder()
            .setCaptureMode(ImageCapture.CAPTURE_MODE_MAXIMIZE_QUALITY)
            .setTargetRotation(rotation)
            .setResolutionSelector(
                ResolutionSelector.Builder()
                    .setAspectRatioStrategy(AspectRatioStrategy.RATIO_4_3_FALLBACK_AUTO_STRATEGY)
                    .setResolutionStrategy(ResolutionStrategy(Size(WIDTH, HEIGHT), ResolutionStrategy.FALLBACK_RULE_CLOSEST_LOWER_THEN_HIGHER))
                    .build(),
            )
        Camera2Interop.Extender(builder).setSessionCaptureCallback(watcher)
        val capture = builder.build()
        val camera = onMain {
            if (!provider.hasCamera(CameraSelector.DEFAULT_BACK_CAMERA)) throw IllegalStateException("this phone has no rear camera")
            provider.unbindAll()
            provider.bindToLifecycle(owner, CameraSelector.DEFAULT_BACK_CAMERA, capture)
        }
        if (camera == null) return failed(asked, "the rear camera would not open for a close look", started)
        rear(camera)
        try {
            if (!opened(camera)) return failed(asked, "the rear camera did not open in time", started)
            describe(camera.cameraInfo)
            val state = camera.cameraInfo.zoomState.value
            val most = state?.maxZoomRatio?.toDouble() ?: 1.0
            val least = state?.minZoomRatio?.toDouble() ?: 1.0
            val target = asked.coerceIn(least, max(least, most))
            if (target != 1.0) camera.cameraControl.setZoomRatio(target.toFloat()).get(ZOOM_MS, TimeUnit.MILLISECONDS)
            val reached = camera.cameraInfo.zoomState.value?.zoomRatio?.toDouble() ?: target
            val focused = focus(camera)
            val shot = shoot(capture)
            val crop = Zoom.crop(asked, reached)
            val made = finish(shot.bytes, shot.longSide, shot.degrees + turn, mirror, crop, maxSide)
            val lens = active.get()
            last = JSONObject()
                .put("asked", asked)
                .put("lens_zoom", Math.round(reached * 100) / 100.0)
                .put("digital", Math.round(crop * 100) / 100.0)
                .put("lens", lens ?: Camera2CameraInfo.from(camera.cameraInfo).cameraId)
                .put("lens_fov_deg", lensFov(lens) ?: JSONObject.NULL)
                .put("focused", focused ?: JSONObject.NULL)
                .put("shot", "${shot.width}x${shot.height}")
                .put("width", made.second.width)
                .put("height", made.second.height)
                .put("bytes", made.first.size)
                .put("ms", Math.round((System.nanoTime() - started) / 1e5) / 10.0)
                .put("problem", "")
            Log.i(TAG, "close look: $last")
            return made.first
        } catch (e: Exception) {
            return failed(asked, "the close look failed: ${e.cause?.message ?: e.message}", started)
        } finally {
            rear(null)
        }
    }

    private fun failed(asked: Double, why: String, started: Long): ByteArray {
        last = JSONObject().put("asked", asked).put("problem", why).put("ms", Math.round((System.nanoTime() - started) / 1e5) / 10.0)
        Log.w(TAG, why)
        return ByteArray(0)
    }

    private fun <T> onMain(block: () -> T): T? {
        val done = CountDownLatch(1)
        val out = AtomicReference<T?>(null)
        main.post {
            try {
                out.set(block())
            } catch (e: Exception) {
                Log.w(TAG, "the close look could not start", e)
            } finally {
                done.countDown()
            }
        }
        return if (done.await(BIND_MS, TimeUnit.MILLISECONDS)) out.get() else null
    }

    private fun opened(camera: Camera): Boolean {
        val until = System.nanoTime() + OPEN_MS * 1_000_000
        while (System.nanoTime() < until) {
            if (camera.cameraInfo.cameraState.value?.type == CameraState.Type.OPEN) return true
            Thread.sleep(50)
        }
        return camera.cameraInfo.cameraState.value?.type == CameraState.Type.OPEN
    }

    private fun describe(info: CameraInfo) {
        if (lenses != null) return
        val out = JSONArray()
        val physical = try {
            info.physicalCameraInfos
        } catch (e: Exception) {
            emptySet()
        }
        for (one in listOf(info) + physical.filter { it != info }) {
            try {
                val c2 = Camera2CameraInfo.from(one)
                val focal = c2.getCameraCharacteristic(CameraCharacteristics.LENS_INFO_AVAILABLE_FOCAL_LENGTHS)?.firstOrNull()?.toDouble() ?: Double.NaN
                val sensor = c2.getCameraCharacteristic(CameraCharacteristics.SENSOR_INFO_PHYSICAL_SIZE)
                val pixels = c2.getCameraCharacteristic(CameraCharacteristics.SENSOR_INFO_PIXEL_ARRAY_SIZE)
                val fov = Zoom.fovDeg(focal, sensor?.width?.toDouble() ?: Double.NaN)
                out.put(
                    JSONObject()
                        .put("id", c2.cameraId)
                        .put("logical", one == info)
                        .put("focal_mm", if (focal.isNaN()) JSONObject.NULL else Math.round(focal * 100) / 100.0)
                        .put("fov_deg", if (fov.isNaN()) JSONObject.NULL else Math.round(fov * 10) / 10.0)
                        .put("pixels", pixels?.let { "${it.width}x${it.height}" } ?: JSONObject.NULL)
                        .put("intrinsic_zoom", one.intrinsicZoomRatio.toDouble().let { if (it.isNaN() || it <= 0) JSONObject.NULL else Math.round(it * 100) / 100.0 }),
                )
            } catch (e: Exception) {
                Log.w(TAG, "a lens could not be described", e)
            }
        }
        lenses = out
        val state = info.zoomState.value
        if (state != null) range = JSONArray().put(Math.round(state.minZoomRatio * 100) / 100.0).put(Math.round(state.maxZoomRatio * 100) / 100.0)
        Log.i(TAG, "rear lenses: $out, zoom ${range ?: "unknown"}")
    }

    private fun lensFov(id: String?): Double? {
        val all = lenses ?: return null
        for (i in 0 until all.length()) {
            val lens = all.getJSONObject(i)
            if (lens.optString("id") == id && !lens.isNull("fov_deg")) return lens.getDouble("fov_deg")
        }
        return null
    }

    private fun focus(camera: Camera): Boolean? {
        val point = SurfaceOrientedMeteringPointFactory(1f, 1f).createPoint(0.5f, 0.5f)
        val action = FocusMeteringAction.Builder(point, FocusMeteringAction.FLAG_AF or FocusMeteringAction.FLAG_AE).setAutoCancelDuration(3, TimeUnit.SECONDS).build()
        if (!camera.cameraInfo.isFocusMeteringSupported(action)) return null
        return try {
            camera.cameraControl.startFocusAndMetering(action).get(FOCUS_MS, TimeUnit.MILLISECONDS).isFocusSuccessful
        } catch (e: Exception) {
            false
        }
    }

    private class Shot(val bytes: ByteArray, val degrees: Int, val width: Int, val height: Int) {
        val longSide: Int get() = max(width, height)
    }

    private fun shoot(capture: ImageCapture): Shot {
        val done = CountDownLatch(1)
        val shot = AtomicReference<Shot?>(null)
        val error = AtomicReference<String?>(null)
        capture.takePicture(callbacks, object : ImageCapture.OnImageCapturedCallback() {
            override fun onCaptureSuccess(image: ImageProxy) {
                try {
                    val buffer = image.planes[0].buffer
                    buffer.rewind()
                    shot.set(Shot(ByteArray(buffer.remaining()).also { buffer.get(it) }, image.imageInfo.rotationDegrees, image.width, image.height))
                } catch (e: Exception) {
                    error.set(e.message)
                } finally {
                    image.close()
                    done.countDown()
                }
            }

            override fun onError(exception: ImageCaptureException) {
                error.set(exception.message ?: "error ${exception.imageCaptureError}")
                done.countDown()
            }
        })
        if (!done.await(SHOOT_MS, TimeUnit.MILLISECONDS)) throw IllegalStateException("the picture took too long")
        return shot.get() ?: throw IllegalStateException(error.get() ?: "no picture came back")
    }

    private fun finish(jpeg: ByteArray, longSide: Int, rotation: Int, mirror: Boolean, crop: Double, maxSide: Int): Pair<ByteArray, Size> {
        val raw = Mat(1, jpeg.size, CvType.CV_8UC1)
        raw.put(0, 0, jpeg)
        val flags = when (Zoom.reduce(longSide, crop, maxSide)) {
            8 -> Imgcodecs.IMREAD_REDUCED_COLOR_8
            4 -> Imgcodecs.IMREAD_REDUCED_COLOR_4
            2 -> Imgcodecs.IMREAD_REDUCED_COLOR_2
            else -> Imgcodecs.IMREAD_COLOR
        } or Imgcodecs.IMREAD_IGNORE_ORIENTATION
        val decoded = Imgcodecs.imdecode(raw, flags)
        raw.release()
        if (decoded.empty()) throw IllegalStateException("the camera's picture could not be read")
        var picture = Frames.orient(decoded, rotation, mirror)
        if (crop > 1.0) {
            val box = Zoom.centre(picture.cols(), picture.rows(), crop)
            val part = Mat(picture, Rect(box[0], box[1], box[2], box[3])).clone()
            picture.release()
            picture = part
        }
        val shown = Size(picture.cols(), picture.rows())
        val out = Frames.jpeg(picture, maxSide, QUALITY)
        picture.release()
        return out to shown
    }

    fun shutdown() {
        callbacks.shutdown()
    }

    companion object {
        const val TAG = "PebbleCloseUp"
        const val WIDTH = 4032
        const val HEIGHT = 3024
        const val QUALITY = 90
        const val BIND_MS = 3_000L
        const val OPEN_MS = 3_000L
        const val ZOOM_MS = 2_000L
        const val FOCUS_MS = 2_500L
        const val SHOOT_MS = 5_000L
    }
}
