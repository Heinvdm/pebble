package nz.pebble.robot.usb

import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.hardware.usb.UsbManager
import android.util.Log
import com.hoho.android.usbserial.driver.CdcAcmSerialDriver
import com.hoho.android.usbserial.driver.ProbeTable
import com.hoho.android.usbserial.driver.UsbSerialPort
import com.hoho.android.usbserial.driver.UsbSerialProber
import com.hoho.android.usbserial.util.SerialInputOutputManager
import org.json.JSONObject
import java.io.IOException
import java.io.InputStream
import java.io.OutputStream
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong
import nz.pebble.robot.link.LineChannel

class UsbBridge(private val context: Context, private val port: Int) {
    private val usb = context.getSystemService(UsbManager::class.java)
    @Volatile private var server: ServerSocket? = null
    @Volatile private var client: Socket? = null
    @Volatile private var serial: UsbSerialPort? = null
    private var io: SerialInputOutputManager? = null
    private var acceptor: Thread? = null
    @Volatile private var running = false
    private var asked = false
    private val toBody = AtomicLong()
    private val fromBody = AtomicLong()
    @Volatile private var diverted: LinkedBlockingQueue<String>? = null
    private val pending = StringBuilder()
    @Volatile var problem = ""
        private set
    @Volatile var device = ""
        private set

    fun start() {
        if (running) return
        running = true
        acceptor = Thread({ accept() }, "pebble-usb-accept").also { it.start() }
    }

    fun stop() {
        running = false
        closeSerial()
        try {
            client?.close()
        } catch (e: IOException) {
            Log.d(TAG, "client already closed")
        }
        try {
            server?.close()
        } catch (e: IOException) {
            Log.d(TAG, "server already closed")
        }
        acceptor?.interrupt()
        acceptor = null
    }

    fun tick() {
        if (!running) return
        if (serial == null) openSerial()
    }

    private fun prober(): UsbSerialProber {
        val table = UsbSerialProber.getDefaultProbeTable()
        table.addProduct(ESPRESSIF, 0x1001, CdcAcmSerialDriver::class.java)
        table.addProduct(ESPRESSIF, 0x4001, CdcAcmSerialDriver::class.java)
        table.addProduct(ESPRESSIF, 0x0002, CdcAcmSerialDriver::class.java)
        return UsbSerialProber(table)
    }

    @Synchronized
    private fun openSerial() {
        val drivers = prober().findAllDrivers(usb)
        val driver = drivers.firstOrNull { it.device.vendorId == ESPRESSIF } ?: drivers.firstOrNull()
        if (driver == null) {
            problem = "no ESP32 is plugged into the phone's USB port"
            device = ""
            return
        }
        device = "${driver.device.productName ?: "USB serial"} (${String.format("%04x:%04x", driver.device.vendorId, driver.device.productId)})"
        if (!usb.hasPermission(driver.device)) {
            problem = "the phone has not let Pebble use $device yet; answer the question on the screen, or unplug and plug it in again"
            if (!asked) {
                asked = true
                val intent = PendingIntent.getBroadcast(context, 0, Intent(ACTION_PERMISSION).setPackage(context.packageName), PendingIntent.FLAG_IMMUTABLE)
                usb.requestPermission(driver.device, intent)
            }
            return
        }
        val connection = usb.openDevice(driver.device)
        if (connection == null) {
            problem = "$device could not be opened"
            return
        }
        try {
            val p = driver.ports.first()
            p.open(connection)
            p.setParameters(BAUD, 8, UsbSerialPort.STOPBITS_1, UsbSerialPort.PARITY_NONE)
            try {
                p.dtr = true
                p.rts = true
            } catch (e: Exception) {
                Log.d(TAG, "this port has no DTR/RTS")
            }
            val manager = SerialInputOutputManager(p, object : SerialInputOutputManager.Listener {
                override fun onNewData(data: ByteArray) {
                    fromBody.addAndGet(data.size.toLong())
                    diverted?.let {
                        divert(it, data)
                        return
                    }
                    val out = client ?: return
                    try {
                        out.getOutputStream().write(data)
                    } catch (e: IOException) {
                        dropClient()
                    }
                }

                override fun onRunError(e: Exception) {
                    problem = "the USB link stopped: ${e.message}"
                    Log.w(TAG, problem)
                    closeSerial()
                }
            })
            manager.start()
            serial = p
            io = manager
            problem = ""
            Log.i(TAG, "USB link open: $device at $BAUD")
        } catch (e: Exception) {
            problem = "$device would not open: ${e.message}"
            Log.w(TAG, problem, e)
            try {
                connection.close()
            } catch (ignored: Exception) {
                Log.d(TAG, "connection already closed")
            }
        }
    }

    @Synchronized
    private fun closeSerial() {
        io?.stop()
        io = null
        try {
            serial?.close()
        } catch (e: IOException) {
            Log.d(TAG, "serial already closed")
        }
        serial = null
    }

    private fun accept() {
        try {
            val socket = ServerSocket(port, 1, InetAddress.getByName("127.0.0.1"))
            socket.reuseAddress = true
            server = socket
            while (running) {
                val incoming = socket.accept()
                if (diverted != null) {
                    incoming.close()
                    continue
                }
                incoming.tcpNoDelay = true
                dropClient()
                client = incoming
                Thread({ pump(incoming) }, "pebble-usb-client").start()
            }
        } catch (e: IOException) {
            if (running) {
                problem = "the USB bridge could not listen on port $port: ${e.message}"
                Log.w(TAG, problem)
            }
        }
    }

    private fun pump(socket: Socket) {
        val buffer = ByteArray(512)
        try {
            val input: InputStream = socket.getInputStream()
            while (running) {
                val count = input.read(buffer)
                if (count < 0) break
                val p = serial ?: continue
                p.write(buffer.copyOf(count), WRITE_MS)
                toBody.addAndGet(count.toLong())
            }
        } catch (e: IOException) {
            Log.d(TAG, "the brain's link closed: ${e.message}")
        } finally {
            if (client == socket) dropClient()
        }
    }

    private fun dropClient() {
        val old = client ?: return
        client = null
        try {
            old.close()
        } catch (e: IOException) {
            Log.d(TAG, "client already closed")
        }
    }

    private fun divert(queue: LinkedBlockingQueue<String>, data: ByteArray) {
        synchronized(pending) {
            for (b in data) {
                val c = (b.toInt() and 0xFF).toChar()
                when {
                    c == '\n' -> {
                        queue.offer(pending.toString().trimEnd('\r'))
                        pending.setLength(0)
                    }
                    pending.length < MAX_LINE -> pending.append(c)
                }
            }
        }
    }

    fun channel(): LineChannel? {
        val port = serial ?: return null
        val queue = LinkedBlockingQueue<String>()
        synchronized(pending) { pending.setLength(0) }
        diverted = queue
        dropClient()
        return object : LineChannel {
            override fun send(line: String) {
                port.write((line + "\n").toByteArray(Charsets.US_ASCII), WRITE_MS)
            }

            override fun receive(timeoutMs: Long): String? = queue.poll(timeoutMs, TimeUnit.MILLISECONDS)
        }
    }

    fun release() {
        diverted = null
    }

    fun opened(): Boolean = serial != null

    fun status(): JSONObject = JSONObject()
        .put("port", port)
        .put("device", device)
        .put("open", serial != null)
        .put("brain_connected", client != null)
        .put("to_body", toBody.get())
        .put("from_body", fromBody.get())
        .put("problem", problem)

    companion object {
        const val TAG = "PebbleUsb"
        const val ESPRESSIF = 0x303A
        const val BAUD = 115200
        const val WRITE_MS = 200
        const val ACTION_PERMISSION = "nz.pebble.robot.USB_PERMISSION"
        const val MAX_LINE = 256
    }
}
