package nz.pebble.robot.recall

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtException
import ai.onnxruntime.OrtSession
import java.nio.LongBuffer

class OrtEncoder(model: ByteArray) : Encoder {
    private val env = OrtEnvironment.getEnvironment()
    private val session: OrtSession
    private val inputs: Set<String>
    private val lock = Any()
    private var running: OrtSession.RunOptions? = null
    private var runningFor: Any? = null
    private var stopped = false

    init {
        val options = OrtSession.SessionOptions()
        options.setIntraOpNumThreads(1)
        options.setInterOpNumThreads(1)
        options.setExecutionMode(OrtSession.SessionOptions.ExecutionMode.SEQUENTIAL)
        options.setOptimizationLevel(OrtSession.SessionOptions.OptLevel.ALL_OPT)
        options.setCPUArenaAllocator(false)
        options.setMemoryPatternOptimization(false)
        session = env.createSession(model, options)
        inputs = session.inputNames
    }

    override fun encode(rows: List<IntArray>, token: Any?): Array<FloatArray> {
        if (rows.isEmpty()) return emptyArray()
        val padded = Pooling.pad(rows)
        val shape = longArrayOf(padded.count.toLong(), padded.width.toLong())
        val feed = LinkedHashMap<String, OnnxTensor>()
        val options = OrtSession.RunOptions()
        synchronized(lock) {
            running = options
            runningFor = token
            stopped = false
        }
        try {
            feed["input_ids"] = OnnxTensor.createTensor(env, LongBuffer.wrap(padded.ids), shape)
            feed["attention_mask"] = OnnxTensor.createTensor(env, LongBuffer.wrap(padded.mask), shape)
            if ("token_type_ids" in inputs) feed["token_type_ids"] = OnnxTensor.createTensor(env, LongBuffer.wrap(padded.types), shape)
            session.run(feed.filterKeys { it in inputs }, options).use { result ->
                val hidden = result[0] as OnnxTensor
                return Pooling.first(hidden.floatBuffer, hidden.info.shape)
            }
        } catch (e: OrtException) {
            if (synchronized(lock) { stopped }) throw Encoder.Stopped()
            throw e
        } finally {
            synchronized(lock) {
                running = null
                runningFor = null
                options.close()
            }
            feed.values.forEach { it.close() }
        }
    }

    override fun stop(token: Any) {
        synchronized(lock) {
            if (running != null && runningFor === token) {
                stopped = true
                running?.setTerminate(true)
            }
        }
    }

    override fun close() {
        session.close()
    }
}
