package nz.pebble.robot.ui

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class HouseInputTest {
    @Test
    fun aLatitudeAndLongitudeAreToldApartFromATown() {
        assertEquals(-41.29 to 174.78, HouseInput.latLon("-41.29, 174.78"))
        assertEquals(-41.29 to 174.78, HouseInput.latLon(" -41.29 174.78 "))
        assertEquals(-41.0 to 174.0, HouseInput.latLon("-41;174"))
        assertNull(HouseInput.latLon("Wellington"))
        assertNull(HouseInput.latLon("-95, 172"))
        assertNull(HouseInput.latLon("-43, 190"))
    }

    @Test
    fun grownUpsAreSplitOnCommas() {
        assertEquals(listOf("Ina", "Sam"), HouseInput.names(" Ina, Sam ,, Ina"))
        assertTrue(HouseInput.names("  ").isEmpty())
    }

    @Test
    fun theStateReadsInPlainWordsAndNeverShowsAPassword() {
        val house = JSONObject("""{"place": {"name": "Wellington", "lat": -41.29, "lon": 174.78}, "guest_wifi": {"ssid": "Guests", "security": "nopass"}, "children_arrivals": true, "guardians": 2, "cooking_watch": false, "tsunami_zone": null, "passphrase_set": false, "sealed": true}""")
        val text = HouseInput.describe(house)
        assertTrue(text, text.contains("Home: Wellington (-41.29, 174.78)."))
        assertTrue(text, text.contains("\"Guests\" (open)"))
        assertTrue(text, text.contains("on, with 2 grown-ups besides the owner"))
        assertTrue(text, text.contains("Cooking watch: off."))
        assertTrue(text, text.contains("not answered"))
        assertTrue(!text.contains("passphrase"))
        assertEquals("", HouseInput.tsunami(house))
        assertEquals("yes", HouseInput.tsunami(JSONObject("{\"tsunami_zone\": true}")))
        assertEquals("no", HouseInput.tsunami(JSONObject("{\"tsunami_zone\": false}")))
    }

    @Test
    fun aSealedSelfWithASpokenPassphraseSaysWhyNothingCanChange() {
        val house = JSONObject("""{"place": null, "guest_wifi": null, "children_arrivals": false, "guardians": 0, "cooking_watch": true, "tsunami_zone": true, "passphrase_set": true, "sealed": true}""")
        val text = HouseInput.describe(house)
        assertTrue(text, text.contains("not set, so Pebble can't work out sunrise and sunset"))
        assertTrue(text, text.contains("can't be changed here"))
    }

    @Test
    fun aSealedSelfWithAnOwnersPasswordAsksForItAndCountsWhatWaits() {
        val house = JSONObject("""{"place": null, "guest_wifi": null, "children_arrivals": false, "guardians": 0, "cooking_watch": true, "tsunami_zone": null, "passphrase_set": true, "sealed": true, "password_works": true, "waiting": 2}""")
        val text = HouseInput.describe(house)
        assertTrue(text, text.contains("type the owner's password"))
        assertTrue(text, text.contains("2 changes sent, waiting for Pebble to take them."))
        assertTrue(!HouseInput.describe(JSONObject(house.toString()).put("waiting", 0)).contains("waiting for Pebble"))
        assertTrue(HouseInput.describe(JSONObject(house.toString()).put("waiting", 1)).contains("1 change sent, waiting for Pebble to take it."))
    }
}
