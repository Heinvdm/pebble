package nz.pebble.robot.debug

import nz.pebble.robot.script.ScriptService
import java.io.File
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.Socket
import java.security.KeyStore

class ScriptProbeService : ScriptService() {
    override fun extra(op: String, message: Map<*, *>): Map<String, Any?>? {
        if (op != "probe") return null
        val port = (message["port"] as? Long)?.toInt() ?: 8765
        val data = applicationInfo.dataDir
        val out = LinkedHashMap<String, Any?>()
        out["list_files"] = attempt { File(data, "files").list()?.size ?: throw SecurityException("the folder could not be listed") }
        out["read_control"] = attempt { File(data, "files/script-probe-control.txt").readBytes().size }
        out["read_config"] = attempt { File(data, "files/pebble.json").readBytes().size }
        out["read_key"] = attempt { File(data, "files/keys/pebble-device.key").readBytes().size }
        out["list_self"] = attempt { File(data, "files/self").list()?.size ?: throw SecurityException("the folder could not be listed") }
        out["write_file"] = attempt {
            File(data, "files/script-probe.txt").writeText("x")
            "written"
        }
        out["shared_prefs"] = attempt {
            getSharedPreferences("script-probe", 0).edit().putString("x", "y").commit()
        }
        out["keystore"] = attempt { KeyStore.getInstance("AndroidKeyStore").apply { load(null) }.aliases().toList().size }
        out["socket_local"] = attempt {
            Socket().use { it.connect(InetSocketAddress("127.0.0.1", port), 1500) }
            "connected"
        }
        out["socket_internet"] = attempt {
            Socket().use { it.connect(InetSocketAddress("1.1.1.1", 443), 2000) }
            "connected"
        }
        out["dns"] = attempt { InetAddress.getByName("example.com").hostAddress }
        return out
    }

    private fun attempt(block: () -> Any?): String = try {
        "allowed: ${block()}"
    } catch (e: Throwable) {
        "refused: ${e.javaClass.simpleName}: ${e.message}"
    }
}
