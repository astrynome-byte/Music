// SPDX-License-Identifier: GPL-3.0-only
// Actual scene route with boundary-only context/remote/editor endpoints.
#include <QCoreApplication>
#include <array>
#include <cstddef>
#include <functional>
#include <tuple>
#include "notation/internal/notationmidiinput.h"
#include "engraving/dom/note.h"
#include <iostream>
#include <stdexcept>
#include "notationscene/internal/midiinputoutputcontroller.h"
#include "playback/ipracticemidicontroller.h"
#include "notation/inotation.h"

namespace mu::notation {
struct MidiPracticeRoutingProbe {
    static void send(MidiInputOutputController& route, const muse::midi::Event& e) { route.onMidiEventReceived(0,e); }
    static void bind(MidiInputOutputController& route, std::shared_ptr<context::IGlobalContext> context,
                     std::shared_ptr<muse::midiremote::IMidiRemote> remote,
                     std::shared_ptr<mu::playback::IPracticeMidiController> practice)
    {
        route.globalContext.set(context); route.midiRemote.set(remote);
#ifdef CADENCE_BUILD
        route.practiceMidiController.set(practice);
#else
        (void)practice;
#endif
    }
};
}
using namespace mu;
using muse::midi::Event;
static void check(bool b,const char* why){if(!b)throw std::runtime_error(why);}
struct Input final:notation::INotationMidiInput {
    int received=0;
    void onMidiEventReceived(const Event&) override {++received;}
    muse::async::Channel<std::vector<const notation::Note*>> notesReceived()const override{return {};}
    void onRealtimeAdvance()override{}
};
struct Notation final:notation::INotation {
    std::shared_ptr<Input> input=std::make_shared<Input>();
    notation::INotationMidiInputPtr actualInput;
    project::INotationProject* project()const override{return nullptr;}
    notation::IMasterNotationPtr masterNotation()const override{return {};}
    QString name()const override{return {};}
    QString projectName()const override{return {};}
    QString projectNameAndPartName()const override{return {};}
    QString workTitle()const override{return {};}
    QString projectWorkTitle()const override{return {};}
    QString projectWorkTitleAndPartName()const override{return {};}
    bool isOpen()const override{return true;}
    void setIsOpen(bool)override{}
    muse::async::Notification openChanged()const override{return {};}
    bool hasVisibleParts()const override{return true;}
    bool isMaster()const override{return true;}
    notation::ViewMode viewMode()const override{return notation::ViewMode::PAGE;}
    void setViewMode(const notation::ViewMode&)override{}
    muse::async::Notification viewModeChanged()const override{return {};}
    notation::INotationPaintingPtr painting()const override{return {};}
    notation::INotationViewStatePtr viewState()const override{return {};}
    notation::INotationSoloMuteStatePtr soloMuteState()const override{return {};}
    notation::INotationInteractionPtr interaction()const override{return {};}
    notation::INotationMidiInputPtr midiInput()const override{return actualInput ? actualInput : input;}
    notation::INotationUndoStackPtr undoStack()const override{return {};}
    notation::INotationStylePtr style()const override{return {};}
    notation::INotationElementsPtr elements()const override{return {};}
    notation::INotationAccessibilityPtr accessibility()const override{return {};}
    notation::INotationPartsPtr parts()const override{return {};}
    muse::async::Notification notationChanged()const override{return {};}
};
struct Context final:context::IGlobalContext {
    notation::INotationPtr current;
    void setCurrentProject(const project::INotationProjectPtr&)override{}
    project::INotationProjectPtr currentProject()const override{return {};}
    muse::async::Notification currentProjectChanged()const override{return {};}
    notation::IMasterNotationPtr currentMasterNotation()const override{return {};}
    muse::async::Notification currentMasterNotationChanged()const override{return {};}
    void setCurrentNotation(const notation::INotationPtr& n)override{current=n;}
    notation::INotationPtr currentNotation()const override{return current;}
    muse::async::Notification currentNotationChanged()const override{return {};}
    void setCurrentPlayer(const muse::audio::IPlayerPtr&)override{}
    context::IPlaybackStatePtr playbackState()const override{return {};}
};
struct Remote final:muse::midiremote::IMidiRemote {
    int received=0;bool handles=false;
    const muse::midiremote::MidiMappingList& midiMappings()const override{static const muse::midiremote::MidiMappingList x;return x;}
    muse::Ret setMidiMappings(const muse::midiremote::MidiMappingList&)override{return muse::Ret(muse::Ret::Code::Ok);}
    void resetMidiMappings()override{}
    muse::async::Notification midiMappingsChanged()const override{return {};}
    void setIsSettingMode(bool)override{}
    bool isSettingMode()const override{return false;}
    void setCurrentActionEvent(const Event&)override{}
    muse::Ret process(const Event&)override{++received;return handles?muse::Ret(muse::Ret::Code::Ok):muse::Ret(muse::Ret::Code::Undefined);}
};
struct Practice final:playback::IPracticeMidiController {
    bool capture=false;int received=0;
    std::function<bool()> prepare;
    bool startFromSelection()override{capture = prepare ? prepare() : true;return capture;}
    void finish()override{capture=false;}
    bool consumeMidiEvent(const Event&)override{++received;return capture;}
    QVariantMap state()const override{return {};}
    QVariantList history()const override{return {};}
    void refreshHistory()override{}
    bool clearHistory()override{return true;}
    bool retryHistory()override{return true;}
    void discardPendingHistory()override{}
    bool recordManualSession(const QVariantMap&)override{return true;}
    muse::async::Notification stateChanged()const override{return {};}
};

// The actual refusal path never reads a Score or dereferences a Note. These
// opaque markers prove that it returns before cleanup, queue or score access.
// The activation/context endpoints are explicit boundaries, not a full Score.
struct AbsentScore final: notation::IGetScore {
    mutable int queried = 0;
    engraving::Score* score() const override { ++queried; return nullptr; }
    muse::async::Notification scoreInited() const override { return {}; }
};
namespace mu::notation {
struct MidiPracticeResetProbe {
    struct State {
        std::vector<muse::midi::Event> queue;
        std::vector<std::tuple<int,bool,Note*>> notes;
        std::array<int,3> timerIds;
        bool metronomeOwner, holdingNotes, allowRests;
    };
    static void seed(NotationMidiInput& input, Note* scoreToken, Note* previewToken) {
        input.m_playingNotes[60] = { false, scoreToken };
        input.m_playingNotes[64] = { true, previewToken };
        input.onMidiEventReceived(Event::fromMidi10Package(0x643c90));
        input.m_realtimeTimer.start(60000);input.m_extendNoteTimer.start(60000);
        input.m_shouldDisableMetronome=true;input.m_holdingNotesInInputByDuration=true;
        input.m_allowRealtimeRests=false;
    }
    static State state(const NotationMidiInput& input) {
        State result;
        result.queue=input.m_eventsQueue;
        for(const auto& pair:input.m_playingNotes)result.notes.emplace_back(pair.first,pair.second.isPreview,pair.second.note);
        result.timerIds={input.m_processTimer.timerId(),input.m_realtimeTimer.timerId(),input.m_extendNoteTimer.timerId()};
        result.metronomeOwner=input.m_shouldDisableMetronome;
        result.holdingNotes=input.m_holdingNotesInInputByDuration;result.allowRests=input.m_allowRealtimeRests;
        return result;
    }
    static bool same(const State& a,const State& b) {
        return a.queue==b.queue && a.notes==b.notes && a.timerIds==b.timerIds
            && a.metronomeOwner==b.metronomeOwner && a.holdingNotes==b.holdingNotes && a.allowRests==b.allowRests;
    }
    static void releaseOpaqueMarkers(NotationMidiInput& input) { input.m_playingNotes.clear(); }
};
}
int main(int argc,char**argv)
{
    QCoreApplication app(argc,argv);
    try {
        AbsentScore absent;
        auto scope=std::make_shared<muse::modularity::Context>(23458);
        auto input=std::make_shared<notation::NotationMidiInput>(&absent,nullptr,nullptr,scope);
        alignas(engraving::Note) std::array<std::byte,sizeof(engraving::Note)*2> inert{};
        auto* scoreToken=reinterpret_cast<engraving::Note*>(inert.data());
        auto* previewToken=reinterpret_cast<engraving::Note*>(inert.data()+sizeof(engraving::Note));
        notation::MidiPracticeResetProbe::seed(*input,scoreToken,previewToken);
        const auto before=notation::MidiPracticeResetProbe::state(*input);
        check(before.queue.size()==1 && before.notes.size()==2,"Native test setup incomplete");
        check(!input->prepareForMidiPractice(),"A held score-owned input note did not refuse practice");
        check(absent.queried==0,"Refusal queried the score before protecting input ownership");
        check(notation::MidiPracticeResetProbe::same(before,notation::MidiPracticeResetProbe::state(*input)),
              "Refused preparation changed map, queue, timers or MIDI ownership");
        std::cout<<"PASS: real MIDI refusal preserves map queue timers and score boundary\n";
        auto context=std::make_shared<Context>();auto notation=std::make_shared<Notation>();
        notation->actualInput=input;context->current=notation;
        auto remote=std::make_shared<Remote>();auto practice=std::make_shared<Practice>();
        practice->prepare=[input](){return input->prepareForMidiPractice();};
        check(!practice->startFromSelection() && !practice->capture,"Refused activation kept MIDI capture armed");
        notation::MidiInputOutputController route(scope);
        notation::MidiPracticeRoutingProbe::bind(route,context,remote,practice);
        const auto on=Event::fromMidi10Package(0x644390).toMIDI20();
        notation::MidiPracticeRoutingProbe::send(route,on);
        auto after=notation::MidiPracticeResetProbe::state(*input);
        check(remote->received==1 && practice->received==1 && after.queue.size()==before.queue.size()+1,
              "Actual scene route did not return input to the real notation queue after refusal");
        check(after.notes==before.notes && after.timerIds==before.timerIds && absent.queried==0,
              "Ordinary queue delivery altered held notes or touched the score");
        remote->handles=true;
        notation::MidiPracticeRoutingProbe::send(route,on);
        check(remote->received==2 && notation::MidiPracticeResetProbe::state(*input).queue==after.queue,
              "Existing remote precedence changed after refused practice");
        std::cout<<"PASS: actual scene router restores ordinary input after preparation refusal\n";
        notation::MidiPracticeResetProbe::releaseOpaqueMarkers(*input);
    } catch(const std::exception& error) { std::cerr<<"FAIL: "<<error.what()<<'\n';return 1; }
    return 0;
}
