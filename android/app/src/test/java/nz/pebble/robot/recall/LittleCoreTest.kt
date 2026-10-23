package nz.pebble.robot.recall

import nz.pebble.robot.llm.LlamaPlan
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class LittleCoreTest {
    private val pixel6Pro = listOf(1_803_000L, 1_803_000L, 1_803_000L, 1_803_000L, 2_253_000L, 2_253_000L, 2_802_000L, 2_802_000L)
    private val s22 = listOf(1_785_600L, 1_785_600L, 1_785_600L, 1_785_600L, 2_496_000L, 2_496_000L, 2_496_000L, 2_995_200L)

    @Test
    fun theSentenceModelGetsALittleCoreTheLanguageModelsLeaveFree() {
        assertEquals(listOf(7, 6, 5, 4) to listOf(1, 0), LlamaPlan.cores(pixel6Pro))
        assertEquals(2, LittleCore.pick(pixel6Pro))
        assertEquals(2, LittleCore.pick(s22))
        assertEquals(6, LittleCore.pick(pixel6Pro.reversed()))
    }

    @Test
    fun withEqualCoresOrFewCoresItStillGetsOne() {
        assertEquals(0, LittleCore.pick(List(8) { 2_000_000L }))
        assertEquals(0, LittleCore.pick(listOf(0L, 0L)))
        assertEquals(0, LittleCore.pick(listOf(1_000L, 2_000L)))
        assertNull(LittleCore.pick(emptyList()))
    }

    @Test
    fun theAllowedCoresAreReadFromTheKernelsList() {
        assertEquals(listOf(2), LittleCore.parse("2"))
        assertEquals(listOf(0, 1, 2, 3), LittleCore.parse("\t0-3"))
        assertEquals(listOf(0, 1, 2, 3, 6), LittleCore.parse("0-3,6"))
        assertNull(LittleCore.parse(""))
        assertNull(LittleCore.parse("a"))
        assertNull(LittleCore.parse("3-1"))
    }
}
