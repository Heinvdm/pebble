package nz.pebble.robot.net

import android.util.Log
import nz.pebble.robot.Models
import nz.pebble.robot.Paths
import nz.pebble.robot.link.ProfileOverlay
import nz.pebble.robot.llm.LlamaPlan
import nz.pebble.robot.llm.LlamaServer
import nz.pebble.robot.llm.ModelAllow
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.net.Inet4Address
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.NetworkInterface
import java.net.ServerSocket
import java.net.Socket
import java.security.MessageDigest
import java.security.SecureRandom

class Receiver(private val paths: Paths, private val cache: File, private val seen: ModelAllow.Seen, private val install: (File) -> String) {
    @Volatile private var server: ServerSocket? = null
    @Volatile var code = ""
        private set
    @Volatile var until = 0L
        private set
    @Volatile private var wrong = 0
    @Volatile var problem = ""
        private set
    @Volatile private var bound = ""
    private val received = ArrayList<String>()

    val open: Boolean get() = server != null && System.currentTimeMillis() < until

    @Synchronized
    fun open(minutes: Int = 15): Boolean {
        close()
        val address = wifiAddress()
        if (address == null) {
            problem = "the phone has no Wi-Fi address, so there is nothing to receive on; join Pebble's Wi-Fi first"
            return false
        }
        code = (SecureRandom().nextInt(900_000) + 100_000).toString()
        until = System.currentTimeMillis() + minutes * 60_000L
        wrong = 0
        return try {
            val socket = ServerSocket()
            socket.reuseAddress = true
            socket.bind(InetSocketAddress(address, PORT), 1)
            server = socket
            bound = address.hostAddress ?: ""
            Thread({ serve(socket) }, "pebble-receiver").start()
            problem = ""
            true
        } catch (e: IOException) {
            problem = "could not listen on port $PORT: ${e.message}"
            false
        }
    }

    @Synchronized
    fun close() {
        try {
            server?.close()
        } catch (e: IOException) {
            Log.d(TAG, "already closed")
        }
        server = null
        until = 0L
        bound = ""
    }

    fun tick() {
        if (server != null && System.currentTimeMillis() >= until) close()
    }

    private fun serve(socket: ServerSocket) {
        try {
            while (!socket.isClosed) {
                val client = socket.accept()
                client.soTimeout = 60_000
                var done = false
                try {
                    done = handle(client)
                } catch (e: Exception) {
                    Log.w(TAG, "a request failed", e)
                } finally {
                    try {
                        client.close()
                    } catch (ignored: IOException) {
                        Log.d(TAG, "client already closed")
                    }
                }
                if (done || !open) close()
            }
        } catch (e: IOException) {
            Log.d(TAG, "receiver closed")
        }
    }

    private fun handle(client: Socket): Boolean {
        val input = client.getInputStream().buffered()
        val output = client.getOutputStream()
        val request = try {
            HttpLite.read(input)
        } catch (e: IllegalArgumentException) {
            output.write(HttpLite.response(400, "That was not a request Pebble understands."))
            return false
        } ?: return false
        if (!codeMatches(request.headers[CODE_HEADER] ?: "", code)) {
            wrong++
            output.write(HttpLite.response(403, "Wrong or missing code. Send the code on Pebble's admin screen in the $CODE_HEADER header."))
            if (wrong >= MAX_WRONG) close()
            return false
        }
        return when {
            request.method == "GET" && request.path == "/" -> {
                output.write(HttpLite.response(200, describe()))
                false
            }
            request.method == "PUT" && request.path.startsWith("/models/") -> putModel(request, input, output, request.path.removePrefix("/models/"))
            request.method == "PUT" && request.path == "/update" -> putUpdate(request, input, output)
            request.method == "PUT" && request.path == "/profile" -> putProfile(request, input, output)
            else -> {
                output.write(HttpLite.response(404, "Pebble takes PUT /models/<name>.gguf, PUT /update and PUT /profile."))
                false
            }
        }
    }

    private fun expect(request: HttpLite.Request, output: java.io.OutputStream) {
        if (request.headers["expect"]?.lowercase() == "100-continue") {
            output.write("HTTP/1.1 100 Continue\r\n\r\n".toByteArray())
            output.flush()
        }
    }

    private fun receive(request: HttpLite.Request, input: java.io.InputStream, target: File): Boolean {
        val tmp = File(target.parentFile, ".${target.name}.upload")
        var left = request.length
        tmp.outputStream().use { out ->
            val buffer = ByteArray(1 shl 16)
            while (left > 0) {
                val count = input.read(buffer, 0, minOf(buffer.size.toLong(), left).toInt())
                if (count < 0) break
                out.write(buffer, 0, count)
                left -= count
            }
            out.fd.sync()
        }
        if (left != 0L) {
            tmp.delete()
            return false
        }
        target.delete()
        return tmp.renameTo(target)
    }

    private fun putModel(request: HttpLite.Request, input: java.io.InputStream, output: java.io.OutputStream, name: String): Boolean {
        if (!Models.validName(name)) {
            output.write(HttpLite.response(400, "A model's name must end in .gguf and use only letters, digits, dots, dashes and underscores."))
            return false
        }
        if (request.length <= 0) {
            output.write(HttpLite.response(411, "Send the file with its length (curl -T does)."))
            return false
        }
        if (!ModelAllow.maybeKnown(request.length)) {
            output.write(HttpLite.response(403, "Not copied: no model on Pebble's list has that size. Pebble only loads the models listed in this app."))
            return false
        }
        paths.models.mkdirs()
        val fit = LlamaPlan.fitsDisk(request.length, LlamaServer.freeSpace(paths.models))
        if (!fit.ok) {
            output.write(HttpLite.response(507, "Not copied: ${fit.why}."))
            return false
        }
        expect(request, output)
        val target = File(paths.models, name)
        val tmp = File(paths.models, ".$name.upload")
        val (count, sha) = tmp.outputStream().use { out ->
            ModelAllow.copy(input, out, request.length).also { out.fd.sync() }
        }
        if (count != request.length) {
            tmp.delete()
            output.write(HttpLite.response(400, "The copy was cut short; nothing was kept."))
            return false
        }
        if (ModelAllow.known(count, sha) == null) {
            tmp.delete()
            output.write(HttpLite.response(403, "Not kept: this file's fingerprint is not on Pebble's list of models, so Pebble will not load it."))
            return false
        }
        target.delete()
        if (!tmp.renameTo(target)) {
            tmp.delete()
            output.write(HttpLite.response(500, "The file could not be put in place; nothing was kept."))
            return false
        }
        seen.note(target, sha)
        synchronized(received) { received += "model $name" }
        output.write(HttpLite.response(200, "Saved $name (${LlamaPlan.gb(count)}), checked against Pebble's list. The receiver is now closed. Choose the model on the admin screen."))
        return true
    }

    private fun putUpdate(request: HttpLite.Request, input: java.io.InputStream, output: java.io.OutputStream): Boolean {
        if (request.length <= 0 || request.length > MAX_APK) {
            output.write(HttpLite.response(413, "Send one APK of at most ${MAX_APK shr 20} MB."))
            return false
        }
        expect(request, output)
        val apk = File(cache, "update.apk")
        if (!receive(request, input, apk)) {
            output.write(HttpLite.response(400, "The copy was cut short; nothing was installed."))
            return false
        }
        val said = install(apk)
        synchronized(received) { received += "update" }
        output.write(HttpLite.response(200, "$said The receiver is now closed."))
        return true
    }

    private fun putProfile(request: HttpLite.Request, input: java.io.InputStream, output: java.io.OutputStream): Boolean {
        if (request.length <= 0 || request.length > 64 * 1024) {
            output.write(HttpLite.response(413, "A body profile is a small JSON file."))
            return false
        }
        expect(request, output)
        val bytes = ByteArray(request.length.toInt())
        var got = 0
        while (got < bytes.size) {
            val count = input.read(bytes, got, bytes.size - got)
            if (count < 0) break
            got += count
        }
        val kept = try {
            ProfileOverlay.clean(JSONObject(String(bytes, 0, got)))
        } catch (e: Exception) {
            output.write(HttpLite.response(400, "That is not JSON: ${e.message}"))
            return false
        }
        if (kept.length() == 0) {
            output.write(HttpLite.response(400, "Nothing kept: a profile sent to the phone may set only the cameras' field of view, rotation and mirror, drive.cpm and drive.wheel_track_mm, within their safe ranges."))
            return false
        }
        nz.pebble.robot.Atomic.write(paths.profileOverlay, kept.toString(2).toByteArray())
        synchronized(received) { received += "profile" }
        output.write(HttpLite.response(200, "Kept ${ProfileOverlay.describe(kept)}; everything else in the file was left out. The receiver is now closed. Restart Pebble's brain on the admin screen to use it."))
        return true
    }

    private fun describe(): String = "Pebble is ready to receive one file until ${java.text.DateFormat.getTimeInstance().format(java.util.Date(until))}, over plain HTTP on its own Wi-Fi.\n" +
        "Models: curl -T model.gguf -H \"$CODE_HEADER: $code\" \"http://$bound:$PORT/models/model.gguf\"\n" +
        "Update: curl -T app-release.apk -H \"$CODE_HEADER: $code\" \"http://$bound:$PORT/update\""

    fun status(): JSONObject = JSONObject()
        .put("open", open)
        .put("code", if (open) code else "")
        .put("until", until)
        .put("port", PORT)
        .put("header", CODE_HEADER)
        .put("addresses", JSONArray(if (bound.isNotEmpty()) listOf(bound) else emptyList<String>()))
        .put("received", JSONArray(synchronized(received) { received.takeLast(10) }))
        .put("problem", problem)

    companion object {
        const val TAG = "PebbleReceiver"
        const val PORT = 8899
        const val MAX_WRONG = 5
        const val MAX_APK = 400L shl 20
        const val CODE_HEADER = "x-pebble-code"

        fun codeMatches(given: String, code: String): Boolean = code.isNotEmpty() && MessageDigest.isEqual(given.trim().toByteArray(), code.toByteArray())

        fun wifiAddress(): InetAddress? = try {
            NetworkInterface.getNetworkInterfaces().toList()
                .filter { it.isUp && !it.isLoopback && it.name.startsWith("wlan") }
                .flatMap { it.inetAddresses.toList() }
                .firstOrNull { it is Inet4Address && !it.isLoopbackAddress }
        } catch (e: Exception) {
            null
        }
    }
}
