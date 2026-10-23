package nz.pebble.robot.net

import java.io.InputStream
import java.net.URLDecoder

object HttpLite {
    data class Request(val method: String, val path: String, val query: Map<String, String>, val headers: Map<String, String>) {
        val length: Long get() = headers["content-length"]?.trim()?.toLongOrNull() ?: -1L
    }

    const val MAX_LINE = 4096
    const val MAX_HEADERS = 64

    fun readLine(input: InputStream): String? {
        val out = StringBuilder()
        while (true) {
            val b = input.read()
            if (b < 0) return if (out.isEmpty()) null else out.toString()
            if (b == '\n'.code) return out.toString().trimEnd('\r')
            if (out.length >= MAX_LINE) throw IllegalArgumentException("line too long")
            out.append(b.toChar())
        }
    }

    fun read(input: InputStream): Request? {
        val first = readLine(input) ?: return null
        val parts = first.split(' ')
        if (parts.size != 3 || !parts[2].startsWith("HTTP/")) throw IllegalArgumentException("not an HTTP request")
        val headers = HashMap<String, String>()
        while (true) {
            val line = readLine(input) ?: break
            if (line.isEmpty()) break
            if (headers.size >= MAX_HEADERS) throw IllegalArgumentException("too many headers")
            val colon = line.indexOf(':')
            if (colon <= 0) continue
            headers[line.substring(0, colon).trim().lowercase()] = line.substring(colon + 1).trim()
        }
        val target = parts[1]
        val mark = target.indexOf('?')
        val path = if (mark >= 0) target.substring(0, mark) else target
        val query = if (mark >= 0) parseQuery(target.substring(mark + 1)) else emptyMap()
        return Request(parts[0].uppercase(), URLDecoder.decode(path, "UTF-8"), query, headers)
    }

    fun parseQuery(text: String): Map<String, String> = text.split('&').filter { it.isNotEmpty() }.associate {
        val eq = it.indexOf('=')
        if (eq < 0) URLDecoder.decode(it, "UTF-8") to "" else URLDecoder.decode(it.substring(0, eq), "UTF-8") to URLDecoder.decode(it.substring(eq + 1), "UTF-8")
    }

    fun response(code: Int, text: String): ByteArray {
        val body = (text + "\n").toByteArray()
        val reason = when (code) {
            200 -> "OK"
            400 -> "Bad Request"
            403 -> "Forbidden"
            404 -> "Not Found"
            411 -> "Length Required"
            413 -> "Payload Too Large"
            507 -> "Insufficient Storage"
            else -> "Error"
        }
        val head = "HTTP/1.1 $code $reason\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Length: ${body.size}\r\nConnection: close\r\n\r\n"
        return head.toByteArray() + body
    }
}
