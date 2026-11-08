// Targeted regression probe for the product layout's removal of WTL.
// It uses the same product objects as the TSF DLL and creates no desktop UI.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <study/windows/CandidateUi.h>
#include <study/windows/ProductRuntime.h>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>

struct Checks {
  std::filesystem::path path;
  std::vector<std::pair<std::string, bool>> items;
  void Check(const std::string& name, bool passed) {
    items.emplace_back(name, passed);
    std::ofstream out(path);
    out << "{\"checks\":[";
    for (size_t i = 0; i < items.size(); ++i) {
      if (i) out << ',';
      out << "{\"name\":\"" << items[i].first << "\",\"passed\":"
          << (items[i].second ? "true" : "false") << '}';
    }
    out << "]}\n";
    std::cout << (passed ? "PASS " : "FAIL ") << name << std::endl;
    if (!passed) throw std::runtime_error(name);
  }
};

static weasel::Context Fixture() {
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

static void Frame(const std::filesystem::path& directory, const std::string& name,
                  const study::CandidateFrame& frame) {
  if (frame.bgra.size() != static_cast<size_t>(frame.width) * frame.height * 4 || frame.bgra.empty())
    throw std::runtime_error("Invalid native frame");
  std::ofstream pixels(directory / (name + ".bgra"), std::ios::binary);
  pixels.write(reinterpret_cast<const char*>(frame.bgra.data()), frame.bgra.size());
  std::ofstream meta(directory / (name + ".json"));
  meta << "{\"width\":" << frame.width << ",\"height\":" << frame.height << "}\n";
}

int wmain(int argc, wchar_t** argv) {
  if (argc != 3 || !GetEnvironmentVariableW(L"STUDYIME_DEV_SESSION", nullptr, 0) ||
      !GetEnvironmentVariableW(L"STUDYIME_DEV_DATA_ROOT", nullptr, 0)) return 2;
  if (FAILED(CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED))) return 3;
  int result = 0;
  try {
    using namespace study;
    ProductInstanceSuffix();  // Validate the isolated session/data pair.
    const std::filesystem::path frames = argv[2];
    std::filesystem::create_directories(frames);
    Checks checks{argv[1]};
    UiPreferences preferences;
    preferences.theme = Theme::Light;
    checks.Check("isolated product preferences saved", SavePreferences(PreferencesPath(), preferences));
    weasel::Status status;
    status.composing = true;
    ActionState state;
    state.learning = true;
    state.stamp = {19, {23, 1}};
    const auto context = Fixture();
    for (UINT dpi : {96, 120, 144, 192}) {
      CandidateUi ui;
      ui.SetRenderEnvironment(dpi, 1600, true);
      ui.Present(state, true);
      ui.Update(context, status);
      const auto frame = ui.Render(GetTickCount64());
      const auto* geometry = ui.Geometry();
      bool hits = true, selections = true;
      int selected = -1, menus = 0;
      ui.SetUICallBack([&](size_t* selection, size_t*, bool*, bool*) {
        if (selection) selected = static_cast<int>(*selection);
      });
      ui.studyMenu = [&](unsigned, HWND, POINT) { ++menus; };
      for (int i = 0; i < 5; ++i) {
        for (const auto rect : {geometry->GetCandidateCommentRect(i), geometry->GetCandidateTextRect(i)}) {
          const int hit = geometry->Hit(rect.CenterPoint());
          hits = hits && hit == i;
          selected = -1;
          ui.Invoke(hit);
          selections = selections && selected == i && menus == 0;
        }
      }
      checks.Check("DPI " + std::to_string(dpi) + " geometry and both-line Chinese selection",
          std::abs(frame.width - 600.0 * dpi / 96) <= 4 &&
          std::abs(frame.height - 55.0 * dpi / 96) <= 1 && hits && selections);
      Frame(frames, "dpi-" + std::to_string(dpi), frame);
      if (dpi == 96) Frame(frames, "light", frame);
      ui.Invalidate();
      selected = -1;
      ui.Invoke(0);
      checks.Check("DPI " + std::to_string(dpi) + " invalidated action rejected", selected == -1);
    }
    CandidateUi paging;
    paging.SetRenderEnvironment(96, 1600, true);
    paging.Present(state, true); paging.Update(context, status);
    const auto width = paging.Render(GetTickCount64()).width;
    auto second = context;
    second.cinfo.currentPage = 1; second.cinfo.is_last_page = true;
    second.cinfo.candies.resize(1); second.cinfo.comments.resize(1); second.cinfo.labels.resize(1);
    ++state.stamp.version.revision;
    paging.Present(state, true); paging.Update(second, status);
    checks.Check("last page retains candidate viewport and toolbar", paging.Render(GetTickCount64()).width == width && paging.Geometry()->tools[0].left == 500);
    ++state.stamp.version.revision;
    paging.Present(state, true); paging.Update(context, status);
    state.learning = false; ++state.stamp.version.revision;
    paging.Present(state, true); paging.Update(context, status);
    const auto closed = paging.Render(GetTickCount64() + 300);
    Frame(frames, "closed", closed);
    checks.Check("learning off retains width and Chinese row", closed.width == 600 && closed.height == 38);
    state.learning = true; ++state.stamp.version.revision;
    CandidateUi narrow;
    narrow.SetRenderEnvironment(96, 320, true);
    narrow.Present(state, true); narrow.Update(context, status);
    const auto constrained = narrow.Render(GetTickCount64());
    Frame(frames, "narrow", constrained);
    checks.Check("narrow viewport keeps full-sized candidate cells", constrained.width <= 320 && constrained.height == 55 && narrow.Geometry()->GetCandidateRect(0).Width() == 96);
    preferences.theme = Theme::Dark;
    if (!SavePreferences(PreferencesPath(), preferences)) throw std::runtime_error("Cannot save dark preferences");
    CandidateUi dark;
    dark.SetRenderEnvironment(96, 1600, true); dark.Present(state, true); dark.Update(context, status);
    Frame(frames, "dark", dark.Render(GetTickCount64()));
    preferences.largeText = true;
    if (!SavePreferences(PreferencesPath(), preferences)) throw std::runtime_error("Cannot save large preferences");
    CandidateUi large;
    large.SetRenderEnvironment(96, 1600, true); large.Present(state, true); large.Update(context, status);
    const auto largeFrame = large.Render(GetTickCount64());
    Frame(frames, "large", largeFrame);
    checks.Check("large font preserves toolbar size", largeFrame.height == 59 && large.Geometry()->tools[0].Width() == 24);
    StudyMotion motion;
    motion.Reset(true); motion.Page(1, 1000, false);
    checks.Check("paging duration remains 180 milliseconds", motion.At(1179).active && !motion.At(1180).active);
    motion.SetLearning(false, 1200, false);
    checks.Check("learning duration remains 240 milliseconds", motion.At(1439).active && !motion.At(1440).active);
    CandidateUi preferenceOwner;
    preferences.userLearning = false;
    preferences.inputScheme = InputScheme::Flypy;
    checks.Check("external word learning preference saved", SavePreferences(PreferencesPath(), preferences));
    checks.Check("English toolbar toggle preserves externally changed word learning", preferenceOwner.SaveLearning(false) &&
        !LoadPreferences(PreferencesPath()).userLearning && !LoadPreferences(PreferencesPath()).learning);
    checks.Check("English toolbar toggle preserves the externally selected input scheme",
        LoadPreferences(PreferencesPath()).inputScheme == InputScheme::Flypy);
  } catch (const std::exception& error) {
    std::cerr << error.what() << std::endl;
    result = 1;
  }
  CoUninitialize();
  return result;
}
