package nz.pebble.robot.brain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder

class SpeechPartsTest {
    @Test
    fun aLongFirstSentenceIsCutAtItsFirstPauseSoTheFirstWordsComeFast() {
        assertEquals(listOf("Hello there."), Parts.firstWords("Hello there."))
        val long = "Well, I can see a cat on the couch and a ball under the table over there."
        assertEquals(listOf("Well, I can see a cat on the couch and a ball under the table over there."), Parts.firstWords(long))
        val later = "I can see a cat on the couch, and a ball under the table over there by the door."
        assertEquals(listOf("I can see a cat on the couch,", "and a ball under the table over there by the door."), Parts.firstWords(later))
        val none = "I can see a cat on the couch and a ball under the table over there by the door"
        assertEquals(listOf(none), Parts.firstWords(none))
    }

    @Test
    fun keywordsBecomeOneLineTheSpotterReads() {
        val line = Keywords.line(listOf(KeywordSpec("pebble", "PE BB LE", 1.5f, 0.25f), KeywordSpec("hey pebble", "HE Y PE BB LE", 2f, 0.3f), KeywordSpec("", "X")))
        assertEquals("PE BB LE :1.5 #0.25 @pebble/HE Y PE BB LE :2.0 #0.3 @hey_pebble", line)
    }

    @Test
    fun quietSpeechIsBroughtUpToTheTargetButNoMoreThanThirtyTimes() {
        val target = Math.pow(10.0, -23.0 / 20.0)
        fun gainFor(rms: Double) = Gain.of(rms * rms * 16_000, 16_000, -23f, 30f)
        assertEquals((target / 0.01).toFloat(), gainFor(0.01), 1e-3f)
        assertEquals(30f, gainFor(0.0005), 1e-6f)
        assertEquals(Gain.MIN, gainFor(0.9), 1e-6f)
        assertEquals(30f, Gain.of(0.0, 0, -23f, 30f), 1e-6f)
    }

    @Test
    fun speechModelsThatKeepFailingToLoadRestLongerEachTime() {
        assertEquals(0L, Rest.ms(1))
        assertEquals(60 * 60_000L, Rest.ms(2))
        assertEquals(2 * 60 * 60_000L, Rest.ms(3))
        assertEquals(24 * 60 * 60_000L, Rest.ms(9))
    }

    @Test
    fun onlySettingsTheModelsDependOnReloadThem() {
        val base = HearingSettings()
        assertEquals(false, HearingSettings.parse("{\"print_after_final\": true, \"normalise\": false, \"kws_flush_s\": 0}", base).needsReload(base))
        assertEquals(true, HearingSettings.parse("{\"mode\": \"keywords\"}", base).needsReload(base))
        assertEquals(true, HearingSettings.parse("{\"min_silence_s\": 0.4}", base).needsReload(base))
        assertEquals(true, HearingSettings.parse("{\"kws_probes\": 1}", base).needsReload(base))
        val flushOff = HearingSettings.parse("{\"kws_flush_s\": 0, \"target_dbfs\": -20}", base)
        assertEquals(0f, flushOff.kwsFlushS, 1e-6f)
        assertEquals(-20f, flushOff.targetDbfs, 1e-6f)
        assertEquals(0.64f, base.kwsFlushS, 1e-6f)
    }

    @Test
    fun theNameSpotterProbesSitOnDifferentStepsOfItsGrid() {
        assertEquals(listOf(0, 2_560), HearingSettings().probeLags().toList())
        assertEquals(listOf(0), HearingSettings.parse("{\"kws_probes\": 1}").probeLags().toList())
        assertEquals(emptyList<Int>(), HearingSettings.parse("{\"kws_probes\": 0}").probeLags().toList())
        assertEquals(4, HearingSettings.parse("{\"kws_probes\": 9}").kwsProbes)
        assertEquals(listOf(0, 1_280, 2_560, 3_840), HearingSettings.parse("{\"kws_probes\": 9}").probeLags().toList())
    }

    @Test
    fun hearingSettingsKeepWhatIsNotGiven() {
        val first = HearingSettings.parse("{\"mode\": \"keywords\", \"keywords\": [{\"word\": \"pebble\", \"tokens\": \"PE BB LE\"}], \"min_silence_s\": 0.3}")
        assertEquals(HearingSettings.MODE_KEYWORDS, first.mode)
        assertEquals(listOf(KeywordSpec("pebble", "PE BB LE")), first.keywords)
        assertEquals(0.3f, first.minSilenceS, 1e-6f)
        val second = HearingSettings.parse("{\"vad_threshold\": 0.6, \"mode\": \"shout\"}", first)
        assertEquals(HearingSettings.MODE_KEYWORDS, second.mode)
        assertEquals(0.6f, second.vadThreshold, 1e-6f)
        assertEquals(0.3f, second.minSilenceS, 1e-6f)
    }

    @Test
    fun theSegmenterOpensPausesAndClosesOnTheAgreedTimes() {
        val seg = Segmenter(0.5f, 0.1f, 0.25f, 20f)
        val window = 512.0 / 16_000
        val steps = ArrayList<Segmenter.Step>()
        val talk = List(3) { 0.1f } + List(20) { 0.9f } + List(3) { 0.1f } + List(5) { 0.9f } + List(12) { 0.05f }
        talk.forEach { steps += seg.step(it) }
        val start = steps.filterIsInstance<Segmenter.Step.Start>().single()
        assertEquals(3L, start.firstSpeechWindow)
        assertEquals(3 + 3, steps.indexOf(start))
        val pauses = steps.filterIsInstance<Segmenter.Step.Pause>()
        assertEquals(listOf(23L, 31L), pauses.map { it.silenceWindow })
        assertTrue(steps.contains(Segmenter.Step.Resume))
        val end = steps.filterIsInstance<Segmenter.Step.End>().single()
        assertEquals(31L, end.silenceWindow)
        assertEquals(31 + Math.ceil(0.25 / window).toInt() - 1, steps.indexOf(end))
        assertTrue(!seg.speaking)
    }

    private fun wav(samples: ShortArray, rate: Int = 16_000, channels: Int = 1): ByteArray {
        val data = ByteBuffer.allocate(samples.size * 2).order(ByteOrder.LITTLE_ENDIAN)
        samples.forEach { data.putShort(it) }
        val out = ByteArrayOutputStream()
        val head = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
        head.put("RIFF".toByteArray()).putInt(36 + samples.size * 2).put("WAVE".toByteArray())
        head.put("fmt ".toByteArray()).putInt(16).putShort(1).putShort(channels.toShort()).putInt(rate).putInt(rate * 2 * channels).putShort((2 * channels).toShort()).putShort(16)
        head.put("data".toByteArray()).putInt(samples.size * 2)
        out.write(head.array())
        out.write(data.array())
        return out.toByteArray()
    }

    @Test
    fun aTestWavIsRead() {
        val samples = shortArrayOf(0, 100, -100, 32767, -32768)
        assertEquals(samples.toList(), Wav.pcm16(wav(samples)).toList())
        try {
            Wav.pcm16(wav(samples, rate = 8_000))
            throw AssertionError("should have refused")
        } catch (e: IllegalArgumentException) {
            assertTrue(e.message!!.contains("16000"))
        }
        assertEquals(3, Microphone.lastLoud(shortArrayOf(0, 2000, 10, -3000, 5)))
    }

    @Test
    fun aWideStereoTestWavKeepsItsRateAndChannels() {
        val samples = shortArrayOf(1, -1, 2, -2, 3, -3)
        val sound = Wav.read(wav(samples, rate = 48_000, channels = 2))
        assertEquals(48_000, sound.rate)
        assertEquals(2, sound.channels)
        assertEquals(3, sound.frames)
        assertEquals(listOf<Short>(-1, -2, -3), sound.channel(1).toList())
        assertEquals(listOf<Short>(1, 2, 3), Wav.pcm16(wav(samples, rate = 16_000, channels = 2)).toList())
        assertEquals(2, Microphone.lastLoud(shortArrayOf(0, 0, 0, 2000, 0, -3000, 5, 0), 2, 1))
    }

    @Test
    fun aMicPlanIsOnlyTakenWhenItCanBeBroughtDownToSixteenKilohertz() {
        val base = MicPlan()
        assertEquals(MicPlan(48_000, 2, 1), MicPlan.parse(org.json.JSONObject("{\"mic_rate\": 48000, \"mic_channels\": 2, \"mic_speech_channel\": 1}"), base))
        assertEquals(base, MicPlan.parse(org.json.JSONObject("{\"mic_rate\": 44100}"), base))
        assertEquals(base, MicPlan.parse(org.json.JSONObject("{\"mic_channels\": 3}"), base))
        assertEquals(base, MicPlan.parse(org.json.JSONObject("{\"mic_speech_channel\": 1}"), base))
        assertTrue(MicPlan(96_000, 1, 0).wide)
        assertTrue(!base.wide)
    }

    @Test
    fun theSpottersLevelIsWorkedOutSlowlyFromSpeechOnly() {
        val level = SpotLevel()
        assertEquals(1f, level.gain(-23f, 30f), 0f)
        val quiet = FloatArray(512) { if (it % 2 == 0) 0.00316f else -0.00316f }
        repeat(10) { level.heard(quiet) }
        assertEquals(22.4f, level.gain(-23f, 30f), 0.3f)
        val loud = FloatArray(512) { if (it % 2 == 0) 0.1f else -0.1f }
        level.heard(loud)
        assertTrue(level.gain(-23f, 30f) > 2.0f)
        repeat(2_000) { level.heard(loud) }
        assertEquals(0.708f, level.gain(-23f, 30f), 0.02f)
        val silent = SpotLevel()
        repeat(5) { silent.heard(FloatArray(512)) }
        assertEquals(30f, silent.gain(-23f, 30f), 0f)
    }
}
