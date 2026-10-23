package nz.pebble.robot.eyes

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Test

class LightAndZoomTest {
    @Test
    fun theTorchAlwaysEndsByItself() {
        assertEquals(TorchRules.DEFAULT_S, TorchRules.seconds(0.0), 0.0)
        assertEquals(TorchRules.DEFAULT_S, TorchRules.seconds(Double.NaN), 0.0)
        assertEquals(TorchRules.LONGEST_S, TorchRules.seconds(1e9), 0.0)
        assertEquals(120.0, TorchRules.seconds(120.0), 0.0)
    }

    @Test
    fun aGlowLevelBecomesOneOfThePhonesSteps() {
        assertEquals(1, TorchRules.step(0.0, 5))
        assertEquals(5, TorchRules.step(1.0, 5))
        assertEquals(3, TorchRules.step(0.5, 5))
        assertEquals(1, TorchRules.step(0.7, 1))
        assertEquals(5, TorchRules.step(Double.NaN, 5))
    }

    @Test
    fun aLensThatFallsShortIsMadeUpWithACrop() {
        assertEquals(1.0, Zoom.crop(4.0, 4.0), 1e-9)
        assertEquals(1.0, Zoom.crop(4.0, 3.995), 1e-9)
        assertEquals(2.0, Zoom.crop(4.0, 2.0), 1e-9)
        assertEquals(4.0, Zoom.crop(4.0, Double.NaN), 1e-9)
        assertEquals(Zoom.DEFAULT, Zoom.asked(0.0), 0.0)
        assertEquals(Zoom.MOST, Zoom.asked(50.0), 0.0)
        assertEquals(1.0, Zoom.asked(0.5), 0.0)
    }

    @Test
    fun theCropIsTakenFromTheMiddle() {
        assertArrayEquals(intArrayOf(1500, 1125, 1000, 750), Zoom.centre(4000, 3000, 4.0))
        assertArrayEquals(intArrayOf(0, 0, 640, 480), Zoom.centre(640, 480, 1.0))
    }

    @Test
    fun aBigPictureIsDecodedSmallerWhenItCanBe() {
        assertEquals(2, Zoom.reduce(4000, 1.0, 1536))
        assertEquals(1, Zoom.reduce(4000, 2.0, 1536))
        assertEquals(4, Zoom.reduce(4000, 1.0, 768))
        assertEquals(1, Zoom.reduce(1000, 1.0, 1536))
    }

    @Test
    fun theTelephotosFieldOfViewComesFromItsFocalLength() {
        assertEquals(23.5, Zoom.fovDeg(19.0, 7.9), 0.5)
        assertEquals(Double.NaN, Zoom.fovDeg(0.0, 7.9), 0.0)
    }
}
