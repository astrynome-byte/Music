package com.astrynome.music

import android.app.Application
import android.content.Context
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.*
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config

/** Launches the real Activity/Compose UI on Robolectric; not a physical-device test. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class MusicScreenTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()
    @Before fun resetJournal() {
        compose.activity.getSharedPreferences("journal", Context.MODE_PRIVATE).edit().clear().commit()
        compose.activityRule.scenario.recreate()
        compose.waitForIdle()
    }
    @Test fun allMainScreensLaunch() {
        listOf("Journal", "Audio", "Découvrir", "YouTube").forEach { tab ->
            compose.onNodeWithTag("nav_$tab").performClick()
            compose.onNodeWithTag("screen_$tab").assertExists()
        }
    }
    @Test fun journalEntrySurvivesActivityRecreation() {
        compose.onNodeWithTag("journal_title").performTextInput("Morceau de test persistant")
        compose.onNodeWithTag("journal_add").performClick()
        compose.activityRule.scenario.recreate()
        compose.waitForIdle()
        compose.onNodeWithTag("screen_Journal").performScrollToNode(hasText("Morceau de test persistant"))
        compose.onNodeWithText("Morceau de test persistant").assertExists()
        assertEquals("Morceau de test persistant", MusicStore(compose.activity).entries().single().title)
    }
    @Test fun analyzesBundledAudioWithoutNetwork() {
        compose.onNodeWithTag("nav_Audio").performClick()
        compose.onNodeWithTag("screen_Audio").performScrollToNode(hasText("Analyser"))
        compose.onNodeWithText("Analyser").performClick()
        compose.waitUntil(15000) { compose.onAllNodesWithTag("audio_analysis").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("audio_analysis").assertTextContains("Énergie RMS", substring = true)
    }
    @Test fun youtubeOpensCanonicalExternalLink() {
        compose.onNodeWithTag("nav_YouTube").performClick()
        compose.onNodeWithTag("screen_YouTube").performScrollToNode(hasTestTag("youtube_link"))
        compose.onNodeWithTag("youtube_link").performTextInput("https://music.youtube.com/watch?v=dQw4w9WgXcQ")
        compose.onNodeWithTag("screen_YouTube").performScrollToNode(hasText("Ouvrir la vidéo"))
        compose.onNodeWithText("Ouvrir la vidéo").performClick()
        val app = ApplicationProvider.getApplicationContext<Application>()
        assertEquals("https://www.youtube.com/watch?v=dQw4w9WgXcQ", shadowOf(app).nextStartedActivity.data.toString())
    }
}
