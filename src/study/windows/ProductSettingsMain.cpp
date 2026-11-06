#include "UiPreferences.h"
#include <ProductIdentity.h>
#include <iostream>

int wmain(int argc, wchar_t** argv) {
  if (argc == 2 && std::wstring(argv[1]) == L"--identity") {
    std::cout << study::kProductIdentityJson << std::endl;
    return 0;
  }
  if (argc != 1) return 2;
  const auto path = study::PreferencesPath();
  auto preferences = study::LoadPreferences(path);
  study::EditPreferences(nullptr, path, preferences);
  return 0;
}
