#include "stdafx.h"
#include <study/windows/CandidateUi.h>
#include <study/windows/EnglishMenu.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <cmath>

CAppModule _Module;
struct Checks {
  std::filesystem::path path;
  std::vector<std::pair<std::string, bool>> items;
  void Check(const std::string& name, bool pass) {
    items.emplace_back(name, pass);
    std::ofstream output(path);
    output << "{\"checks\":[";
    for (size_t i = 0; i < items.size(); ++i) {
      if (i) output << ',';
      output << "{\"name\":\"" << items[i].first << "\",\"passed\":" << (items[i].second ? "true" : "false") << '}';
    }
    output << "]}\n";
    std::cout << (pass ? "PASS " : "FAIL ") << name << std::endl;
    if (!pass) throw std::runtime_error(name);
  }
};
static void Frame(const std::filesystem::path& directory, const std::string& name, const study::CandidateFrame& frame) {
  if (frame.bgra.empty()) throw std::runtime_error("Empty native render");
  std::ofstream data(directory / (name + ".bgra"), std::ios::binary);
  data.write(reinterpret_cast<const char*>(frame.bgra.data()), static_cast<std::streamsize>(frame.bgra.size()));
  std::ofstream meta(directory / (name + ".json"));
  meta << "{\"width\":" << frame.width << ",\"height\":" << frame.height << ",\"source\":\"production offscreen DirectWrite renderer\"}\n";
}
static weasel::Context Context() {
  weasel::Context context;
  context.preedit.str = L"ni hao";
  const wchar_t* chinese[] = {L"你好", L"你们", L"苹果", L"学习", L"工作"};
  const wchar_t* english[] = {L"hello", L"you (plural)", L"apple", L"learn; study", L"work"};
  for (unsigned i = 0; i < 5; ++i) {
    context.cinfo.candies.emplace_back(chinese[i]);
    context.cinfo.comments.emplace_back(english[i]);
    context.cinfo.labels.emplace_back(std::to_wstring(i + 1));
  }
  context.cinfo.highlighted = 0;
  context.cinfo.currentPage = 0;
  context.cinfo.is_last_page = false;
  return context;
}
int wmain(int argc, wchar_t** argv) {
  if (argc != 4) return 2;
  CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
  _Module.Init(nullptr, GetModuleHandleW(nullptr));
  Checks checks{argv[1]};
  const std::filesystem::path frames = argv[2], settings = argv[3];
  std::filesystem::create_directories(frames);
  SetEnvironmentVariableW(L"STUDY_SETTINGS_PATH", settings.c_str());
  try {
    using namespace study;
    UiPreferences preferences;
    checks.Check("missing settings use documented defaults", LoadPreferences(settings / L"absent") == preferences);
    preferences.theme = Theme::Dark; preferences.largeText = true; preferences.learning = false;
    preferences.shortcut = EnglishShortcut::AltEnter; preferences.reduceMotion = true;
    checks.Check("settings atomically round-trip all five preferences", SavePreferences(settings, preferences) && LoadPreferences(settings) == preferences);
    std::ifstream file(settings); std::string contents((std::istreambuf_iterator<char>(file)), {}); file.close();
    checks.Check("preferences contain no candidate or input fields", contents.find("input") == std::string::npos && contents.find("candidate") == std::string::npos && contents.size() < 160);
    { std::ofstream out(settings); out << "version=1\nlearning=0\nlearning=1\n"; }
    checks.Check("duplicate preference keys fail to defaults", LoadPreferences(settings) == UiPreferences{});
    { std::ofstream out(settings); out << std::string(3000, 'x'); }
    checks.Check("oversized settings are bounded and rejected", LoadPreferences(settings) == UiPreferences{});
    preferences = {}; preferences.theme = Theme::Light;
    checks.Check("light settings saved for rendering", SavePreferences(settings, preferences));
    {
      CandidateUi memory;
      const DWORD attributes = GetFileAttributesW(settings.c_str());
      SetFileAttributesW(settings.c_str(), attributes | FILE_ATTRIBUTE_READONLY);
      const bool saved = memory.SaveLearning(false);
      const bool reloaded = memory.ReloadPreferences();
      SetFileAttributesW(settings.c_str(), attributes);
      checks.Check("failed preference write retains the current in-memory learning choice", !saved && !reloaded && !memory.Preferences().learning && LoadPreferences(settings).learning);
    }
    {
      SetEnvironmentVariableW(L"STUDY_SETTINGS_PATH", nullptr);
      CandidateUi memory; memory.SaveLearning(false);
      const bool reloaded = memory.ReloadPreferences();
      SetEnvironmentVariableW(L"STUDY_SETTINGS_PATH", settings.c_str());
      checks.Check("isolated host without a settings path retains memory-only preferences", !reloaded && !memory.Preferences().learning);
    }

    StudyMotion motion;
    motion.Reset(true); motion.Page(1, 1000, false);
    auto initial = motion.At(1000), halfway = motion.At(1090), end = motion.At(1180);
    checks.Check("next page enters from right and fades in for 180 ms", initial.incomingX > 9.99 && initial.incomingAlpha < .001 && halfway.incomingX > 0 && halfway.incomingX < 10 && end.incomingX == 0 && end.incomingAlpha == 1);
    checks.Check("outgoing page exits left and is gone at 120 ms", halfway.outgoingX < 0 && motion.At(1120).outgoingAlpha < .001);
    motion.Page(-1, 1100, false);
    checks.Check("rapid reverse paging replaces rather than queues motion", motion.At(1100).incomingX < -9.99 && !motion.At(1280).active);
    motion.SetLearning(false, 1200, false);
    const auto collapsing = motion.At(1260);
    checks.Check("learning collapse interpolates height for 240 ms", collapsing.learning > 0 && collapsing.learning < 1 && motion.At(1439).active && !motion.At(1440).active);
    checks.Check("English fades out within 160 ms", motion.At(1360).englishAlpha < .001);
    motion.SetLearning(true, 1260, false);
    checks.Check("rapid learning reversal starts at current height", std::abs(motion.At(1260).learning - collapsing.learning) < .0001 && motion.At(1500).learning > .999);
    motion.Page(1, 1300, true); motion.SetLearning(false, 1300, true);
    checks.Check("reduced motion applies both state changes immediately", !motion.At(1300).active && motion.At(1300).learning == 0 && motion.At(1300).incomingX == 0);

    weasel::Status status; status.composing = true;
    ActionState state; state.learning = true; state.stamp = {19, {23, 1}};
    auto context = Context();
    CandidateUi ui; ui.SetRenderEnvironment(96, 1600, false);
    ui.Present(state, true); ui.Update(context, status);
    auto light = ui.Render(GetTickCount64());
    Frame(frames, "light", light);
    checks.Check("five two-line candidates and toolbar measure 600 by 55 DIP", light.width == 600 && light.height == 55);
    checks.Check("outer corners are transparent and body is opaque", light.bgra[3] == 0 && light.bgra[(static_cast<size_t>(25) * light.width + 20) * 4 + 3] == 255);
    const auto* layout = ui.Geometry();
    const CRect en = layout->GetCandidateCommentRect(1), zh = layout->GetCandidateTextRect(1);
    checks.Check("English and Chinese rows share the same candidate hit target", layout->Hit(en.CenterPoint()) == 1 && layout->Hit(zh.CenterPoint()) == 1);
    int selected = -1, menuIndex = -1, pages = 0; bool requestedLearning = true;
    ui.SetUICallBack([&](size_t* selection, size_t*, bool* next, bool*) {
      if (selection) selected = static_cast<int>(*selection);
      if (next) pages += *next ? 1 : -1;
    });
    ui.studyMenu = [&](unsigned index, HWND, POINT) { menuIndex = static_cast<int>(index); };
    ui.studyLearning = [&](bool value) { requestedLearning = value; };
    ui.Invoke(layout->Hit(en.CenterPoint()));
    checks.Check("ordinary English-row action selects Chinese candidate independent of highlight", selected == 1 && ui.ctx().cinfo.highlighted == 0 && menuIndex == -1);
    ui.Invoke(StudyLayout::Previous);
    checks.Check("previous-page boundary is disabled without dispatch", pages == 0 && !ui.Enabled(StudyLayout::Previous));
    ui.Invoke(StudyLayout::Next);
    checks.Check("next-page tool dispatches the existing page callback", pages == 1);
    ui.Invoke(StudyLayout::Learning);
    checks.Check("learning tool requests a versioned toggle without selection", !requestedLearning && selected == 1);
    ui.Invoke(StudyLayout::More);
    checks.Check("more tool uses the current candidate index", menuIndex == 0);

    auto second = context; second.cinfo.currentPage = 1; second.cinfo.is_last_page = true;
    second.cinfo.candies.resize(1); second.cinfo.comments.resize(1); second.cinfo.labels.resize(1);
    second.cinfo.candies[0].str = L"最后一项"; second.cinfo.comments[0].str = L"last item";
    ++state.stamp.version.revision; ui.Present(state, true); ui.Update(second, status);
    const auto now = GetTickCount64();
    auto pageMid = ui.Render(now + 35); Frame(frames, "page-transition", pageMid);
    checks.Check("last page keeps width and toolbar coordinates", pageMid.width == light.width && ui.Geometry()->tools[0].left == 500);
    checks.Check("current page and hit targets switch before animation ends", ui.ctx().cinfo.currentPage == 1 && ui.ctx().cinfo.candies.size() == 1 && ui.Geometry()->Hit(ui.Geometry()->GetCandidateTextRect(0).CenterPoint()) == 0);
    checks.Check("outgoing candidates are absent from accessible names", ui.AccessibleName(0).find(L"最后一项") != std::wstring::npos && ui.AccessibleName(1).empty());
    ui.Present(state, true); ui.Update(context, status);
    auto pageBack = ui.Render(GetTickCount64() + 400);
    checks.Check("returning to previous page retains fixed width", pageBack.width == light.width);
    state.learning = false; ++state.stamp.version.revision;
    ui.Present(state, true); ui.Update(context, status);
    auto closeStart = GetTickCount64();
    Frame(frames, "learning-transition", ui.Render(closeStart + 50));
    checks.Check("learning-off immediately removes English accessibility during animation", ui.AccessibleName(0).find(L"hello") == std::wstring::npos && ui.ctx().cinfo.currentPage == context.cinfo.currentPage && ui.ctx().cinfo.highlighted == context.cinfo.highlighted);
    auto closed = ui.Render(closeStart + 300); Frame(frames, "closed", closed);
    checks.Check("learning-off ends at 38 DIP without changing width", closed.height == 38 && closed.width == light.width);
    ui.Present(state, false); ui.Update(context, status); selected = -1; ui.Invoke(0);
    checks.Check("missing study capability disables study controls but retains Chinese selection", !ui.Enabled(StudyLayout::Learning) && ui.Enabled(0) && selected == 0);
    ui.Invalidate(); selected = -1; ui.Invoke(0);
    checks.Check("invalidated snapshot cannot dispatch a stale pointer action", selected == -1 && !ui.Enabled(StudyLayout::More));

    state.learning = true;
    ui.InputKey('P', false); auto single = second; single.preedit.str = L"ping guo"; single.cinfo.currentPage = 0;
    single.cinfo.candies[0].str = L"苹果"; single.cinfo.comments[0].str = L"apple";
    ui.Present(state, true); ui.Update(single, status);
    checks.Check("new single-candidate composition uses a short bar", ui.Render(GetTickCount64() + 300).width == 208);
    single.cinfo.candies[0].str = L"非常长的中文候选短语";
    single.cinfo.comments[0].str = L"a complete and deliberately long English definition that must never be truncated in a commit";
    ui.InputKey('A', false); ui.Present(state, true); ui.Update(single, status);
    Frame(frames, "long", ui.Render(GetTickCount64() + 300));
    checks.Check("long Chinese expands its cell while English retains its full source value", ui.Geometry()->GetCandidateRect(0).Width() > 96 && ui.ctx().cinfo.comments[0].str.size() > 70);
    for (UINT dpi : {96, 120, 144, 192}) {
      CandidateUi scaled; scaled.SetRenderEnvironment(dpi, 1600, true);
      scaled.Present(state, true); scaled.Update(context, status);
      auto frame = scaled.Render(GetTickCount64());
      const auto* geometry = scaled.Geometry();
      bool hits = true;
      for (int i = 0; i < 5; ++i) hits = hits && geometry->Hit(geometry->GetCandidateCommentRect(i).CenterPoint()) == i && geometry->Hit(geometry->GetCandidateTextRect(i).CenterPoint()) == i;
      checks.Check("DPI " + std::to_string(dpi) + " scales geometry and preserves both-line hit regions", std::abs(frame.height - 55.0 * dpi / 96) <= 1 && hits && geometry->tools[3].right < frame.width);
      if (dpi == 192) Frame(frames, "dpi-192", frame);
    }
    CandidateUi narrow; narrow.SetRenderEnvironment(96, 320, true); narrow.Present(state, true); narrow.Update(context, status);
    auto constrained = narrow.Render(GetTickCount64());
    Frame(frames, "narrow", constrained);
    checks.Check("narrow work area constrains a single row without shrinking type", constrained.width <= 320 && constrained.height == 55 && narrow.Geometry()->GetCandidateRect(0).Width() == 96);
    context.cinfo.highlighted = 4; narrow.Present(state, true); narrow.Update(context, status);
    checks.Check("keyboard selection reveals an overflow candidate within fixed viewport", narrow.Geometry()->viewport.PtInRect(narrow.Geometry()->GetCandidateTextRect(4).CenterPoint()) && narrow.Render(GetTickCount64()).width == constrained.width);
    preferences.theme = Theme::Dark; SavePreferences(settings, preferences);
    CandidateUi dark; dark.SetRenderEnvironment(96, 1600, true); dark.Present(state, true); dark.Update(Context(), status);
    auto darkFrame = dark.Render(GetTickCount64()); Frame(frames, "dark", darkFrame);
    checks.Check("dark and light themes have identical geometry", darkFrame.width == light.width && darkFrame.height == light.height && darkFrame.bgra != light.bgra);
    preferences.largeText = true; SavePreferences(settings, preferences);
    CandidateUi large; large.SetRenderEnvironment(96, 1600, true); large.Present(state, true); large.Update(Context(), status);
    auto largeFrame = large.Render(GetTickCount64()); Frame(frames, "large", largeFrame);
    checks.Check("larger font preset increases line space without scaling the whole UI", largeFrame.height == 59 && large.Geometry()->tools[0].Width() == 24);

    EnglishTarget target; target.reason = "ready"; target.chinese = "hello target"; target.english = "full definition";
    EnglishMenuOptions options; options.details = options.settings = true; options.shortcut = L"Alt+Enter";
    HMENU menu = CreateEnglishMenu(target, options);
    wchar_t label[128]{}; GetMenuStringW(menu, kInputEnglish, label, 128, MF_BYCOMMAND);
    checks.Check("explicit English menu shows the configured shortcut and separate detail command", std::wstring(label).find(L"Alt+Enter") != std::wstring::npos && GetMenuState(menu, kViewDefinition, MF_BYCOMMAND) != 0xffffffff);
    checks.Check("settings menu is disabled during composition", (GetMenuState(menu, kOpenSettings, MF_BYCOMMAND) & MF_GRAYED) != 0);
    DestroyMenu(menu); options.learning = false; menu = CreateEnglishMenu(target, options);
    checks.Check("learning-off disables English and definition menu commands", (GetMenuState(menu, kInputEnglish, MF_BYCOMMAND) & MF_GRAYED) && (GetMenuState(menu, kViewDefinition, MF_BYCOMMAND) & MF_GRAYED));
    DestroyMenu(menu);

    preferences = {}; preferences.theme = Theme::Light; SavePreferences(settings, preferences);
    CandidateUi detail; detail.SetRenderEnvironment(96, 1600, true); detail.Create(nullptr);
    detail.Present(state, true); detail.Update(Context(), status);
    const auto originalSize = detail.Geometry()->GetContentSize();
    CandidateFrame detailFrame;
    detail.frameObserver = [&](bool definition, const CandidateFrame& frame) { if (definition) detailFrame = frame; };
    state.index = 0; state.chinese = "你好"; state.english = "A complete English explanation shown in a separate floating window. It wraps naturally and never resizes the candidate bar."; state.reason = "ready";
    detail.ShowDefinition(state, 0, true);
    checks.Check("full definition is an independent nonactivating floating window", detail.DefinitionVisible() && !detailFrame.bgra.empty() && detail.Geometry()->GetContentSize() == originalSize);
    Frame(frames, "definition", detailFrame);
    detail.Invalidate();
    checks.Check("candidate invalidation closes the definition immediately", !detail.DefinitionVisible());
    detail.Destroy(true);
    checks.Check("settings cannot open during a composing candidate state", !ui.ShowSettings(nullptr));
    std::cout << checks.items.size() << " native v0.5 component checks passed.\n";
  } catch (const std::exception& error) {
    std::cerr << error.what() << std::endl; _Module.Term(); CoUninitialize(); return 1;
  }
  _Module.Term(); CoUninitialize(); return 0;
}
