package com.astrynome.music

import android.content.Context
import android.media.AudioAttributes
import android.media.MediaPlayer
import androidx.core.net.toUri
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue

/** MediaPlayer reads local content URIs; no storage permission or remote API needed. */
class AudioPlayer {
    private var player: MediaPlayer? = null
    var status by mutableStateOf("Aucun morceau en lecture")
        private set
    fun play(context: Context, track: AudioTrack) {
        release()
        status = "Chargement : ${track.title}"
        val next = MediaPlayer()
        player = next
        try {
            next.setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA)
                .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build())
            next.setOnPreparedListener { if (player === it) { it.start(); status = "Lecture : ${track.title}" } }
            next.setOnCompletionListener { if (player === it) { status = "Lecture terminée"; release() } }
            next.setOnErrorListener { failed, _, _ ->
                if (player === failed) { status = "Lecture impossible : format ou fichier inaccessible"; release() }
                true
            }
            next.setDataSource(context, track.uri.toUri())
            next.prepareAsync()
        } catch (_: Exception) {
            release()
            status = "Lecture impossible : réimportez le fichier ou vérifiez son format"
        }
    }
    fun pause() {
        // Releasing also cancels a pending asynchronous prepare on backgrounding.
        if (player != null) { release(); status = "Lecture arrêtée" }
    }
    fun release() { player?.release(); player = null }
}
