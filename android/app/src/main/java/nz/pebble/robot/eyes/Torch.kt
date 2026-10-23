package nz.pebble.robot.eyes

import android.content.Context
import android.hardware.camera2.CameraAccessException
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.util.Log
import androidx.camera.core.Camera
import androidx.camera.core.TorchState
import org.json.JSONObject
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.math.roundToInt

object TorchRules {
    const val DEFAULT_S = 600.0
    const val LONGEST_S = 3_600.0

    fun seconds(asked: Double): Double = if (asked.isFinite() && asked > 0) asked.coerceAtMost(LONGEST_S) else DEFAULT_S

    fun step(fraction: Double, maxLevel: Int): Int {
        if (maxLevel <= 1) return 1
        val f = if (fraction.isFinite()) fraction.coerceIn(0.0, 1.0) else 1.0
        return (1 + f * (maxLevel - 1)).roundToInt().coerceIn(1, maxLevel)
    }

    fun reason(error: CameraAccessException): String = when (error.reason) {
        CameraAccessException.CAMERA_IN_USE -> "the rear camera is in use"
        CameraAccessException.MAX_CAMERAS_IN_USE -> "too many cameras are in use"
        CameraAccessException.CAMERA_DISABLED -> "the camera is switched off by policy"
        CameraAccessException.CAMERA_DISCONNECTED -> "the camera is not there"
        else -> "camera error ${error.reason}"
    }
}

class Torch(context: Context, private val hot: () -> Boolean) {
    private val manager: CameraManager? = context.getSystemService(CameraManager::class.java)
    private val main = Handler(Looper.getMainLooper())
    private val id: String? = find()
    private val maxLevel: Int = levels()
    private var wanted = false
    private var fraction = 1.0
    private var until = 0L
    private var lit = false
    private var usable = true
    private var through = ""
    private var problem = ""
    private var ended = ""
    private var camera: Camera? = null

    private val callback = object : CameraManager.TorchCallback() {
        override fun onTorchModeChanged(cameraId: String, enabled: Boolean) {
            if (cameraId != id) return
            lit = enabled
            usable = true
        }

        override fun onTorchModeUnavailable(cameraId: String) {
            if (cameraId == id) usable = false
        }
    }

    private val check = object : Runnable {
        override fun run() {
            if (!wanted) return
            apply()
        }
    }

    init {
        if (id != null) {
            try {
                manager?.registerTorchCallback(callback, main)
            } catch (e: Exception) {
                Log.w(TAG, "could not follow the torch", e)
            }
        }
    }

    private fun find(): String? = try {
        manager?.cameraIdList?.firstOrNull { name ->
            val c = manager.getCameraCharacteristics(name)
            c.get(CameraCharacteristics.LENS_FACING) == CameraCharacteristics.LENS_FACING_BACK && c.get(CameraCharacteristics.FLASH_INFO_AVAILABLE) == true
        }
    } catch (e: Exception) {
        Log.w(TAG, "could not look for a torch", e)
        null
    }

    private fun levels(): Int {
        val name = id ?: return 0
        if (Build.VERSION.SDK_INT < 33) return 1
        return try {
            manager?.getCameraCharacteristics(name)?.get(CameraCharacteristics.FLASH_INFO_STRENGTH_MAXIMUM_LEVEL) ?: 1
        } catch (e: Exception) {
            1
        }
    }

    fun set(on: Boolean, level: Double, seconds: Double): JSONObject {
        val done = CountDownLatch(1)
        main.post {
            wanted = on
            fraction = if (level.isFinite()) level.coerceIn(0.0, 1.0) else 1.0
            until = SystemClock.elapsedRealtime() + (TorchRules.seconds(seconds) * 1000).toLong()
            ended = ""
            apply()
            done.countDown()
        }
        done.await(WAIT_MS, TimeUnit.MILLISECONDS)
        return info()
    }

    fun cameraChanged(rear: Camera?) {
        main.post {
            camera = rear
            if (wanted) apply()
        }
    }

    fun off(why: String) {
        main.post {
            if (!wanted) return@post
            wanted = false
            ended = why
            apply()
        }
    }

    private fun apply() {
        val now = SystemClock.elapsedRealtime()
        if (wanted && now >= until) {
            wanted = false
            ended = "its time ran out"
        }
        if (wanted && hot()) {
            wanted = false
            ended = "the phone got hot"
        }
        val on = wanted
        val bound = camera
        try {
            when {
                bound != null -> {
                    val future = bound.cameraControl.enableTorch(on)
                    future.addListener({
                        try {
                            future.get()
                        } catch (e: Exception) {
                            problem = "the open rear camera would not switch its light ${if (on) "on" else "off"}: ${e.cause?.message ?: e.message}"
                            Log.w(TAG, problem)
                        }
                    }, { main.post(it) })
                    if (on && bound.cameraInfo.isTorchStrengthSupported) bound.cameraControl.setTorchStrengthLevel(TorchRules.step(fraction, bound.cameraInfo.maxTorchStrengthLevel))
                    through = "the rear camera, which is open"
                    problem = ""
                }
                id != null && manager != null -> {
                    if (on && Build.VERSION.SDK_INT >= 33 && maxLevel > 1) manager.turnOnTorchWithStrengthLevel(id, TorchRules.step(fraction, maxLevel)) else manager.setTorchMode(id, on)
                    through = "the phone's torch call"
                    problem = ""
                }
                on -> {
                    wanted = false
                    problem = "this phone has no light on its back"
                }
            }
        } catch (e: CameraAccessException) {
            problem = "the torch could not be switched ${if (on) "on" else "off"}: ${TorchRules.reason(e)}"
            Log.w(TAG, problem)
            if (on) wanted = false
        } catch (e: Exception) {
            problem = "the torch could not be switched ${if (on) "on" else "off"}: ${e.message}"
            Log.w(TAG, problem, e)
            if (on) wanted = false
        }
        main.removeCallbacks(check)
        if (wanted) main.postDelayed(check, CHECK_MS)
    }

    fun info(): JSONObject {
        val bound = camera
        val shining = if (bound != null) bound.cameraInfo.torchState.value == TorchState.ON else lit
        val left = if (wanted) ((until - SystemClock.elapsedRealtime()) / 1000.0).coerceAtLeast(0.0) else 0.0
        return JSONObject()
            .put("has_torch", id != null)
            .put("wanted", wanted)
            .put("on", shining)
            .put("level", fraction)
            .put("steps", if (bound != null && bound.cameraInfo.isTorchStrengthSupported) bound.cameraInfo.maxTorchStrengthLevel else maxLevel)
            .put("through", through)
            .put("left_s", Math.round(left * 10) / 10.0)
            .put("free", usable)
            .put("ended", ended)
            .put("problem", problem)
    }

    fun shutdown() {
        main.post {
            wanted = false
            apply()
            try {
                manager?.unregisterTorchCallback(callback)
            } catch (e: Exception) {
                Log.d(TAG, "the torch was not followed")
            }
        }
    }

    companion object {
        const val TAG = "PebbleTorch"
        const val CHECK_MS = 5_000L
        const val WAIT_MS = 3_000L
    }
}
