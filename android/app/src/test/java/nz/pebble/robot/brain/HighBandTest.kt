package nz.pebble.robot.brain

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.roundToInt
import kotlin.math.sin

class HighBandTest {
    private val rate = 48_000
    private var clock = 0.0

    private fun watcher() = HighBand { clock }

    private fun level(db: Double) = 32768 * Math.pow(10.0, db / 20)

    private fun play(band: HighBand, seconds: Double, speaking: Boolean = false, sample: (Double) -> Double) {
        val chunk = 960
        val total = (seconds * rate).toInt()
        var at = 0
        val noise = java.util.Random(3)
        val pcm = ShortArray(chunk)
        while (at < total) {
            for (i in 0 until chunk) {
                pcm[i] = (sample((at + i).toDouble() / rate) + noise.nextGaussian() * level(-75.0)).roundToInt().coerceIn(-32768, 32767).toShort()
            }
            at += chunk
            clock += chunk * 1000.0 / rate
            band.onWide(pcm, chunk, 1, rate, speaking)
        }
    }

    private fun rows(band: HighBand): List<JSONObject> {
        val all = JSONObject(band.read(0)).getJSONArray("rows")
        return (0 until all.length()).map { all.getJSONObject(it) }
    }

    private fun tones(band: HighBand) = rows(band).filter { it.getString("kind") == "tone" }

    @Test
    fun aSteadyMosquitoToneIsFoundAndCalledSteady() {
        val band = watcher()
        play(band, 12.0) { t -> level(-40.0) * sin(2 * PI * 17_400 * t) }
        val found = tones(band)
        val steady = found.firstOrNull { it.getString("what") == "steady" }
        assertTrue("no steady row in $found", steady != null)
        assertEquals(17_400.0, steady!!.getDouble("hz"), 47.0)
        assertEquals("steady", steady.getString("shape"))
        assertTrue("$found", steady.getDouble("over_db") > 20)
        assertTrue("$found", found.first().getString("what") == "start")
        assertTrue("$found", found.all { abs(it.getDouble("hz") - 17_400) < 100 })
    }

    @Test
    fun aToneTenDecibelsOverTheRoomIsFoundWithinTwoSeconds() {
        val band = watcher()
        play(band, 2.0) { 0.0 }
        val bin = 371 * HighBand.BIN_HZ
        play(band, 2.0) { t -> level(-86.5) * sin(2 * PI * bin * t) }
        val start = tones(band).firstOrNull { it.getString("what") == "start" }
        assertTrue(start != null)
        assertEquals(bin, start!!.getDouble("hz"), 47.0)
        assertTrue(start.getDouble("t") - 2_000 <= 2_000)
    }

    @Test
    fun twoMinutesOfHissAndClicksMakeNoTones() {
        val band = watcher()
        val random = java.util.Random(21)
        play(band, 120.0) { t -> if (random.nextInt(4_800) == 0) 20_000.0 else 0.0 }
        assertTrue(tones(band).toString(), tones(band).isEmpty())
    }

    @Test
    fun hissThatStartsAfterSilenceIsNotTakenForTonesOrData() {
        val band = HighBand { clock }
        val pcm = ShortArray(960)
        repeat(300) {
            clock += 20.0
            band.onWide(pcm, 960, 1, rate, false)
        }
        val random = java.util.Random(5)
        var last = 0.0
        play(band, 4.0) { _ ->
            val white = random.nextGaussian() * level(-50.0)
            val high = white - last
            last = white
            high
        }
        assertTrue(tones(band).toString(), tones(band).isEmpty())
    }

    @Test
    fun hissThatStartsSuddenlyAfterSilenceMakesNoToneInFortyCases() {
        val strays = ArrayList<String>()
        for (case in 1..40) {
            var now = 0.0
            val band = HighBand { now }
            val quiet = ShortArray(960)
            repeat(100 + 25 * (case % 9)) {
                now += 20.0
                band.onWide(quiet, 960, 1, rate, false)
            }
            val random = java.util.Random(case.toLong())
            val loud = level(-40.0 - (case % 7) * 5.0)
            val high = case % 2 == 0
            var last = 0.0
            val pcm = ShortArray(960)
            repeat(200) {
                for (i in 0 until 960) {
                    val white = random.nextGaussian() * loud
                    pcm[i] = (if (high) white - last else white).roundToInt().coerceIn(-32768, 32767).toShort()
                    last = white
                }
                now += 20.0
                band.onWide(pcm, 960, 1, rate, false)
            }
            val found = JSONObject(band.read(0)).getJSONArray("rows").let { rows -> (0 until rows.length()).map { rows.getJSONObject(it) }.filter { it.getString("kind") == "tone" } }
            if (found.isNotEmpty()) strays += "case $case: $found"
        }
        assertTrue(strays.joinToString(" | "), strays.isEmpty())
    }

    @Test
    fun aPulsingToneIsCalledPulsingWithItsPeriod() {
        val band = watcher()
        play(band, 9.0) { t -> if (t % 1.0 < 0.2) level(-45.0) * sin(2 * PI * 18_000 * t) else 0.0 }
        play(band, 0.5) { 0.0 }
        val ends = tones(band).filter { it.getString("what") == "end" }
        assertTrue("only ${ends.size} pulses: ${tones(band)}", ends.size >= 7)
        val last = ends.last()
        assertEquals("$ends", "pulsing", last.getString("shape"))
        assertEquals(1.0, last.getDouble("period_s"), 0.05)
        assertTrue(last.getDouble("regular") > 0.9)
    }

    @Test
    fun aSweepIsCalledSweeping() {
        val band = watcher()
        var phase = 0.0
        play(band, 3.0) { t ->
            phase += 2 * PI * (16_000 + 1_000 * t) / rate
            level(-40.0) * sin(phase)
        }
        play(band, 0.5) { 0.0 }
        val end = tones(band).last { it.getString("what") == "end" }
        assertEquals("sweeping", end.getString("shape"))
        assertTrue(end.getInt("low_hz") < 16_200 && end.getInt("high_hz") > 18_800)
    }

    @Test
    fun hoppingDataTonesMakeOneDataRow() {
        val band = watcher()
        val random = java.util.Random(9)
        val symbols = Array(40) { IntArray(3) { 320 + random.nextInt(96) } }
        play(band, 2.56) { t ->
            val symbol = symbols[((t / 0.064).toInt()).coerceAtMost(symbols.size - 1)]
            symbol.sumOf { level(-50.0) * sin(2 * PI * it * HighBand.BIN_HZ * t) }
        }
        play(band, 1.0) { 0.0 }
        val found = tones(band)
        val data = found.filter { it.getString("shape") == "data" }
        assertEquals("rows: $found", 1, data.size)
        assertTrue(data.single().getInt("tones") >= 20)
        assertTrue("plain rows: $found", found.size <= 3)
    }

    @Test
    fun aShortBurstNearNineteenKilohertzLooksLikeABeacon() {
        val band = watcher()
        play(band, 1.0) { 0.0 }
        play(band, 0.4) { t -> level(-45.0) * sin(2 * PI * 19_000 * t) }
        play(band, 1.0) { 0.0 }
        val end = tones(band).single { it.getString("what") == "end" }
        assertEquals("beacon", end.getString("shape"))
    }

    @Test
    fun speechAndMusicBelowEightKilohertzMakeNoTones() {
        val band = watcher()
        play(band, 5.0) { t -> (1..35).sumOf { h -> level(-30.0 - h) * sin(2 * PI * 200 * h * t) } }
        assertTrue(tones(band).isEmpty())
        val levels = rows(band).filter { it.getString("kind") == "levels" }
        assertTrue(levels.size >= 4)
        assertEquals(8, levels.first().getJSONArray("db").length())
        assertEquals(15_000, levels.first().getInt("from_hz"))
    }

    @Test
    fun theWheelsTwentyKilohertzLineIsPebblesOwnWhileItMoves() {
        val band = watcher()
        band.moving = true
        play(band, 1.0) { t -> level(-40.0) * sin(2 * PI * 20_000 * t) }
        band.moving = false
        play(band, 0.5) { 0.0 }
        val end = tones(band).last()
        assertTrue(end.getBoolean("own"))
    }

    @Test
    fun pebblesOwnSoundsAreNotWatched() {
        val band = watcher()
        play(band, 2.0, speaking = true) { t -> level(-40.0) * sin(2 * PI * 17_000 * t) }
        assertTrue(tones(band).isEmpty())
    }

    @Test
    fun sixteenKilohertzSoundGivesNoHighBand() {
        val band = watcher()
        assertFalse(JSONObject(band.read(0)).getBoolean("on"))
        band.onWide(ShortArray(320), 320, 1, 16_000, false)
        val state = JSONObject(band.read(0))
        assertFalse(state.getBoolean("on"))
        assertTrue(state.getString("problem").contains("48 or 96 kHz"))
    }

    @Test
    fun aPathThatStopsBelowFifteenKilohertzSwitchesTheWatcherOff() {
        val band = watcher()
        band.top(15_100.0)
        play(band, 1.0) { t -> level(-40.0) * sin(2 * PI * 15_050 * t) }
        val state = JSONObject(band.read(0))
        assertFalse(state.getBoolean("on"))
        assertTrue(state.getString("problem").contains("stops at"))
    }

    @Test
    fun ninetySixKilohertzUsesTheSameBins() {
        val band = watcher()
        val wide = 96_000
        val chunk = 1_920
        val pcm = ShortArray(chunk)
        var at = 0
        repeat(600) {
            for (i in 0 until chunk) pcm[i] = (level(-40.0) * sin(2 * PI * 21_000.0 * (at + i) / wide)).roundToInt().toShort()
            at += chunk
            clock += 20.0
            band.onWide(pcm, chunk, 1, wide, false)
        }
        val state = JSONObject(band.read(0))
        assertTrue(state.getBoolean("on"))
        assertEquals(24_000, state.getInt("top_hz"))
        assertTrue(tones(band).any { abs(it.getDouble("hz") - 21_000) < 47 })
    }
}
