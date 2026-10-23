package nz.pebble.robot.brain

import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.BatteryManager
import android.os.HardwarePropertiesManager
import android.os.SystemClock
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.max

class SensorRing(val kind: String, val width: Int, private val capacity: Int) {
    private val times = DoubleArray(capacity)
    private val values = FloatArray(capacity * width)
    private var total = 0L

    @Synchronized
    fun add(tMs: Double, v: FloatArray) {
        val slot = (total % capacity).toInt()
        times[slot] = tMs
        for (i in 0 until width) values[slot * width + i] = if (i < v.size) v[i] else 0f
        total++
    }

    @Synchronized
    fun latest(): FloatArray? {
        if (total == 0L) return null
        val slot = ((total - 1) % capacity).toInt()
        return values.copyOfRange(slot * width, slot * width + width)
    }

    @Synchronized
    fun read(from: Long, max: Int, nowMs: Double): JSONObject {
        val oldest = maxOf(0L, total - capacity)
        val start = from.coerceIn(oldest, total)
        val count = minOf(max.toLong().coerceAtLeast(0), total - start).toInt()
        val rows = JSONArray()
        for (n in 0 until count) {
            val slot = ((start + n) % capacity).toInt()
            val row = JSONArray().put(times[slot])
            for (i in 0 until width) row.put(values[slot * width + i].toDouble())
            rows.put(row)
        }
        return JSONObject().put("kind", kind).put("total", total).put("from", start).put("rows", rows).put("now_ms", nowMs)
    }
}

class PhoneSensors(private val context: Context) : SensorEventListener {
    private val manager = context.getSystemService(SensorManager::class.java)
    private val sensors: Map<String, Sensor?> = mapOf(
        "accel" to manager?.getDefaultSensor(Sensor.TYPE_ACCELEROMETER),
        "gyro" to manager?.getDefaultSensor(Sensor.TYPE_GYROSCOPE),
        "pressure" to manager?.getDefaultSensor(Sensor.TYPE_PRESSURE),
        "light" to manager?.getDefaultSensor(Sensor.TYPE_LIGHT),
        "proximity" to manager?.getDefaultSensor(Sensor.TYPE_PROXIMITY),
        "magnet" to manager?.getDefaultSensor(Sensor.TYPE_MAGNETIC_FIELD),
    )
    private val rings = mapOf(
        "accel" to SensorRing("accel", 3, 4096),
        "gyro" to SensorRing("gyro", 3, 4096),
        "pressure" to SensorRing("pressure", 1, 4096),
        "light" to SensorRing("light", 1, 256),
        "proximity" to SensorRing("proximity", 1, 256),
        "magnet" to SensorRing("magnet", 3, 256),
    )
    private val lastAt = HashMap<String, Long>()
    @Volatile private var running = false
    @Volatile private var tapOn = false
    private var tapUsers = 0

    @Synchronized
    fun start() {
        if (running || manager == null) return
        running = true
        register()
    }

    @Synchronized
    fun stop() {
        if (!running) return
        running = false
        manager?.unregisterListener(this)
    }

    @Synchronized
    fun tap(on: Boolean) {
        tapUsers = if (on) tapUsers + 1 else max(0, tapUsers - 1)
        if ((tapUsers > 0) == tapOn) return
        tapOn = tapUsers > 0
        if (running) {
            manager?.unregisterListener(this)
            register()
        }
    }

    private fun register() {
        val m = manager ?: return
        val fast = if (tapOn) FAST_US else SensorManager.SENSOR_DELAY_NORMAL
        sensors["accel"]?.let { m.registerListener(this, it, fast) }
        sensors["gyro"]?.let { m.registerListener(this, it, fast) }
        sensors["light"]?.let { m.registerListener(this, it, SensorManager.SENSOR_DELAY_NORMAL) }
        sensors["proximity"]?.let { m.registerListener(this, it, SensorManager.SENSOR_DELAY_NORMAL) }
        if (tapOn) {
            sensors["pressure"]?.let { m.registerListener(this, it, SensorManager.SENSOR_DELAY_GAME) }
            sensors["magnet"]?.let { m.registerListener(this, it, SensorManager.SENSOR_DELAY_NORMAL) }
        } else {
            sensors["pressure"]?.let { m.registerListener(this, it, SensorManager.SENSOR_DELAY_NORMAL) }
        }
    }

    override fun onSensorChanged(event: SensorEvent) {
        val kind = when (event.sensor.type) {
            Sensor.TYPE_ACCELEROMETER -> "accel"
            Sensor.TYPE_GYROSCOPE -> "gyro"
            Sensor.TYPE_PRESSURE -> "pressure"
            Sensor.TYPE_LIGHT -> "light"
            Sensor.TYPE_PROXIMITY -> "proximity"
            Sensor.TYPE_MAGNETIC_FIELD -> "magnet"
            else -> return
        }
        rings.getValue(kind).add(event.timestamp / 1e6, event.values)
        synchronized(lastAt) { lastAt[kind] = SystemClock.elapsedRealtime() }
    }

    override fun onAccuracyChanged(sensor: Sensor, accuracy: Int) = Unit

    private fun fresh(kind: String, maxAgeMs: Long): Boolean {
        val at = synchronized(lastAt) { lastAt[kind] } ?: return false
        return SystemClock.elapsedRealtime() - at <= maxAgeMs
    }

    fun read(kind: String, from: Long, max: Int): String {
        val now = SystemClock.elapsedRealtimeNanos() / 1e6
        val ring = rings[kind] ?: return JSONObject().put("kind", kind).put("total", 0).put("rows", JSONArray()).put("now_ms", now).toString()
        return ring.read(from, max.coerceIn(0, 10_000), now).toString()
    }

    fun info(): String {
        val out = JSONObject()
        for ((kind, sensor) in sensors) {
            if (sensor == null) continue
            out.put(kind, JSONObject()
                .put("name", sensor.name)
                .put("vendor", sensor.vendor)
                .put("max_range", sensor.maximumRange.toDouble())
                .put("resolution", sensor.resolution.toDouble())
                .put("rate_hz", if (sensor.minDelay > 0) 1e6 / sensor.minDelay else 0.0)
                .put("wake_up", sensor.isWakeUpSensor))
        }
        out.put("tap", tapOn)
        return out.toString()
    }

    fun battery(): String {
        val intent: Intent = context.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED)) ?: return JSONObject().put("percent", -1).toString()
        val level = intent.getIntExtra(BatteryManager.EXTRA_LEVEL, -1)
        val scale = intent.getIntExtra(BatteryManager.EXTRA_SCALE, 100)
        val status = intent.getIntExtra(BatteryManager.EXTRA_STATUS, -1)
        val plugged = intent.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0)
        val tenths = intent.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, Int.MIN_VALUE)
        val out = JSONObject()
        out.put("percent", if (level >= 0 && scale > 0) level * 100.0 / scale else -1.0)
        out.put("charging", status == BatteryManager.BATTERY_STATUS_CHARGING || status == BatteryManager.BATTERY_STATUS_FULL || (plugged != 0 && status != BatteryManager.BATTERY_STATUS_DISCHARGING))
        out.put("plugged", plugged != 0)
        if (tenths != Int.MIN_VALUE) out.put("temperature_c", tenths / 10.0)
        return out.toString()
    }

    fun temperature(): Double {
        val hardware = context.getSystemService(HardwarePropertiesManager::class.java) ?: return Double.NaN
        return try {
            val skin = hardware.getDeviceTemperatures(HardwarePropertiesManager.DEVICE_TEMPERATURE_SKIN, HardwarePropertiesManager.TEMPERATURE_CURRENT)
                .filter { it.isFinite() && it > -40f && it < 150f }
            if (skin.isNotEmpty()) skin.max().toDouble() else Double.NaN
        } catch (e: Exception) {
            Double.NaN
        }
    }

    fun light(): Double {
        if (!fresh("light", STALE_MS * 30)) return -1.0
        return rings.getValue("light").latest()?.get(0)?.toDouble() ?: -1.0
    }

    fun proximity(): Double {
        if (sensors["proximity"] == null) return -1.0
        return rings.getValue("proximity").latest()?.get(0)?.toDouble() ?: -1.0
    }

    fun pressure(): Double {
        if (!fresh("pressure", STALE_MS * 5)) return -1.0
        return rings.getValue("pressure").latest()?.get(0)?.toDouble() ?: -1.0
    }

    fun motion(): String {
        if (!fresh("accel", STALE_MS)) return ""
        val a = rings.getValue("accel").latest() ?: return ""
        val g = rings.getValue("gyro").latest() ?: FloatArray(3)
        return JSONObject()
            .put("accel", JSONArray(a.map { it.toDouble() }))
            .put("gyro", JSONArray(g.map { it.toDouble() }))
            .toString()
    }

    companion object {
        const val FAST_US = 10_000
        const val STALE_MS = 2_000L
    }
}
