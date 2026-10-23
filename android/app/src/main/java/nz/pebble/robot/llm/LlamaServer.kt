package nz.pebble.robot.llm

import android.app.ActivityManager
import android.content.Context
import android.os.Build
import android.os.StatFs
import android.util.Log
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import nz.pebble.robot.BuildConfig
import nz.pebble.robot.keeper.Backoff

class LlamaServer(private val context: Context, val role: String, private val logFile: File) {
    private var process: Process? = null
    private var plan: LlamaPlan.Server? = null
    private var startedAt = 0L
    private var readyAt = 0L
    private var lastAnswer = 0L
    private var nextStart = 0L
    private val backoff = Backoff()
    private var kvSeen: Pair<String, KvCost?>? = null
    val choice = LlamaChoice(File(context.noBackupFilesDir, "llama-$role.json"))
    var state = "off"
        private set
    var problem = ""
        private set
    var kind = ""
        private set
    var restarts = 0
        private set
    private var logStart = 0L

    val running: Boolean get() = process?.isAlive == true

    fun tick(wanted: LlamaPlan.Server?, why: String, holdKind: String = "") {
        val now = System.currentTimeMillis()
        if (wanted == null) {
            if (process != null) stop()
            state = "off"
            problem = why
            kind = holdKind
            return
        }
        if (plan != null && plan != wanted && running) stop()
        val p = process
        if (p == null || !p.isAlive) {
            if (p != null) {
                val early = readyAt == 0L || now - readyAt < EARLY_MS
                val code = p.exitValue()
                val failure = ModelFiles.failure(logTail(), code, plan?.projector != null)
                val file = plan?.model?.name ?: "the model"
                val drafter = plan?.drafter?.takeIf { early }
                problem = when {
                    drafter != null -> "llama-server for $file stopped with the drafter ${drafter.name}; it starts again without it (${logName()} has the details)"
                    failure.memory -> "llama-server for $file stopped: ${failure.why}; it starts again by itself (${logName()} has the details)"
                    else -> "$file could not be loaded: ${failure.why}"
                }
                kind = if (drafter != null) ModelFiles.STOPPED else failure.kind
                Log.w(TAG, "llama-server ($role) stopped with code $code: ${failure.why}")
                plan?.takeIf { early && (failure.memory || it.drafter != null) }?.let { stepDown(it, if (readyAt == 0L) "it stopped while loading" else "it stopped soon after loading") }
                process = null
                nextStart = now + backoff.next()
                restarts++
            }
            if (now < nextStart) {
                state = "waiting"
                return
            }
            start(wanted)
            return
        }
        if (health()) {
            lastAnswer = now
            if (readyAt == 0L) {
                readyAt = now
                Log.i(TAG, "llama-server ($role) is ready after ${(now - startedAt) / 1000} s")
            }
            state = "ready"
            problem = ""
            kind = ""
            backoff.healthy(now, readyAt)
            return
        }
        val quiet = now - maxOf(lastAnswer, startedAt)
        if (readyAt == 0L && now - startedAt > LOAD_LIMIT_MS) {
            plan?.let { stepDown(it, "it did not finish loading") }
            kill("llama-server for ${plan?.model?.name ?: "the model"} did not finish loading in ${LOAD_LIMIT_MS / 60000} minutes; it starts again with a smaller setting")
        }
        else if (readyAt != 0L && quiet > HANG_MS) kill("llama-server for ${plan?.model?.name ?: "the model"} stopped answering for ${quiet / 1000} s, so it was stopped; it starts again by itself")
        else state = if (readyAt == 0L) "loading" else "busy"
    }

    fun kv(model: File): KvCost? {
        val id = "${model.path}/${model.length()}/${model.lastModified()}"
        kvSeen?.takeIf { it.first == id }?.let { return it.second }
        val cost = KvCost.read(model)
        kvSeen = id to cost
        return cost
    }

    fun key(model: File, projector: File?, drafter: File? = null): String = LlamaChoice.key(BuildConfig.VERSION_CODE, Build.MODEL ?: "phone", model, projector, drafter)

    fun current(model: File, projector: File?, drafter: File?, batch: Int, port: Int): LlamaPlan.Server? =
        plan?.takeIf { running && it.model == model && it.projector == projector && it.drafter == drafter && it.batch == batch && it.port == port }

    val planned: LlamaPlan.Server? get() = plan

    fun stateFor(port: Int, batch: Int, drafter: Boolean): String {
        val p = plan ?: return "starting"
        if (p.port != port || p.batch != batch || (p.drafter != null) != drafter) return "starting"
        return state
    }

    fun pid(): Int? {
        val port = plan?.port ?: return null
        if (!running) return null
        val proc = File("/proc")
        for (dir in proc.listFiles() ?: return null) {
            val id = dir.name.toIntOrNull() ?: continue
            val cmd = try {
                File(dir, "cmdline").readBytes().toString(Charsets.UTF_8).split(Char(0))
            } catch (e: Exception) {
                continue
            }
            if (cmd.isNotEmpty() && cmd[0].endsWith(EXE) && cmd.windowed(2).any { it[0] == "--port" && it[1] == port.toString() }) return id
        }
        return null
    }

    fun rss(): Long? {
        val id = pid() ?: return null
        return try {
            File("/proc/$id/status").readLines().firstOrNull { it.startsWith("VmRSS:") }?.split(Regex("\\s+"))?.getOrNull(1)?.toLongOrNull()?.times(1024)
        } catch (e: Exception) {
            null
        }
    }

    fun metrics(): Map<String, Double> {
        val port = plan?.port ?: return emptyMap()
        if (state != "ready") return emptyMap()
        return LlamaHttp(port).metrics()
    }

    private fun stepDown(s: LlamaPlan.Server, why: String) {
        if (s.key.isEmpty()) return
        if (s.drafter != null) {
            choice.keepDrafter(s.key, LlamaChoice.DRAFTER_FAILED, why)
            Log.w(TAG, "llama-server ($role): $why with the drafter ${s.drafter.name}; the next start goes without it")
            return
        }
        choice.keep(s.key, s.step + 1, why)
        Log.w(TAG, "llama-server ($role): $why at setting ${s.step}; the next start uses setting ${s.step + 1}")
    }

    private fun start(wanted: LlamaPlan.Server) {
        val exe = File(context.applicationInfo.nativeLibraryDir, EXE)
        if (!exe.exists()) {
            problem = "this build of Pebble has no llama-server for this phone's processor; build it with llama/build.sh and the phone's ABI (SETUP.md, step 1)"
            kind = ModelFiles.NO_PROGRAM
            state = "missing"
            return
        }
        rotate()
        logStart = logFile.length()
        if (kind != ModelFiles.BAD_FILE && kind != ModelFiles.STOPPED) {
            kind = ""
            problem = ""
        }
        val command = listOf(exe.path) + LlamaPlan.args(wanted)
        val builder = ProcessBuilder(command)
            .directory(context.cacheDir)
            .redirectErrorStream(true)
            .redirectOutput(ProcessBuilder.Redirect.appendTo(logFile))
        builder.environment()["LD_LIBRARY_PATH"] = context.applicationInfo.nativeLibraryDir
        builder.environment()["HOME"] = context.filesDir.path
        builder.environment()["TMPDIR"] = context.cacheDir.path
        try {
            process = builder.start()
            plan = wanted
            startedAt = System.currentTimeMillis()
            readyAt = 0L
            lastAnswer = 0L
            state = "loading"
            Log.i(TAG, "started llama-server ($role): ${command.joinToString(" ")}")
        } catch (e: Exception) {
            problem = "llama-server could not be started on this phone; it is tried again by itself (${logName()} has the details)"
            kind = ModelFiles.STOPPED
            state = "failed"
            nextStart = System.currentTimeMillis() + backoff.next()
            Log.e(TAG, "llama-server ($role) would not start", e)
            try {
                logFile.appendText("Pebble could not start llama-server: $e\n")
            } catch (ignored: Exception) {
                Log.d(TAG, "could not write the model log")
            }
        }
    }

    private fun logName(): String = if (role == "main") "the main model log" else "the small model log"

    private fun logTail(): String = try {
        java.io.RandomAccessFile(logFile, "r").use { file ->
            val from = maxOf(logStart.coerceAtMost(file.length()), file.length() - TAIL_BYTES)
            val bytes = ByteArray((file.length() - from).toInt())
            file.seek(from)
            file.readFully(bytes)
            String(bytes, Charsets.UTF_8)
        }
    } catch (e: Exception) {
        ""
    }

    private fun rotate() {
        logFile.parentFile?.mkdirs()
        if (logFile.length() > LOG_LIMIT) {
            val old = File(logFile.path + ".1")
            old.delete()
            logFile.renameTo(old)
        }
    }

    private fun kill(why: String) {
        problem = why
        kind = ModelFiles.STOPPED
        Log.w(TAG, why)
        stop()
        nextStart = System.currentTimeMillis() + backoff.next()
        restarts++
    }

    fun stop() {
        val p = process ?: return
        p.destroy()
        try {
            if (!p.waitFor(3, java.util.concurrent.TimeUnit.SECONDS)) p.destroyForcibly()
        } catch (e: InterruptedException) {
            p.destroyForcibly()
        }
        process = null
        plan = null
        readyAt = 0L
        state = "off"
    }

    private fun health(): Boolean {
        val port = plan?.port ?: return false
        return try {
            val connection = URL("http://127.0.0.1:$port/health").openConnection() as HttpURLConnection
            connection.connectTimeout = 1500
            connection.readTimeout = 2500
            val code = connection.responseCode
            connection.disconnect()
            code == 200
        } catch (e: Exception) {
            false
        }
    }

    fun status(): JSONObject = JSONObject()
        .put("role", role)
        .put("state", state)
        .put("problem", problem)
        .put("kind", kind)
        .put("loading_s", if (state == "loading" && startedAt > 0L) (System.currentTimeMillis() - startedAt) / 1000 else JSONObject.NULL)
        .put("retry_in_s", if (state == "waiting" || state == "failed") maxOf(0L, (nextStart - System.currentTimeMillis() + 999) / 1000) else JSONObject.NULL)
        .put("restarts", restarts)
        .put("model", plan?.model?.name ?: JSONObject.NULL)
        .put("projector", plan?.projector?.name ?: JSONObject.NULL)
        .put("port", plan?.port ?: JSONObject.NULL)
        .put("threads", plan?.threads ?: JSONObject.NULL)
        .put("cores", plan?.mask ?: JSONObject.NULL)
        .put("context", plan?.context ?: JSONObject.NULL)
        .put("setting", plan?.step ?: JSONObject.NULL)
        .put("cacheMib", plan?.cacheMib ?: JSONObject.NULL)
        .put("swaFull", plan?.swaFull ?: JSONObject.NULL)
        .put("cacheType", plan?.cacheType ?: JSONObject.NULL)
        .put("batch", plan?.batch ?: JSONObject.NULL)
        .put("drafter", plan?.drafter?.name ?: JSONObject.NULL)

    companion object {
        const val TAG = "PebbleLlama"
        const val EXE = "libllama-server.so"
        const val LOAD_LIMIT_MS = 15 * 60_000L
        const val HANG_MS = 120_000L
        const val EARLY_MS = 5 * 60_000L
        const val LOG_LIMIT = 2L shl 20
        const val TAIL_BYTES = 16L * 1024

        fun maxFreqs(): List<Long> {
            val out = ArrayList<Long>()
            var cpu = 0
            while (true) {
                val dir = File("/sys/devices/system/cpu/cpu$cpu")
                if (!dir.exists()) break
                val freq = try {
                    File(dir, "cpufreq/cpuinfo_max_freq").readText().trim().toLong()
                } catch (e: Exception) {
                    0L
                }
                out += freq
                cpu++
            }
            if (out.isEmpty()) repeat(Runtime.getRuntime().availableProcessors()) { out += 0L }
            return out
        }

        fun memory(context: Context): Pair<Long, Long> {
            val info = ActivityManager.MemoryInfo()
            context.getSystemService(ActivityManager::class.java).getMemoryInfo(info)
            return info.totalMem to info.availMem
        }

        fun freeSpace(folder: File): Long = try {
            folder.mkdirs()
            StatFs(folder.path).availableBytes
        } catch (e: Exception) {
            0L
        }
    }
}
