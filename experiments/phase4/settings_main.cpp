#include <study/windows/UiPreferences.h>
#include <iostream>

int wmain(int argc, wchar_t** argv) {
  if (argc != 2) {
    std::cerr << "Usage: study_settings_x64.exe <isolated-settings-file>\n";
    return 2;
  }
  SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
  const std::filesystem::path path = argv[1];
  auto preferences = study::LoadPreferences(path);
  study::EditPreferences(nullptr, path, preferences);
  return 0;
}
