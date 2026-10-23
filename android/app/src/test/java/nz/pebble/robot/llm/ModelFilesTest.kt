package nz.pebble.robot.llm

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

class ModelFilesTest {
    @get:Rule
    val folder = TemporaryFolder()

    private val name = "gemma-4-E4B_q4_0-it.gguf"

    @Test
    fun aMissingModelSaysWhatGoesWhere() {
        val models = folder.newFolder("models")
        val hold = ModelFiles.hold(File(models, name), models, emptyList(), emptyList(), 0L, "the main model")!!
        assertEquals(ModelFiles.MISSING, hold.kind)
        assertTrue(hold.why.contains(name) && hold.why.contains(models.path) && hold.why.contains("step 8"))
    }

    @Test
    fun aModelOneFolderTooHighIsFound() {
        val models = folder.newFolder("files", "models")
        val stray = File(models.parentFile, name).apply { writeBytes(ByteArray(10)) }
        val why = ModelFiles.missing(name, models, emptyList(), listOf(stray), "the main model")
        assertTrue(why, why.contains(stray.parent) && why.contains("move it into ${models.path}"))
    }

    @Test
    fun theWrongCapitalsOrAnotherFileAreNamed() {
        val models = folder.newFolder("models")
        val capitals = ModelFiles.missing(name, models, listOf("gemma-4-e4b_q4_0-it.gguf"), emptyList(), "the main model")
        assertTrue(capitals, capitals.contains("capitals") && capitals.contains("gemma-4-e4b_q4_0-it.gguf"))
        val other = ModelFiles.missing(name, models, listOf("gemma-4-E4B-it-Q4_K_M.gguf", "LFM2.5-230M-Q8_0.gguf", ".x.gguf.part"), emptyList(), "the main model")
        assertTrue(other, other.contains("gemma-4-E4B-it-Q4_K_M.gguf, LFM2.5-230M-Q8_0.gguf") && other.contains("under Mind"))
        assertFalse(other.contains(".part"))
    }

    @Test
    fun aFileStillBeingWrittenWaitsUntilItSettles() {
        val models = folder.newFolder("models")
        val file = File(models, name).apply { writeBytes(ByteArray(10)) }
        val now = file.lastModified() + 2_000
        assertEquals(ModelFiles.COPYING, ModelFiles.hold(file, models, listOf(name), emptyList(), now, "the main model")!!.kind)
        assertNull(ModelFiles.hold(file, models, listOf(name), emptyList(), file.lastModified() + ModelFiles.SETTLE_MS + 1, "the main model"))
        assertNull(ModelFiles.hold(file, models, listOf(name), emptyList(), file.lastModified() - 60_000, "the main model"))
    }

    @Test
    fun aDamagedFileIsNotTakenForTooLittleMemory() {
        val corrupt = "llama_model_load: error loading model: tensor 'token_embd.weight' data is not within the file bounds, model is corrupted or incomplete\nllama_model_load_from_file_impl: failed to load model\n"
        val bad = ModelFiles.failure(corrupt, 1, false)
        assertFalse(bad.memory)
        assertEquals(ModelFiles.BAD_FILE, bad.kind)
        assertTrue(bad.why.contains("copy it to the phone again"))
        val unknown = ModelFiles.failure("error loading model: unknown model architecture: 'x'\n", 1, false)
        assertEquals(ModelFiles.BAD_FILE, unknown.kind)
        assertTrue(ModelFiles.failure("ggml_backend_cpu_buffer_type_alloc_buffer: failed to allocate buffer of size 5000000000\nerror loading model: unable to allocate CPU buffer\n", 1, false).memory)
        assertTrue(ModelFiles.failure("", 137, false).memory)
        assertTrue(ModelFiles.failure("", 1, false).memory)
        val projector = ModelFiles.failure("clip_init: failed to load model 'mmproj-F16.gguf'\n", 1, true)
        assertFalse(projector.memory)
        assertTrue(projector.why.contains("projector"))
    }
}
