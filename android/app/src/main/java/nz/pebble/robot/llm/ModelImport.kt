package nz.pebble.robot.llm

import android.util.Log
import java.io.File

class ModelImport(private val drop: File, private val models: File, private val seen: ModelAllow.Seen) {
    data class Refusal(val name: String, val bytes: Long, val modified: Long, val why: String, val unknown: Boolean, val at: Long)

    @Volatile var busy = ""
        private set
    private val refused = LinkedHashMap<String, Refusal>()
    private var worker: Thread? = null

    fun refusals(): List<Refusal> = synchronized(refused) { refused.values.toList() }

    fun refusal(name: String): Refusal? = synchronized(refused) { refused[name] }

    private fun stillRefused(file: File): Boolean = synchronized(refused) {
        refused[file.name]?.let { it.bytes == file.length() && it.modified == file.lastModified() && (it.unknown || System.currentTimeMillis() - it.at < RETRY_MS) } == true
    }

    private fun refuse(file: File, why: String) {
        Log.w(TAG, "refused ${file.name}: $why")
        synchronized(refused) { refused[file.name] = Refusal(file.name, file.length(), file.lastModified(), why, why == NOT_KNOWN, System.currentTimeMillis()) }
    }

    private fun clear(name: String) = synchronized(refused) { refused.remove(name) }

    fun waiting(name: String): Boolean = busy == name || File(drop, name).exists() && !stillRefused(File(drop, name))

    fun tick(now: Long) {
        if (worker?.isAlive == true) return
        models.mkdirs()
        models.listFiles { f -> f.name.startsWith(".") && f.name.endsWith(".part") }?.forEach { it.delete() }
        val unchecked = gguf(models).firstOrNull { !seen.checked(it) }
        if (unchecked != null) {
            start(unchecked.name) { check(unchecked) }
            return
        }
        val ready = gguf(drop).firstOrNull { !ModelFiles.copying(it, now) && !stillRefused(it) } ?: return
        start(ready.name) { take(ready) }
    }

    private fun start(name: String, job: () -> Unit) {
        busy = name
        worker = Thread({
            try {
                job()
            } catch (e: Exception) {
                Log.w(TAG, "checking $name failed", e)
            } finally {
                busy = ""
            }
        }, "pebble-models").also { it.start() }
    }

    private fun check(file: File) {
        if (!ModelAllow.maybeKnown(file.length())) {
            seen.note(file, "")
            refuse(file, NOT_KNOWN)
            return
        }
        val sha = ModelAllow.hash(file)
        seen.note(file, sha)
        if (ModelAllow.known(file.length(), sha) == null) refuse(file, NOT_KNOWN) else clear(file.name)
    }

    private fun take(file: File) {
        if (!ModelAllow.maybeKnown(file.length())) {
            refuse(file, NOT_KNOWN)
            return
        }
        val fit = LlamaPlan.fitsDisk(file.length(), LlamaServer.freeSpace(models))
        if (!fit.ok) {
            refuse(file, fit.why)
            return
        }
        val part = File(models, ".${file.name}.part")
        val (count, sha) = file.inputStream().use { input ->
            part.outputStream().use { out ->
                ModelAllow.copy(input, out, Long.MAX_VALUE).also { out.fd.sync() }
            }
        }
        if (count != file.length() || ModelAllow.known(count, sha) == null) {
            part.delete()
            refuse(file, if (count != file.length()) "it changed while it was being read; copy it again" else NOT_KNOWN)
            return
        }
        val target = File(models, file.name)
        target.delete()
        if (!part.renameTo(target)) {
            part.delete()
            refuse(file, "it could not be moved into Pebble's own storage")
            return
        }
        seen.note(target, sha)
        clear(file.name)
        file.delete()
        Log.i(TAG, "moved ${file.name} into Pebble's own storage after checking it")
    }

    companion object {
        const val TAG = "PebbleModels"
        const val NOT_KNOWN = "its fingerprint is not on Pebble's list of models, so Pebble will not load it"
        const val RETRY_MS = 5 * 60_000L

        fun gguf(dir: File): List<File> = dir.listFiles { f -> f.isFile && !f.name.startsWith(".") && f.name.lowercase().endsWith(".gguf") }?.sortedBy { it.name }.orEmpty()
    }
}
