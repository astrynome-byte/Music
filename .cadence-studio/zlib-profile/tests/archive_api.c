/* SPDX-License-Identifier: GPL-3.0-only */
#include <stdio.h>
#include <string.h>
#include <zlib.h>

/* Exercise the public contract consumed by MuseScore's ZIP container. The
 * canned raw Deflate stream is independent of this build's compressor. */
int main(void)
{
    static const unsigned char raw_hello[] = {0xcb, 0x48, 0xcd, 0xc9, 0xc9, 0x07, 0x00};
    static const unsigned char original[] = "Cadence MSCZ/MXL raw Deflate contract: 123456789";
    unsigned char decoded[256] = {0}, compressed[256] = {0};
    z_stream stream;
    if (strcmp(zlibVersion(), "1.3.2") || strcmp(zlibVersion(), ZLIB_VERSION)) return 1;
    if (crc32(0L, (const Bytef *)"123456789", 9) != 0xcbf43926UL) return 2;
    memset(&stream, 0, sizeof(stream));
    if (inflateInit2(&stream, -MAX_WBITS) != Z_OK) return 3;
    stream.next_in = (Bytef *)raw_hello; stream.avail_in = sizeof(raw_hello);
    stream.next_out = decoded; stream.avail_out = sizeof(decoded);
    if (inflate(&stream, Z_FINISH) != Z_STREAM_END || stream.total_out != 5 || memcmp(decoded, "hello", 5)) return 4;
    if (inflateEnd(&stream) != Z_OK) return 5;
    memset(&stream, 0, sizeof(stream));
    if (deflateInit2(&stream, Z_DEFAULT_COMPRESSION, Z_DEFLATED, -MAX_WBITS, 8, Z_DEFAULT_STRATEGY) != Z_OK) return 6;
    stream.next_in = (Bytef *)original; stream.avail_in = sizeof(original);
    stream.next_out = compressed; stream.avail_out = sizeof(compressed);
    if (deflate(&stream, Z_FINISH) != Z_STREAM_END) return 7;
    {
        const uLong compressed_size = stream.total_out;
        if (deflateEnd(&stream) != Z_OK) return 8;
        memset(&stream, 0, sizeof(stream)); memset(decoded, 0, sizeof(decoded));
        if (inflateInit2(&stream, -MAX_WBITS) != Z_OK) return 9;
        stream.next_in = compressed; stream.avail_in = (uInt)compressed_size;
        stream.next_out = decoded; stream.avail_out = sizeof(decoded);
        if (inflate(&stream, Z_FINISH) != Z_STREAM_END || stream.total_out != sizeof(original) || memcmp(decoded, original, sizeof(original))) return 10;
        if (inflateEnd(&stream) != Z_OK) return 11;
    }
    puts("PASS: zlib 1.3.2 static headers/library, known raw Deflate vector, CRC32 and archive API roundtrip");
    return 0;
}
