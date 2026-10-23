package nz.pebble.robot

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class ConfigTest {
    private val self = File("/data/user/0/nz.pebble.robot/files/self")

    @Test
    fun theBrainGetsTheAndroidBodyAndTheFacePage() {
        val args = PebbleConfig().brainArgs(self, null, "192.168.1.50")
        assertEquals(listOf("--self", self.path, "--body", "android", "--mind", "llama"), args.take(6))
        assertTrue(args.containsAll(listOf("--screen", "--screen-port", "8765")))
        assertFalse("--sub" in args)
        assertTrue(PebbleConfig(sub = true).brainArgs(self, null, "192.168.1.50").containsAll(listOf("--sub", "lfm25_230m")))
        assertEquals("tcp:192.168.1.50:7777", args[args.indexOf("--link") + 1])
    }

    @Test
    fun linkChoicesBecomeTheRightFlags() {
        assertEquals("tcp:pebble.local:7777", PebbleConfig().linkSpec(null))
        assertEquals("tcp:10.0.2.2:7777", PebbleConfig(host = "10.0.2.2").linkSpec(null))
        assertEquals("tcp:127.0.0.1:7778", PebbleConfig(link = PebbleConfig.LINK_USB).linkSpec("1.2.3.4"))
        val sim = PebbleConfig(link = PebbleConfig.LINK_SIM, mind = "scripted", dryRun = true, camera = false).brainArgs(self, File("/sdcard/p.json"), null)
        assertTrue("--sim" in sim && "--dry-run" in sim && "--no-camera" in sim)
        assertFalse("--link" in sim || "--sub" in sim)
        assertEquals(File("/sdcard/p.json").path, sim[sim.indexOf("--body") + 1])
    }

    @Test
    fun badValuesFromTheFileFallBackToSafeOnes() {
        val text = "{\"link\":\"bluetooth\",\"host\":\"bad host; rm -rf\",\"port\":99999,\"mind\":\"x\",\"mainModel\":\"../../etc.gguf\",\"extra\":[\"--seed\",\"4\"]}"
        val c = PebbleConfig.fromJson(text)
        assertEquals(PebbleConfig.LINK_WIFI, c.link)
        assertEquals(PebbleConfig.AUTO, c.host)
        assertEquals(7777, c.port)
        assertEquals("llama", c.mind)
        assertEquals(PebbleConfig().mainModel, c.mainModel)
        assertEquals(listOf("--seed", "4"), c.extra)
        val wanted = PebbleConfig(link = "usb", dryRun = true, testImage = "cat.jpg")
        assertEquals(wanted, PebbleConfig.fromJson(wanted.toJson().toString()))
    }

    @Test
    fun modelNamesCannotLeaveTheModelsFolder() {
        assertTrue(Models.validName("gemma-4-E4B-it-Q4_K_M.gguf"))
        assertFalse(Models.validName("../x.gguf"))
        assertFalse(Models.validName("a/b.gguf"))
        assertFalse(Models.validName(".hidden.gguf"))
        assertFalse(Models.validName("model.bin"))
    }
}
