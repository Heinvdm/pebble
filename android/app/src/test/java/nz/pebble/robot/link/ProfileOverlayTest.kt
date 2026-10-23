package nz.pebble.robot.link

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ProfileOverlayTest {
    private val pushed = JSONObject(
        """
        {
          "name": "mine",
          "link": "tcp:evil:7777",
          "drive": {"cpm": 21.3, "wheel_track_mm": 168, "max_speed_mm_s": 5000, "max_power": 1000},
          "tilt": {"min": -90, "max": 120},
          "eyes": {"front": {"fov_h_deg": 78.5, "rotate": 90, "mirror": true, "source": "x"}, "rear": {"fov_h_deg": 400, "rotate": 45}, "detect": {"backend": "evil"}},
          "safety": {"enabled": false, "hearing": {"kind": "command", "command": ["sh", "-c", "rm -rf /"]}},
          "power": {"shutdown_command": ["reboot"]},
          "firmware_settings": {"edge": "2000", "stop": "0"},
          "hearing": {"kind": "command"}
        }
        """.trimIndent(),
    )

    @Test
    fun onlyTheSafeFieldsAreKept() {
        val kept = ProfileOverlay.clean(pushed)
        assertEquals(setOf("eyes", "drive"), kept.keys().asSequence().toSet())
        assertEquals(setOf("cpm", "wheel_track_mm"), kept.getJSONObject("drive").keys().asSequence().toSet())
        assertEquals(21.3, kept.getJSONObject("drive").getDouble("cpm"), 1e-9)
        val front = kept.getJSONObject("eyes").getJSONObject("front")
        assertEquals(setOf("fov_h_deg", "rotate", "mirror"), front.keys().asSequence().toSet())
        assertEquals(90, front.getInt("rotate"))
        assertFalse(kept.getJSONObject("eyes").has("rear"))
        assertFalse(kept.toString().contains("command"))
    }

    @Test
    fun outOfRangeValuesAreLeftOut() {
        val kept = ProfileOverlay.clean(JSONObject("""{"drive": {"cpm": 1000, "wheel_track_mm": 9}, "eyes": {"front": {"fov_h_deg": "wide", "mirror": "yes"}}}"""))
        assertEquals(0, kept.length())
        assertEquals(0.0, ProfileOverlay.clean(JSONObject("""{"drive": {"cpm": 0}}""")).getJSONObject("drive").getDouble("cpm"), 0.0)
    }

    @Test
    fun theOverlayOnlyChangesItsOwnFields() {
        val base = JSONObject("""{"name": "android", "drive": {"max_power": 600, "cpm": 20.7, "wheel_track_mm": 165}, "eyes": {"front": {"fov_h_deg": 81.1, "width": 640}, "max_fps": 10}, "safety": {"hearing": {"kind": "android"}}}""")
        val merged = ProfileOverlay.merge(base, pushed)
        assertEquals("android", merged.getString("name"))
        assertEquals(600, merged.getJSONObject("drive").getInt("max_power"))
        assertEquals(21.3, merged.getJSONObject("drive").getDouble("cpm"), 1e-9)
        assertEquals(640, merged.getJSONObject("eyes").getJSONObject("front").getInt("width"))
        assertEquals(78.5, merged.getJSONObject("eyes").getJSONObject("front").getDouble("fov_h_deg"), 1e-9)
        assertEquals("android", merged.getJSONObject("safety").getJSONObject("hearing").getString("kind"))
        assertFalse(merged.has("power") || merged.has("firmware_settings") || merged.has("tilt"))
        assertTrue(ProfileOverlay.describe(ProfileOverlay.clean(pushed)).contains("drive cpm"))
    }
}
