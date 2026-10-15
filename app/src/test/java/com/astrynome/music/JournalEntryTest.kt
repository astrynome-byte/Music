package com.astrynome.music

import org.junit.Assert.assertEquals
import org.junit.Test

class JournalEntryTest {
    @Test fun acceptsEverySupportedEmotion() {
        JournalEntry.emotions.forEach { emotion ->
            assertEquals(emotion, JournalEntry("Un morceau", emotion).emotion)
        }
    }
    @Test(expected = IllegalArgumentException::class)
    fun rejectsBlankTitle() { JournalEntry("  ", "Calme") }
    @Test(expected = IllegalArgumentException::class)
    fun rejectsUnknownEmotion() { JournalEntry("Un morceau", "Inconnue") }
}
