// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Cadence Studio contributors
#include "audio/common/cadencefxparams.h"
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
using namespace muse::audio::cadencefx;
int main() {
    unsigned checks=0;
    auto require=[&](bool ok){ if(!ok) throw std::runtime_error("Native-FX configuration contract failed"); ++checks; };
    try {
        for(auto kind:{Kind::Equalizer,Kind::Compressor}) {
            auto initial=defaults(kind);require(initial.supported);require(decode(kind,{}).values==initial.values);
            for(std::size_t i=0;i<6;++i) {
                for(double value:{parameters(kind)[i].minimum,parameters(kind)[i].maximum,parameters(kind)[i].initial}) {
                    auto settings=initial;settings.values[i]=value;auto encoded=encode(settings);auto roundtrip=decode(kind,encoded);
                    require(encoded.size()==7 && encoded.at(SCHEMA_KEY)=="1" && roundtrip.supported && roundtrip.values==settings.values);
                }
            }
            auto encoded=encode(initial);
            auto bad=encoded;bad[SCHEMA_KEY]="2";require(!decode(kind,bad).supported);require(bad.at(SCHEMA_KEY)=="2");
            bad=encoded;bad.erase(SCHEMA_KEY);require(!decode(kind,bad).supported);
            bad=encoded;bad["futureParameter"]="1";require(!decode(kind,bad).supported);
            for(const char* invalid:{"nan","inf","-inf","1,5","12 trailing","","1e9999"}) {
                bad=encoded;bad[parameters(kind)[0].key]=invalid;require(!decode(kind,bad).supported);
            }
            bad=encoded;bad[parameters(kind)[0].key]=std::string(65,'1');require(!decode(kind,bad).supported);
            bad=encoded;bad[parameters(kind)[0].key]="-100000";require(!decode(kind,bad).supported);
            auto modified=initial;modified.values[0]=std::numeric_limits<double>::infinity();require(decode(kind,encode(modified)).values[0]==parameters(kind)[0].initial);
        }
        require(!decode(Kind::None,{}).supported);require(encode(defaults(Kind::None)).empty());
        require(kindForId(EQUALIZER_ID)==Kind::Equalizer && kindForId(COMPRESSOR_ID)==Kind::Compressor && kindForId("Muse Reverb")==Kind::None);
        std::cout << checks << " actual versioned native-FX configuration checks passed\n";
        return 0;
    } catch(const std::exception& error) { std::cerr << error.what() << '\n';return 1; }
}
