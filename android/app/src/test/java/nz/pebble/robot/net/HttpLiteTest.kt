package nz.pebble.robot.net

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayInputStream

class HttpLiteTest {
    @Test
    fun aCurlUploadIsRead() {
        val text = "PUT /models/gemma%20x.gguf?code=123456&x HTTP/1.1\r\nHost: 192.168.1.9:8899\r\nContent-Length: 42\r\nExpect: 100-continue\r\n\r\nBODY"
        val input = ByteArrayInputStream(text.toByteArray())
        val request = HttpLite.read(input)!!
        assertEquals("PUT", request.method)
        assertEquals("/models/gemma x.gguf", request.path)
        assertEquals("123456", request.query["code"])
        assertEquals("", request.query["x"])
        assertEquals(42L, request.length)
        assertEquals("100-continue", request.headers["expect"])
        assertEquals("BODY", input.readBytes().toString(Charsets.UTF_8))
    }

    @Test
    fun junkIsRefused() {
        assertNull(HttpLite.read(ByteArrayInputStream(ByteArray(0))))
        try {
            HttpLite.read(ByteArrayInputStream("hello there\r\n\r\n".toByteArray()))
            throw AssertionError("should have refused")
        } catch (e: IllegalArgumentException) {
            assertTrue(e.message!!.contains("HTTP"))
        }
        assertTrue(String(HttpLite.response(403, "no")).startsWith("HTTP/1.1 403 Forbidden"))
    }
}
