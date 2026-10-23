package nz.pebble.robot.admin

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class AdminPinTest {
    @get:Rule
    val folder = TemporaryFolder()

    @Test
    fun aPinIsKeptOnlyAsASaltedHashAndChecked() {
        val file = folder.root.resolve("pin.json")
        val now = 1_000_000L
        val pin = AdminPin(file, { now }, 1_000)
        assertFalse(pin.isSet())
        pin.set("482913")
        assertTrue(pin.isSet())
        assertFalse(file.readText().contains("482913"))
        assertTrue(pin.check("482913").ok)
        assertFalse(pin.check("000000").ok)
        val otherFile = folder.root.resolve("other.json")
        AdminPin(otherFile, { now }, 1_000).set("482913")
        assertNotEquals(file.readText(), otherFile.readText())
    }

    @Test
    fun wrongPinsLockForLongerEachTime() {
        val file = folder.root.resolve("pin.json")
        var now = 5_000_000L
        val pin = AdminPin(file, { now }, 1_000)
        pin.set("123456")
        repeat(AdminPin.FREE_TRIES) { assertEquals(0L, pin.check("999999").waitMs) }
        assertEquals(30_000L, pin.check("999999").waitMs)
        assertFalse(pin.check("123456").ok)
        now += 30_001
        assertEquals(60_000L, pin.check("999999").waitMs)
        now += 60_001
        assertTrue(pin.check("123456").ok)
        assertEquals(0L, pin.check("999999").waitMs)
    }

    @Test
    fun onlySixToTwelveDigitsMakeAPin() {
        assertTrue(AdminPin.valid("123456"))
        assertTrue(AdminPin.valid("123456789012"))
        assertFalse(AdminPin.valid("12345"))
        assertFalse(AdminPin.valid("1234567890123"))
        assertFalse(AdminPin.valid("12345a"))
        assertEquals(AdminPin.MAX_LOCK_MS, AdminPin.lockFor(40))
    }
}
