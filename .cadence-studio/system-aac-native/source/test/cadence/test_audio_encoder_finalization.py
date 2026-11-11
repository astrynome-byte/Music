# SPDX-License-Identifier: GPL-3.0-only
"""Exercise the production encoder finalization contract without a Qt engine.

Only unrelated Progress/path/format data are lightweight stubs. The actual
AbstractAudioEncoder header, Ret implementation and virtual dispatch are used.
This does not exercise Media Foundation, file I/O or SoundTrackWriter at runtime.
"""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
HARNESS = r'''
#include "audio/engine/internal/export/abstractaudioencoder.h"
#include <string>
using namespace muse;
using namespace muse::audio;
using namespace muse::audio::encode;

class Encoder : public AbstractAudioEncoder {
public:
    int drains = 0;
    size_t encode(samples_t, const float*) override { return 2; }
    size_t flush() override { ++drains; return 0; }
protected:
    size_t requiredOutputBufferSize(samples_t) const override { return 0; }
};

class DelayedFailure : public Encoder {
public:
    size_t flush() override {
        Encoder::flush();
        error = make_ret(Ret::Code::UnknownError, std::string("AAC drain/file close failed"));
        return 0;
    }
    Ret lastError() const override { return error; }
private:
    Ret error = make_ok();
};

int main(int argc, char** argv) {
    if (argc != 2) { return 2; }
    const bool failure = std::string(argv[1]) == "delayed-failure";
    std::unique_ptr<Encoder> encoder = failure ? std::make_unique<DelayedFailure>() : std::make_unique<Encoder>();
    float samples[] = { .1f, -.1f };
    if (encoder->encode(1, samples) != 2) { return 3; }
    const Ret finished = encoder->finish();
    if (encoder->drains != 1) { return 4; }
    if (failure) {
        return !finished && finished.text() == "AAC drain/file close failed" ? 0 : 5;
    }
    return finished ? 0 : 6;
}
'''


class EncoderFinalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CXX", shutil.which("g++") or "g++"))
        cls.work = tempfile.TemporaryDirectory(prefix="cadence encoder finalization ")
        cls.addClassCleanup(cls.work.cleanup)
        folder = Path(cls.work.name)
        stubs = {
            "global/progress.h": '#include "global/types/ret.h"\nnamespace muse { class Progress {}; }\n',
            "global/io/path.h": 'namespace muse::io { struct path_t { const char* c_str() const { return ""; } }; }\n',
            "audio/common/audiotypes.h": '#include <cstdint>\nnamespace muse::audio { using samples_t=uint64_t; struct SoundTrackFormat { bool isValid() const { return true; } }; }\n',
        }
        for name, text in stubs.items():
            path = folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        source = folder / "contract.cpp"
        source.write_text(HARNESS)
        cls.executable = folder / "contract"
        run = subprocess.run(
            [*compiler, "-std=c++17", "-DNO_QT_SUPPORT", "-include", "memory",
             "-I", str(folder), "-I", str(ROOT / "src/framework"),
             "-I", str(ROOT / "src/framework/global"), str(source),
             str(ROOT / "src/framework/global/types/ret.cpp"), "-o", str(cls.executable)],
            capture_output=True, text=True, timeout=60)
        if run.returncode:
            raise AssertionError(run.stdout + run.stderr)

    def test_empty_drain_can_succeed(self):
        subprocess.run([str(self.executable), "already-drained"], check=True, timeout=10)

    def test_delayed_failure_after_consumed_samples_is_not_success(self):
        subprocess.run([str(self.executable), "delayed-failure"], check=True, timeout=10)
