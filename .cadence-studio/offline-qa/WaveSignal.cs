// SPDX-License-Identifier: GPL-3.0-only
using System;
using System.IO;
using System.Text;

public sealed class CadenceOfflineWaveResult
{
    public string Format { get; set; }
    public int Channels { get; set; }
    public int SampleRate { get; set; }
    public int BitsPerSample { get; set; }
    public long Frames { get; set; }
    public long Samples { get; set; }
    public double DurationSeconds { get; set; }
    public long NonFiniteSamples { get; set; }
    public long ClippedSamples { get; set; }
    public long NonZeroSamples { get; set; }
    public double PeakAbsolute { get; set; }
    public double Rms { get; set; }
    public bool Passed { get; set; }
}

public static class CadenceOfflineWaveV1
{
    // Inspect every decoded sample, including silence and all channels. This
    // proves a bounded, finite, non-silent export; it is not a listening test.
    public static CadenceOfflineWaveResult Inspect(string path)
    {
        var info = new FileInfo(path);
        if (info.Length < 44 || info.Length > 134217728)
            throw new InvalidDataException("WAV length outside 44 bytes..128 MiB.");
        byte[] bytes = File.ReadAllBytes(path);
        if (Encoding.ASCII.GetString(bytes, 0, 4) != "RIFF" ||
            Encoding.ASCII.GetString(bytes, 8, 4) != "WAVE" ||
            (long)BitConverter.ToUInt32(bytes, 4) + 8 != bytes.Length)
            throw new InvalidDataException("Only a complete little-endian RIFF/WAVE is accepted.");
        int format = 0, channels = 0, rate = 0, bits = 0, align = 0;
        long byteRate = 0;
        int dataOffset = -1, dataBytes = -1;
        bool seenFormat = false;
        for (long position = 12; position < bytes.Length; )
        {
            if (position + 8 > bytes.Length) throw new InvalidDataException("Truncated chunk header.");
            int start = checked((int)position);
            string name = Encoding.ASCII.GetString(bytes, start, 4);
            long size = BitConverter.ToUInt32(bytes, start + 4);
            long next = position + 8 + size + (size & 1);
            if (next > bytes.Length) throw new InvalidDataException("Truncated chunk data or padding.");
            int payload = start + 8;
            if (name == "fmt ")
            {
                if (seenFormat || size < 16) throw new InvalidDataException("Missing/duplicate short format chunk.");
                seenFormat = true;
                format = BitConverter.ToUInt16(bytes, payload);
                channels = BitConverter.ToUInt16(bytes, payload + 2);
                rate = checked((int)BitConverter.ToUInt32(bytes, payload + 4));
                byteRate = BitConverter.ToUInt32(bytes, payload + 8);
                align = BitConverter.ToUInt16(bytes, payload + 12);
                bits = BitConverter.ToUInt16(bytes, payload + 14);
                if (format == 65534)
                {
                    if (size < 40 || BitConverter.ToUInt16(bytes, payload + 16) < 22 ||
                        BitConverter.ToUInt16(bytes, payload + 18) != bits)
                        throw new InvalidDataException("Unsupported extensible sample precision.");
                    byte[] guidBytes = new byte[16];
                    Array.Copy(bytes, payload + 24, guidBytes, 0, 16);
                    var subtype = new Guid(guidBytes);
                    if (subtype == new Guid("00000001-0000-0010-8000-00aa00389b71")) format = 1;
                    else if (subtype == new Guid("00000003-0000-0010-8000-00aa00389b71")) format = 3;
                    else throw new InvalidDataException("Unsupported extensible WAV subformat.");
                }
            }
            if (name == "data")
            {
                if (dataOffset != -1) throw new InvalidDataException("Multiple WAV data chunks.");
                dataOffset = payload; dataBytes = checked((int)size);
            }
            position = next;
        }
        if (!seenFormat || dataOffset < 0 || channels < 1 || channels > 8 || rate < 8000 || rate > 192000 ||
            !((format == 1 && (bits == 16 || bits == 24 || bits == 32)) ||
              (format == 3 && (bits == 32 || bits == 64))) ||
            align != channels * (bits / 8) || byteRate != (long)rate * align ||
            dataBytes == 0 || dataBytes % align != 0)
            throw new InvalidDataException("Unsupported or inconsistent WAV format/data.");
        var result = new CadenceOfflineWaveResult {
            Format = format == 1 ? "PCM" : "IEEE_FLOAT", Channels = channels, SampleRate = rate,
            BitsPerSample = bits, Frames = dataBytes / align, Samples = dataBytes / (bits / 8)
        };
        result.DurationSeconds = (double)result.Frames / rate;
        if (result.DurationSeconds < 0.25 || result.DurationSeconds > 120)
            throw new InvalidDataException("Export duration outside 0.25..120 seconds.");
        double sumSquares = 0;
        int step = bits / 8;
        for (int p = dataOffset; p < dataOffset + dataBytes; p += step)
        {
            double value;
            bool clipped = false;
            if (format == 3) value = bits == 32 ? BitConverter.ToSingle(bytes, p) : BitConverter.ToDouble(bytes, p);
            else if (bits == 16) {
                int raw = BitConverter.ToInt16(bytes, p);
                clipped = raw == Int16.MinValue || raw == Int16.MaxValue;
                value = raw / 32768.0;
            } else if (bits == 24) {
                int raw = bytes[p] | (bytes[p + 1] << 8) | (bytes[p + 2] << 16);
                if ((raw & 0x800000) != 0) raw |= unchecked((int)0xff000000);
                clipped = raw == -8388608 || raw == 8388607;
                value = raw / 8388608.0;
            } else {
                int raw = BitConverter.ToInt32(bytes, p);
                clipped = raw == Int32.MinValue || raw == Int32.MaxValue;
                value = raw / 2147483648.0;
            }
            if (Double.IsNaN(value) || Double.IsInfinity(value)) { result.NonFiniteSamples++; continue; }
            double absolute = Math.Abs(value);
            if (clipped || absolute >= 1.0) result.ClippedSamples++;
            if (absolute > 0) result.NonZeroSamples++;
            if (absolute > result.PeakAbsolute) result.PeakAbsolute = absolute;
            sumSquares += value * value;
        }
        result.Rms = Math.Sqrt(sumSquares / result.Samples);
        result.Passed = result.NonFiniteSamples == 0 && result.ClippedSamples == 0 &&
            result.NonZeroSamples > 0 && result.PeakAbsolute > 0.00001 && result.Rms > 0.000001;
        return result;
    }
}
