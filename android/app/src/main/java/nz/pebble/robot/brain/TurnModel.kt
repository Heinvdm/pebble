package nz.pebble.robot.brain

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import android.content.Context
import android.util.Log
import java.nio.FloatBuffer

class TurnModel(private val context: Context) : AutoCloseable {
    private var session: OrtSession? = null
    private var input = "input_features"
    @Volatile var state = "off"
        private set
    @Volatile var lastChance = Double.NaN
        private set
    @Volatile var lastMs = 0.0
        private set
    @Volatile var runs = 0
        private set

    val present: Boolean by lazy {
        try {
            context.assets.open(ASSET).use { true }
        } catch (e: Exception) {
            false
        }
    }

    private fun open(): OrtSession? {
        session?.let { return it }
        if (state.startsWith("failed") || state == "missing") return null
        if (!present) {
            state = "missing"
            return null
        }
        return try {
            val bytes = context.assets.open(ASSET).use { it.readBytes() }
            val options = OrtSession.SessionOptions()
            options.setIntraOpNumThreads(1)
            options.setInterOpNumThreads(1)
            options.setExecutionMode(OrtSession.SessionOptions.ExecutionMode.SEQUENTIAL)
            options.setOptimizationLevel(OrtSession.SessionOptions.OptLevel.ALL_OPT)
            val made = OrtEnvironment.getEnvironment().createSession(bytes, options)
            input = made.inputNames.firstOrNull() ?: input
            session = made
            state = "on"
            made
        } catch (e: Throwable) {
            state = "failed: ${e.message?.take(120)}"
            Log.w(TAG, "the end-of-turn model would not load", e)
            null
        }
    }

    fun chance(audio: FloatArray, count: Int = audio.size): Double? {
        val s = open() ?: return null
        val started = System.nanoTime()
        return try {
            val features = TurnFeatures.features(TurnFeatures.lastSeconds(audio, count))
            val shape = longArrayOf(1, TurnFeatures.MELS.toLong(), TurnFeatures.FRAMES.toLong())
            OnnxTensor.createTensor(OrtEnvironment.getEnvironment(), FloatBuffer.wrap(features), shape).use { tensor ->
                s.run(mapOf(input to tensor)).use { result ->
                    val out = (result[0] as OnnxTensor).floatBuffer
                    val p = out.get(0).toDouble().coerceIn(0.0, 1.0)
                    lastChance = p
                    lastMs = (System.nanoTime() - started) / 1e6
                    runs++
                    p
                }
            }
        } catch (e: Throwable) {
            state = "failed: ${e.message?.take(120)}"
            Log.w(TAG, "the end-of-turn model failed", e)
            null
        }
    }

    override fun close() {
        session?.close()
        session = null
        if (state == "on") state = "off"
    }

    companion object {
        const val TAG = "PebbleTurn"
        const val ASSET = "turn/smart-turn-v3.2-cpu.onnx"
    }
}
