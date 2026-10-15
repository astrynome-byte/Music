package com.astrynome.music

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class MusicStoreTest {
    private val context: Context get() = ApplicationProvider.getApplicationContext()
    @Before fun clear() { context.getSharedPreferences("journal", Context.MODE_PRIVATE).edit().clear().commit() }
    @Test fun loadsExistingJournalWithoutLosingTitlesOrMoods() {
        context.getSharedPreferences("journal", Context.MODE_PRIVATE).edit()
            .putString("entries", """[{"title":"Ancien morceau","emotion":"Joyeux"}]""").commit()
        val store = MusicStore(context)
        val entries = store.entries()
        assertEquals("Ancien morceau", entries.single().title)
        assertEquals("Joyeux", entries.single().emotion)
        store.saveEntries(entries)
        assertEquals(entries, MusicStore(context).entries())
    }
    @Test fun preservesUnreadablePayloadBeforeRecovery() {
        val preferences = context.getSharedPreferences("journal", Context.MODE_PRIVATE)
        preferences.edit().putString("entries", "broken-json").commit()
        val store = MusicStore(context)
        assertTrue(store.entries().isEmpty())
        assertTrue(store.recoveredData)
        store.saveEntries(listOf(JournalEntry("Nouveau", "Calme")))
        assertEquals("broken-json", preferences.getString("recovery_entries", null))
    }
    @Test fun savesImportedTracksAndYouTubeEntries() {
        val store = MusicStore(context)
        val tracks = listOf(AudioTrack("WAV", "content://audio/1"))
        val entries = listOf(JournalEntry("Lien", "Calme", sourceUri = "https://youtu.be/dQw4w9WgXcQ"))
        store.saveTracks(tracks); store.saveEntries(entries)
        assertEquals(tracks, MusicStore(context).tracks())
        assertEquals(entries, MusicStore(context).entries())
    }
}
