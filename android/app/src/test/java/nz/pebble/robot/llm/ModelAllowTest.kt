package nz.pebble.robot.llm

import nz.pebble.robot.net.Receiver
import nz.pebble.robot.net.SelfUpdate
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.File

class ModelAllowTest {
    @get:Rule
    val folder = TemporaryFolder()

    @Test
    fun theListHoldsThePinnedModels() {
        val gemma = ModelAllow.KNOWN.first { it.name == "gemma-4-E4B_q4_0-it.gguf" }
        assertEquals(5_154_941_280L, gemma.bytes)
        assertNotNull(ModelAllow.known(5_154_941_280L, gemma.sha256.uppercase()))
        assertNull(ModelAllow.known(5_154_941_281L, gemma.sha256))
        assertNull(ModelAllow.known(gemma.bytes, "0".repeat(64)))
        assertTrue(ModelAllow.maybeKnown(246_598_496L))
        assertTrue(ModelAllow.maybeKnown(98_653_280L))
        assertFalse(ModelAllow.maybeKnown(12345L))
        assertTrue(ModelAllow.KNOWN.all { it.sha256.length == 64 })
    }

    @Test
    fun copyingHashesWhatItWrites() {
        val data = "abc".toByteArray()
        val out = ByteArrayOutputStream()
        val (count, sha) = ModelAllow.copy(ByteArrayInputStream(data), out, 100)
        assertEquals(3L, count)
        assertEquals("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", sha)
        assertEquals("abc", out.toString())
        val file = folder.newFile("x.gguf").apply { writeBytes(data) }
        assertEquals(sha, ModelAllow.hash(file))
        val limited = ByteArrayOutputStream()
        assertEquals(2L, ModelAllow.copy(ByteArrayInputStream(data), limited, 2).first)
    }

    @Test
    fun onlyFilesCheckedAgainstTheListAreAllowed() {
        val seen = ModelAllow.Seen(File(folder.root, ".checked.json"))
        val model = folder.newFile("a.gguf").apply { writeBytes(ByteArray(10)) }
        assertFalse(seen.checked(model))
        assertFalse(seen.allowed(model))
        seen.note(model, ModelAllow.hash(model))
        assertTrue(seen.checked(model))
        assertFalse(seen.allowed(model))
        model.appendBytes(ByteArray(1))
        assertFalse(seen.checked(model))
        seen.forget("a.gguf")
        assertFalse(seen.checked(model))
    }

    @Test
    fun theDropFolderWaitsForUnknownFiles() {
        val drop = folder.newFolder("drop")
        val models = folder.newFolder("models")
        val seen = ModelAllow.Seen(File(models, ".checked.json"))
        val importer = ModelImport(drop, models, seen)
        val stranger = File(drop, "evil.gguf").apply { writeBytes(ByteArray(64)) }
        stranger.setLastModified(System.currentTimeMillis() - 60_000)
        importer.tick(System.currentTimeMillis())
        for (i in 0 until 100) {
            if (importer.busy.isEmpty() && importer.refusals().isNotEmpty()) break
            Thread.sleep(20)
        }
        assertEquals("evil.gguf", importer.refusal("evil.gguf")?.name)
        assertTrue(importer.refusal("evil.gguf")!!.why.contains("not on Pebble's list"))
        assertTrue(stranger.exists())
        assertFalse(File(models, "evil.gguf").exists())
        assertFalse(importer.waiting("evil.gguf"))
        assertEquals(listOf<String>(), ModelImport.gguf(models).map { it.name })
    }

    @Test
    fun updatesMustRaiseTheVersionCode() {
        assertNull(SelfUpdate.refusal("nz.pebble.robot", 3, "nz.pebble.robot", 4))
        assertTrue(SelfUpdate.refusal("nz.pebble.robot", 3, "nz.pebble.robot", 3)!!.contains("not higher"))
        assertTrue(SelfUpdate.refusal("nz.pebble.robot", 3, "nz.pebble.robot", 2)!!.contains("step back"))
        assertTrue(SelfUpdate.refusal("nz.pebble.robot", 3, "com.other", 9)!!.contains("not Pebble"))
        assertTrue(SelfUpdate.refusal("nz.pebble.robot", 3, null, null)!!.contains("not an APK"))
    }

    @Test
    fun theReceiverCodeMustMatchExactly() {
        assertTrue(Receiver.codeMatches("123456", "123456"))
        assertTrue(Receiver.codeMatches(" 123456 ", "123456"))
        assertFalse(Receiver.codeMatches("12345", "123456"))
        assertFalse(Receiver.codeMatches("", ""))
    }
}
