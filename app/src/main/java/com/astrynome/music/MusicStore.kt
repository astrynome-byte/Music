package com.astrynome.music

import android.content.Context
import androidx.core.content.edit
import org.json.JSONArray
import org.json.JSONObject

class MusicStore(context: Context) {
    private val preferences = context.getSharedPreferences("journal", Context.MODE_PRIVATE)
    var recoveredData = false
        private set

    fun entries(): List<JournalEntry> = read("entries") { item ->
        JournalEntry(item.getString("title"), item.getString("emotion"),
            item.optString("id").ifBlank { java.util.UUID.randomUUID().toString() },
            item.optString("sourceUri").ifBlank { null })
    }
    fun tracks(): List<AudioTrack> = read("tracks") { AudioTrack(it.getString("title"), it.getString("uri")) }
    private fun <T> read(key: String, decode: (JSONObject) -> T): List<T> {
        val raw = preferences.getString(key, "[]") ?: "[]"
        return runCatching {
            val array = JSONArray(raw)
            (0 until array.length()).mapNotNull { index ->
                runCatching { decode(array.getJSONObject(index)) }.getOrElse { recover(key, raw); null }
            }
        }.getOrElse { recover(key, raw); emptyList() }
    }
    private fun recover(key: String, raw: String) {
        recoveredData = true
        // Keep the original payload before any subsequent write.
        if (!preferences.contains("recovery_$key")) preferences.edit { putString("recovery_$key", raw) }
    }
    fun saveEntries(entries: List<JournalEntry>) {
        val array = JSONArray()
        entries.forEach { array.put(JSONObject().put("title", it.title).put("emotion", it.emotion).put("id", it.id).put("sourceUri", it.sourceUri.orEmpty())) }
        preferences.edit { putString("entries", array.toString()) }
    }
    fun saveTracks(tracks: List<AudioTrack>) {
        val array = JSONArray()
        tracks.forEach { array.put(JSONObject().put("title", it.title).put("uri", it.uri)) }
        preferences.edit { putString("tracks", array.toString()) }
    }
}
