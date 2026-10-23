package nz.pebble.robot.keeper

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class WatchdogTest {
    private fun seen(now: Long, alive: Boolean, startedAt: Long, beat: Long = 0, code: Int? = null, exitAt: Long = 0, charging: Boolean = true, resting: Boolean = false, want: Want = Want.RUN) =
        Seen(now, want, alive, startedAt, beat, code, exitAt, charging, resting)

    @Test
    fun startsOnceAndLeavesAHealthyBrainAlone() {
        val dog = Watchdog()
        assertTrue(dog.decide(seen(1_000, false, 0)) is Act.Start)
        assertTrue(dog.decide(seen(6_000, false, 1_000)) is Act.Wait)
        assertEquals(Act.Nothing, dog.decide(seen(30_000, true, 1_000, beat = 29_000)))
        assertEquals(Act.Nothing, dog.decide(seen(400_000, true, 1_000, beat = 398_000)))
        assertEquals(0, dog.restarts)
    }

    @Test
    fun aBrainThatStopsAnsweringIsKilledAndStartedAgain() {
        val dog = Watchdog()
        dog.decide(seen(0, false, 0))
        assertEquals(Act.Nothing, dog.decide(seen(100_000, true, 1, beat = 0)))
        assertTrue(dog.decide(seen(250_000, true, 1, beat = 150_000)) is Act.Kill)
        assertTrue(dog.decide(seen(255_000, false, 1)) is Act.Wait)
        assertTrue(dog.decide(seen(258_000, false, 1)) is Act.Start)
    }

    @Test
    fun aDeadBrainIsRestartedWithGrowingWaits() {
        val dog = Watchdog()
        dog.decide(seen(0, false, 0))
        var start = 1L
        val waits = ArrayList<Long>()
        var now = 100_000L
        repeat(4) {
            val exitAt = now
            var act = dog.decide(seen(now, false, start, code = 1, exitAt = exitAt))
            var waited = 0L
            while (act !is Act.Start) {
                now += 500
                waited += 500
                act = dog.decide(seen(now, false, start, code = 1, exitAt = exitAt))
            }
            waits += waited
            start = now
            now += 25_000
        }
        assertTrue(waits.zipWithNext().all { (a, b) -> b >= a })
        assertTrue(waits.last() >= 29_500)
    }

    @Test
    fun aLowBatteryRestWaitsForTheCharger() {
        val dog = Watchdog()
        dog.decide(seen(0, false, 0))
        assertTrue(dog.decide(seen(100_000, false, 1, code = 3, exitAt = 99_000, charging = false, resting = true)) is Act.Rest)
        assertTrue(dog.decide(seen(105_000, false, 1, code = 3, exitAt = 99_000, charging = false, resting = true)) is Act.Wait)
        assertTrue(dog.decide(seen(110_000, false, 1, code = 3, exitAt = 99_000, charging = true, resting = true)) is Act.Start)
    }

    @Test
    fun aSealedSelfIsNotRetriedInALoop() {
        val dog = Watchdog()
        dog.decide(seen(0, false, 0))
        val act = dog.decide(seen(100_000, false, 1, code = 4, exitAt = 99_000))
        assertTrue(act is Act.Wait && act.why.contains("sealed"))
        assertTrue(dog.decide(seen(400_000, false, 1, code = 4, exitAt = 99_000)) is Act.Wait)
        assertTrue(dog.decide(seen(700_001, false, 1, code = 4, exitAt = 99_000)) is Act.Start)
    }

    @Test
    fun aPauseStopsTheBrainAndKeepsItStopped() {
        val dog = Watchdog()
        assertTrue(dog.decide(seen(10_000, true, 1, want = Want.PAUSE)) is Act.Stop)
        assertEquals(Act.Nothing, dog.decide(seen(20_000, false, 1, want = Want.PAUSE)))
    }

    @Test
    fun aHoldStopsTheBrainUntilItIsLetGoThenStartsItAtOnce() {
        val dog = Watchdog()
        dog.decide(seen(0, false, 0))
        assertTrue(dog.decide(seen(100_000, true, 1, want = Want.HOLD)) is Act.Stop)
        assertEquals(Act.Nothing, dog.decide(seen(102_000, false, 1, code = 0, exitAt = 101_000, want = Want.HOLD)))
        dog.planned()
        assertTrue(dog.decide(seen(105_000, false, 1, code = 0, exitAt = 101_000)) is Act.Start)
    }

    @Test
    fun theBrainsHeartbeatNamesItsProcess() {
        assertEquals(3724, BrainProcess.pidOf("1792420538.823 3724  "))
        assertEquals(null, BrainProcess.pidOf("1792420538.823"))
        assertEquals(null, BrainProcess.pidOf("garbage here"))
        assertEquals("nz.pebble.robot:brain", BrainProcess.nameOf("nz.pebble.robot:brain".toByteArray() + byteArrayOf(0, 0)))
    }

    @Test
    fun aPlannedRestartDoesNotWait() {
        val dog = Watchdog()
        dog.decide(seen(0, false, 0))
        dog.decide(seen(100_000, false, 1, code = 1, exitAt = 99_000))
        dog.decide(seen(130_000, false, 1))
        dog.planned()
        assertTrue(dog.decide(seen(200_000, false, 150_000, code = 0, exitAt = 199_000)) is Act.Start)
    }
}
