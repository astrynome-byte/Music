// SPDX-License-Identifier: GPL-3.0-only
// Native GUI checks only; no internal Cadence URI/action or QML test hook.
static const std::wstring omrTitle=L"Reconnaître une partition — PDF ou image";
static const std::wstring wavTitle=L"Transcrire une mélodie WAV locale";
static const std::wstring omrMenu=L"Reconnaître un PDF ou une image…";
static const std::wstring wavMenu=L"Transcrire un WAV monodique local…";
static const std::wstring omrChoose=L"Choisir le document…";
static const std::wstring wavChoose=L"Choisir un WAV…";
static const std::wstring wavSave=L"Enregistrer le MIDI et ouvrir…";
static unsigned importKeys=0, altTaps=0, homeTaps=0, nextRowTaps=0;
static HWND observedDialog=nullptr;
static std::vector<std::string> observations;
// Diagnostics only. These values never admit a key or relax a semantic match.
static std::string blockedGuard;
static bool readinessEntered=false,readinessPassed=false;
static unsigned readinessIterations=0;
static std::vector<std::string> readinessFrames;
static HRESULT automation2Result=E_UNEXPECTED,connectionTimeoutResult=E_UNEXPECTED,transactionTimeoutResult=E_UNEXPECTED;
static bool block(const char* reason) {if(blockedGuard.empty())blockedGuard=reason;return false;}
static bool nodeIs(const Node& node,const std::wstring& label,int role,bool enabled=true)
{
    return node.pid==static_cast<int>(targetPid) && node.type==role && !node.offscreen
        && (!enabled||node.enabled) && controlLabel(node.name)==label;
}
static bool observeFocus(IUIAutomation* a,const std::wstring& label,int role)
{
    const Node n=focusedNode(a);
    const bool yes=nodeIs(n,label,role);
    observations.push_back("{\"expected\":"+jsonQuoted(label)+",\"actual\":"+jsonQuoted(n.name)
        +",\"role\":"+std::to_string(n.type)+",\"pid\":"+std::to_string(n.pid)+",\"matched\":"+(yes?"true":"false")+'}');
    return yes;
}
static HWND exactDialog(const std::wstring& title)
{
    HWND match=nullptr;
    for(HWND w:windows()) {
        if(windowTitle(w)!=title||!IsWindowEnabled(w))continue;
        if(match||!cadence_owned_file_dialog_detail::ownedChain(w,mainWindow(),targetPid))return nullptr;
        match=w;
    }
    return match;
}
static bool context(HWND w)
{
    if(!alive()||Clock::now()>=deadline||!owned(w)||!IsWindowVisible(w)||!IsWindowEnabled(w))return false;
    return w==mainWindow() || cadence_owned_file_dialog_detail::ownedChain(w,mainWindow(),targetPid);
}
static bool importKey(IUIAutomation* a,const std::filesystem::path& out,HWND w,WORD key,const char* purpose)
{
    if(!context(w))return block("import_key_context_not_owned_visible_enabled_alive_before_deadline");
    if(importKeys>=70||keyboardFailure||(key==VK_MENU&&altTaps>=1)
        ||(key==VK_HOME&&homeTaps>=1)||(key==VK_NEXT&&nextRowTaps>=2))return block("import_key_budget_or_prior_keyboard_failure");
    const Node before=focusedNode(a);
    if(before.pid!=0&&before.pid!=static_cast<int>(targetPid)) {
        observations.push_back("{\"diagnostic_only\":true,\"blocked_before_any_input\":true,\"foreign_focus_pid\":"+std::to_string(before.pid)+",\"name\":"+jsonQuoted(before.name)+",\"role\":"+std::to_string(before.type)+'}');
        return block("import_key_foreign_focused_element_pid");
    }
    const std::wstring frame=std::to_wstring(importKeys+1);
    snapshot(a,out,(frame+L"-before-import-key").c_str());
    if(key==VK_MENU)++altTaps;
    if(key==VK_HOME)++homeTaps;
    if(key==VK_NEXT)++nextRowTaps;
    ++importKeys;
    const OwnedKeyResult result=SendOwnedKey(targetPid,targetProcess,w,key);
    if(!result.sent)keyboardFailure=true;
    actions.push_back(std::string("{\"action\":\"import_owned_key\",\"purpose\":\"")+purpose+"\",\"key\":"+std::to_string(key)
        +",\"pid\":"+std::to_string(targetPid)+",\"foreground\":"+std::to_string(reinterpret_cast<std::uintptr_t>(result.foreground))
        +",\"focus\":"+std::to_string(reinterpret_cast<std::uintptr_t>(result.focus))+",\"input_count\":"+std::to_string(result.inputCount)
        +",\"observed_name_before\":"+jsonQuoted(before.name)+",\"observed_role_before\":"+std::to_string(before.type)
        +",\"sent\":"+(result.sent?"true":"false")+",\"error\":"+std::to_string(result.error)+'}');
    Sleep(150);snapshot(a,out,(frame+L"-after-import-key").c_str());return result.sent;
}
static bool focusExact(IUIAutomation* a,const std::filesystem::path& out,HWND w,const std::wstring& label,int role)
{
    if(!context(w))return false;
    if(observeFocus(a,label,role))return true;
    auto nodes=snapshot(a,out,L"focus-import-control");const Node* chosen=nullptr;
    for(const Node& n:nodes)if(nodeIs(n,label,role)) {if(chosen)return false;chosen=&n;}
    if(!chosen)return false;
    const HRESULT hr=chosen->element->SetFocus();Sleep(100);
    ComPtr<IUIAutomationElement> current;BOOL same=FALSE;
    const bool equal=SUCCEEDED(a->GetFocusedElement(&current))&&current
        && SUCCEEDED(a->CompareElements(current.Get(),chosen->element.Get(),&same))&&same;
    return SUCCEEDED(hr)&&equal&&observeFocus(a,label,role);
}
static bool waitFocus(IUIAutomation* a,const std::filesystem::path& out,HWND w,const std::wstring& label,int role,unsigned seconds=5)
{
    const auto until=std::min(deadline,Clock::now()+std::chrono::seconds(seconds));
    while(context(w)&&Clock::now()<until){if(focusExact(a,out,w,label,role))return true;Sleep(120);}return false;
}
static bool pressExact(IUIAutomation* a,const std::filesystem::path& out,HWND w,const std::wstring& label,int role,const char* purpose)
{
    return focusExact(a,out,w,label,role)&&observeFocus(a,label,role)&&importKey(a,out,w,VK_RETURN,purpose);
}
static const Node* findReadyMainHome(const std::vector<Node>& nodes)
{
    const Node* found=nullptr;
    for(const Node& n:nodes) {
        // Source AccessibleItemInterface prepends its active panel's name.
        // The full French value below was observed, with this exact role, in
        // GUI2 original main-ready.json (SHA256 61353357...); no suffix match
        // or generic prefix removal is admitted for readiness.
        if(n.pid!=static_cast<int>(targetPid)||n.type!=UIA_RadioButtonControlTypeId||!n.enabled||n.offscreen)continue;
        if(n.name!=L"Accueil"&&n.name!=L"Home"
            &&n.name!=L"Panneau Barre d'outils principale la direction est horizontale, Accueil")continue;
        if(found)return nullptr;
        found=&n;
    }
    return found;
}
static bool readyMain(IUIAutomation* a,const std::filesystem::path& out)
{
    readinessEntered=true;
    while(alive()&&Clock::now()<deadline) {
        if(closeIntroductionOnly())Sleep(200);
        const auto nodes=snapshot(a,out,L"main-ready");
        const HWND main=mainWindow();const bool validContext=context(main);
        const Node* home=findReadyMainHome(nodes);const Node* scores=find(nodes,{L"Partitions",L"Scores"});
        ++readinessIterations;
        unsigned targetNodes=0,rawHome=0,rawScores=0,normalizedHome=0,normalizedScores=0,exactObservedToolbarHome=0;
        for(const Node& n:nodes) {
            if(n.pid!=static_cast<int>(targetPid))continue;
            ++targetNodes;
            if(!n.enabled||n.offscreen||!interactiveType(n.type))continue;
            if(n.name==L"Accueil"||n.name==L"Home")++rawHome;
            if(n.name==L"Partitions"||n.name==L"Scores")++rawScores;
            if(n.type==UIA_RadioButtonControlTypeId&&n.name==L"Panneau Barre d'outils principale la direction est horizontale, Accueil")++exactObservedToolbarHome;
            const auto label=controlLabel(n.name);
            if(label==L"Accueil"||label==L"Home")++normalizedHome;
            if(label==L"Partitions"||label==L"Scores")++normalizedScores;
        }
        const std::string frame="{\"iteration\":"+std::to_string(readinessIterations)+",\"alive\":"+(alive()?"true":"false")
            +",\"deadline_reached\":"+(Clock::now()>=deadline?"true":"false")+",\"main_handle\":"+std::to_string(reinterpret_cast<std::uintptr_t>(main))
            +",\"main_title\":"+jsonQuoted(windowTitle(main))+",\"main_owned\":"+(owned(main)?"true":"false")
            +",\"main_visible\":"+(main&&IsWindowVisible(main)?"true":"false")+",\"main_enabled\":"+(main&&IsWindowEnabled(main)?"true":"false")
            +",\"main_context_passed\":"+(validContext?"true":"false")+",\"foreground_handle\":"+std::to_string(reinterpret_cast<std::uintptr_t>(GetForegroundWindow()))
            +",\"node_count\":"+std::to_string(nodes.size())+",\"target_pid_node_count\":"+std::to_string(targetNodes)
            +",\"raw_home_candidates\":"+std::to_string(rawHome)+",\"raw_scores_candidates\":"+std::to_string(rawScores)
            +",\"normalized_home_candidates_diagnostic_only\":"+std::to_string(normalizedHome)+",\"normalized_scores_candidates_diagnostic_only\":"+std::to_string(normalizedScores)
            +",\"exact_observed_toolbar_home_candidates\":"+std::to_string(exactObservedToolbarHome)
            +",\"unique_role50013_home\":"+(home?"true":"false")+",\"unique_raw_scores\":"+(scores?"true":"false")+'}';
        if(readinessFrames.size()<8)readinessFrames.push_back(frame);else readinessFrames.back()=frame;
        if(validContext&&(home||scores)){readinessPassed=true;return true;}
        Sleep(200);
    }
    return block(alive()?"main_readiness_deadline_without_unique_raw_Home_or_Scores_and_valid_context":"main_readiness_process_exited");
}
static bool openThroughFile(IUIAutomation* a,const std::filesystem::path& out,bool wave)
{
    if(!readyMain(a,out))return false;
    const HWND main=mainWindow();
    // Source NavigableAppMenuModel activates the first menu on Alt release.
    // This is one matched key pair, never a chord, click or direct app action.
    if(!importKey(a,out,main,VK_MENU,"expose_source_defined_application_menu"))return false;
    bool file=waitFocus(a,out,main,L"Fichier",UIA_ButtonControlTypeId,3);
    if(!file)file=waitFocus(a,out,main,L"File",UIA_ButtonControlTypeId,1);
    if(!file)return false;
    if(!importKey(a,out,main,VK_RETURN,"open_observed_file_menu"))return false;
    const std::wstring target=wave?wavMenu:omrMenu;
    bool requested=false;
    for(unsigned step=0;step<24&&context(main);++step) {
        if(focusExact(a,out,main,target,UIA_MenuItemControlTypeId)) {
            requested=pressExact(a,out,main,target,UIA_MenuItemControlTypeId,"activate_exact_import_file_menu_item");break;
        }
        const Node n=focusedNode(a);
        if(n.pid!=static_cast<int>(targetPid)||n.type!=UIA_MenuItemControlTypeId||!n.enabled||n.offscreen)return false;
        if(!importKey(a,out,main,VK_DOWN,"inspect_file_menu_items_without_activating_other_actions"))return false;
    }
    if(!requested)return false;
    const auto until=std::min(deadline,Clock::now()+std::chrono::seconds(8));
    while(alive()&&Clock::now()<until) {
        observedDialog=exactDialog(wave?wavTitle:omrTitle);
        if(observedDialog&&waitFocus(a,out,observedDialog,wave?wavChoose:omrChoose,UIA_ButtonControlTypeId,2)) {
            snapshot(a,out,wave?L"wav-loaded":L"omr-loaded");return true;
        }
        Sleep(150);
    }
    return false;
}
static bool cancelChooser(IUIAutomation* a,const std::filesystem::path& out,HWND dialog,const std::wstring& choose)
{
    if(!pressExact(a,out,dialog,choose,UIA_ButtonControlTypeId,"open_owned_import_source_chooser"))return false;
    HWND picker=nullptr;const ULONGLONG end=GetTickCount64()+8000;
    while(alive()&&GetTickCount64()<end) {
        cadence_owned_file_dialog_detail::DialogSearch search{dialog,targetPid,end};
        EnumWindows(cadence_owned_file_dialog_detail::inspectDialog,reinterpret_cast<LPARAM>(&search));
        if(search.count>1)return false;
        if(search.count==1){picker=search.match;break;}Sleep(100);
    }
    if(!picker||!cadence_owned_file_dialog_detail::isDialog(picker,dialog,targetPid))return false;
    snapshot(a,out,L"native-chooser-before-cancel");
    if(!importKey(a,out,picker,VK_ESCAPE,"cancel_exact_owned_native_chooser_without_selecting_file"))return false;
    const auto until=std::min(deadline,Clock::now()+std::chrono::seconds(5));
    while(alive()&&Clock::now()<until) {
        if((!IsWindow(picker)||!IsWindowVisible(picker))&&context(dialog))
            return waitFocus(a,out,dialog,choose,UIA_ButtonControlTypeId,2);
        Sleep(100);
    }
    return false;
}
static bool focusWaveAcknowledgementFromSource(IUIAutomation* a,const std::filesystem::path& out,HWND dialog)
{
    // The sourcea2b7 URL field is empty. Observe its real public edit control,
    // then use the Up/Down navigation that TextInputField does not override.
    if(!observeFocus(a,wavChoose,UIA_ButtonControlTypeId)
        ||!importKey(a,out,dialog,VK_DOWN,"observe_empty_direct_WAV_URL_without_saisie_or_network")
        ||!waitFocus(a,out,dialog,L"Lien du WAV autorisé ou de sa page source",UIA_EditControlTypeId,2))return false;
    return importKey(a,out,dialog,VK_DOWN,"observe_unchecked_WAV_approximation_after_empty_URL")
        &&waitFocus(a,out,dialog,L"J'accepte une conversion approximative à corriger ; mon WAV reste inchangé.",UIA_CheckBoxControlTypeId,2);
}
static bool focusWaveCloseFromAcknowledgement(IUIAutomation* a,const std::filesystem::path& out,HWND dialog)
{
    if(focusExact(a,out,dialog,L"Fermer",UIA_ButtonControlTypeId)
        ||focusExact(a,out,dialog,L"Close",UIA_ButtonControlTypeId))return true;
    // Acknowledgement is (6,-1); Close is (8,0). PageDown is the real
    // nav-nextrow-control shortcut, which sets column=0 before selecting.
    // End is not deterministic because Last compares row and column jointly.
    const std::wstring ack=L"J'accepte une conversion approximative à corriger ; mon WAV reste inchangé.";
    if(!observeFocus(a,ack,UIA_CheckBoxControlTypeId)
        ||!importKey(a,out,dialog,VK_NEXT,"move_from_observed_ack_to_footer_close_with_next_row_navigation"))return false;
    const Node n=focusedNode(a);return nodeIs(n,L"Fermer",UIA_ButtonControlTypeId)||nodeIs(n,L"Close",UIA_ButtonControlTypeId);
}
static bool closeDialog(IUIAutomation* a,const std::filesystem::path& out,bool wave,bool cancelFile)
{
    const std::wstring title=wave?wavTitle:omrTitle;const HWND dialog=exactDialog(title);
    if(!dialog||!waitFocus(a,out,dialog,wave?wavChoose:omrChoose,UIA_ButtonControlTypeId))return false;
    if(cancelFile&&!cancelChooser(a,out,dialog,wave?wavChoose:omrChoose))return false;
    // Observe real source-defined setup controls without invoking installers,
    // changing settings, or acknowledging a conversion in this smoke phase.
    if(wave) {
        // Choose is (0,-1), parameters use column=0. PageDown crosses that
        // column boundary using the normal source-defined navigation action.
        if(!importKey(a,out,dialog,VK_NEXT,"observe_WAV_tempo_with_next_row_navigation")
            ||!waitFocus(a,out,dialog,L"Tempo saisi, en noires par minute",UIA_SpinnerControlTypeId,2)
            ||!importKey(a,out,dialog,VK_ESCAPE,"leave_tempo_value_unchanged")
            ||!importKey(a,out,dialog,VK_DOWN,"observe_WAV_quantization_property")
            ||!waitFocus(a,out,dialog,L"Grille de quantification imposée",UIA_ComboBoxControlTypeId,2)
            ||!importKey(a,out,dialog,VK_DOWN,"observe_WAV_noise_property")
            ||!waitFocus(a,out,dialog,L"Seuil de bruit en dBFS",UIA_SpinnerControlTypeId,2)
            ||!importKey(a,out,dialog,VK_ESCAPE,"leave_noise_value_unchanged")
            // Home selects the unique minimum (0,-1). Down then reaches
            // empty URL (1,-1), then acknowledgement (6,-1); noise is (5,0).
            ||!importKey(a,out,dialog,VK_HOME,"return_to_unique_first_WAV_source_control")
            ||!waitFocus(a,out,dialog,wavChoose,UIA_ButtonControlTypeId,2)
            ||!focusWaveAcknowledgementFromSource(a,out,dialog))return false;
    } else {
        if(!importKey(a,out,dialog,VK_DOWN,"observe_local_Audiveris_configuration_control")
            ||!waitFocus(a,out,dialog,L"Choisir Audiveris…",UIA_ButtonControlTypeId,2)
            ||!importKey(a,out,dialog,VK_DOWN,"observe_OCR_download_control_without_invoking_it")
            ||!waitFocus(a,out,dialog,L"Télécharger les données OCR…",UIA_ButtonControlTypeId,2)
            ||!importKey(a,out,dialog,VK_RIGHT,"observe_verified_OCR_import_control_without_invoking_it")
            ||!waitFocus(a,out,dialog,L"Importer eng.traineddata…",UIA_ButtonControlTypeId,2))return false;
    }
    if(wave) { if(!focusWaveCloseFromAcknowledgement(a,out,dialog))return false; }
    else if(!importKey(a,out,dialog,VK_END,"focus_dominating_last_OMR_close_control"))return false;
    const Node close=focusedNode(a);const std::wstring label=controlLabel(close.name);
    if(close.pid!=static_cast<int>(targetPid)||close.type!=UIA_ButtonControlTypeId||!close.enabled||close.offscreen
        || (label!=L"Fermer"&&label!=L"Close"))return false;
    if(!pressExact(a,out,dialog,label,UIA_ButtonControlTypeId,"close_observed_import_dialog"))return false;
    const auto until=std::min(deadline,Clock::now()+std::chrono::seconds(5));
    while(alive()&&Clock::now()<until){if(!exactDialog(title)&&context(mainWindow()))return true;Sleep(100);}return false;
}
static bool analyzeWave(IUIAutomation* a,const std::filesystem::path& out,const std::wstring& root,const std::wstring& wave)
{
    const HWND dialog=exactDialog(wavTitle);if(!dialog||!pressExact(a,out,dialog,wavChoose,UIA_ButtonControlTypeId,"choose_only_original_CC0_WAV_copy"))return false;
    const auto selected=SelectOwnedWaveFile(a,targetPid,targetProcess,dialog,root,wave,
        [&](const wchar_t* phase){snapshot(a,out,phase);});
    actions.push_back("{\"action\":\"select_only_controlled_WAV_copy\",\"selected\":"+std::string(selected.selected?"true":"false")
        +",\"path\":"+jsonQuoted(wave)+",\"diagnostic\":"+jsonQuoted(selected.diagnostic)+'}');
    if(!selected.selected||!waitFocus(a,out,dialog,wavChoose,UIA_ButtonControlTypeId))return false;
    const std::wstring tempo=L"Tempo saisi, en noires par minute",grid=L"Grille de quantification imposée",noise=L"Seuil de bruit en dBFS";
    auto move=[&](const std::wstring& label,int role){return importKey(a,out,dialog,VK_DOWN,"observe_source_defined_WAV_setting_without_edit")&&waitFocus(a,out,dialog,label,role,2);};
    if(!importKey(a,out,dialog,VK_NEXT,"observe_WAV_tempo_with_next_row_navigation")
        ||!waitFocus(a,out,dialog,tempo,UIA_SpinnerControlTypeId,2)
        ||!importKey(a,out,dialog,VK_ESCAPE,"finish_tempo_editor_without_change")
        ||!move(grid,UIA_ComboBoxControlTypeId)||!move(noise,UIA_SpinnerControlTypeId)
        ||!importKey(a,out,dialog,VK_ESCAPE,"finish_noise_editor_without_change")
        ||!importKey(a,out,dialog,VK_HOME,"return_to_unique_first_WAV_source_control")
        ||!waitFocus(a,out,dialog,wavChoose,UIA_ButtonControlTypeId,2))return false;
    const std::wstring ack=L"J'accepte une conversion approximative à corriger ; mon WAV reste inchangé.";
    if(!focusWaveAcknowledgementFromSource(a,out,dialog)||!pressExact(a,out,dialog,ack,UIA_CheckBoxControlTypeId,"acknowledge_approximate_conversion_for_CC0_fixture_only"))return false;
    // Use the actual row8/columns0->1 route, rather than Last/End ordering.
    if(!focusWaveCloseFromAcknowledgement(a,out,dialog)
        ||!importKey(a,out,dialog,VK_RIGHT,"focus_enabled_WAV_analysis_from_observed_close")
        ||!pressExact(a,out,dialog,L"Analyser",UIA_ButtonControlTypeId,"start_actual_local_monophonic_analysis"))return false;
    if(!waitFocus(a,out,dialog,wavSave,UIA_ButtonControlTypeId,25))return false;
    snapshot(a,out,L"wav-real-draft-ready");
    // Leave the ready draft visible for a launcher capture. A later close phase
    // discards it; no MIDI Save dialog, score edit or audio playback is invoked.
    observedDialog=dialog;return true;
}
static bool closeReadyWave(IUIAutomation* a,const std::filesystem::path& out)
{
    const HWND dialog=exactDialog(wavTitle);
    if(!dialog||!waitFocus(a,out,dialog,wavSave,UIA_ButtonControlTypeId))return false;
    if(!importKey(a,out,dialog,VK_LEFT,"move_from_MIDI_save_without_invoking_it")
        ||!waitFocus(a,out,dialog,L"Analyser",UIA_ButtonControlTypeId,2)
        ||!importKey(a,out,dialog,VK_LEFT,"focus_close_to_discard_only_test_draft"))return false;
    const Node n=focusedNode(a);const auto label=controlLabel(n.name);
    if(label!=L"Fermer"&&label!=L"Close")return false;
    if(!pressExact(a,out,dialog,label,UIA_ButtonControlTypeId,"discard_only_unsaved_test_draft_and_close"))return false;
    Sleep(200);return !exactDialog(wavTitle)&&context(mainWindow());
}
int wmain(int argc,wchar_t** argv)
{
    if((argc-1)%2)return 1;
    std::filesystem::path output;std::wstring phase,waveRoot,wave;
    for(int i=1;i+1<argc;i+=2) {
        const std::wstring key=argv[i];
        if(key==L"--pid")targetPid=wcstoul(argv[i+1],nullptr,10);
        else if(key==L"--output")output=argv[i+1];
        else if(key==L"--phase")phase=argv[i+1];
        else if(key==L"--fixture-root")waveRoot=argv[i+1];
        else if(key==L"--fixture-wav")wave=argv[i+1];else return 1;
    }
    const std::vector<std::wstring> phases{L"open-omr",L"close-omr",L"open-wav",L"close-wav",L"analyze-wav",L"close-ready-wav"};
    if(!targetPid||output.empty()||!std::filesystem::is_directory(output)||std::find(phases.begin(),phases.end(),phase)==phases.end())return 1;
    if(phase==L"analyze-wav"&&(waveRoot.empty()||wave.empty()))return 1;
    targetProcess=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION|SYNCHRONIZE,FALSE,targetPid);if(!alive())return 1;
    deadline=Clock::now()+std::chrono::seconds(60);bool passed=false;
    HRESULT initialized=CoInitializeEx(nullptr,COINIT_MULTITHREADED),activated=initialized;
    if(SUCCEEDED(initialized)) {
        ComPtr<IUIAutomation> a;activated=CoCreateInstance(__uuidof(CUIAutomation8),nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&a));
        if(FAILED(activated))activated=CoCreateInstance(__uuidof(CUIAutomation),nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&a));
        ComPtr<IUIAutomation2> bounded;
        if(SUCCEEDED(activated))automation2Result=a.As(&bounded);
        if(SUCCEEDED(automation2Result))connectionTimeoutResult=bounded->put_ConnectionTimeout(800);
        if(SUCCEEDED(connectionTimeoutResult))transactionTimeoutResult=bounded->put_TransactionTimeout(1000);
        if(SUCCEEDED(activated)&&SUCCEEDED(automation2Result)&&SUCCEEDED(connectionTimeoutResult)&&SUCCEEDED(transactionTimeoutResult)) {
            if(phase==L"open-omr"||phase==L"open-wav")passed=openThroughFile(a.Get(),output,phase==L"open-wav");
            else if(phase==L"close-omr"||phase==L"close-wav")passed=closeDialog(a.Get(),output,phase==L"close-wav",true);
            else if(phase==L"analyze-wav")passed=analyzeWave(a.Get(),output,waveRoot,wave);
            else if(phase==L"close-ready-wav")passed=closeReadyWave(a.Get(),output);
            snapshot(a.Get(),output,L"phase-final");
        }
        a.Reset();bounded.Reset();CoUninitialize();
    }
    if(!passed&&blockedGuard.empty()) {
        if(FAILED(initialized))blockedGuard="COM_initialization";
        else if(FAILED(activated))blockedGuard="UIAutomation_creation";
        else if(FAILED(automation2Result))blockedGuard="UIAutomation2_query";
        else if(FAILED(connectionTimeoutResult))blockedGuard="UIAutomation_connection_timeout_setup";
        else if(FAILED(transactionTimeoutResult))blockedGuard="UIAutomation_transaction_timeout_setup";
        else blockedGuard="later_semantic_phase_guard";
    }
    RECT rect{};if(owned(observedDialog))GetWindowRect(observedDialog,&rect);
    std::ofstream result(output/L"import-dialog-phase.json",std::ios::binary);
    result<<"{\"schema_version\":1,\"phase\":"<<jsonQuoted(phase)<<",\"pid\":"<<targetPid
        <<",\"status\":\""<<(passed&&!keyboardFailure?"passed_owned_import_dialog_phase":"blocked_or_failed_import_dialog_phase")
        <<"\",\"dialog_handle\":"<<reinterpret_cast<std::uintptr_t>(observedDialog)<<",\"dialog_title\":"<<jsonQuoted(owned(observedDialog)?windowTitle(observedDialog):L"")
        <<",\"rect\":["<<rect.left<<','<<rect.top<<','<<rect.right<<','<<rect.bottom<<"],\"com_hresult\":"<<static_cast<long>(activated)
        <<",\"keys\":"<<importKeys<<",\"alt_taps\":"<<altTaps<<",\"home_taps\":"<<homeTaps<<",\"next_row_taps\":"<<nextRowTaps
        <<",\"keyboard_failure\":"<<(keyboardFailure?"true":"false")
        <<",\"diagnostics_only\":{\"blocked_guard\":"<<jsonQuoted(std::wstring(blockedGuard.begin(),blockedGuard.end()))
        <<",\"COM_initialization_hresult\":"<<static_cast<long>(initialized)<<",\"automation2_query_hresult\":"<<static_cast<long>(automation2Result)
        <<",\"connection_timeout_hresult\":"<<static_cast<long>(connectionTimeoutResult)<<",\"transaction_timeout_hresult\":"<<static_cast<long>(transactionTimeoutResult)
        <<",\"readiness_entered\":"<<(readinessEntered?"true":"false")<<",\"readiness_passed\":"<<(readinessPassed?"true":"false")<<",\"readiness_iterations\":"<<readinessIterations
        <<",\"readiness_frames_bounded_to8\":[";
    for(size_t i=0;i<readinessFrames.size();++i){if(i)result<<',';result<<readinessFrames[i];}result<<"]}"
        <<",\"observations\":[";
    for(size_t i=0;i<observations.size();++i){if(i)result<<',';result<<observations[i];}result<<"],\"actions\":[";
    for(size_t i=0;i<actions.size();++i){if(i)result<<',';result<<actions[i];}
    result<<"],\"real_Audiveris_executed\":false,\"MIDI_saved_or_opened\":false,\"score_editing\":false,\"listening\":false}";
    CloseHandle(targetProcess);return passed&&!keyboardFailure?0:2;
}
