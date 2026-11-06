#pragma once
#include <windows.h>
#include <filesystem>
#include <string>

namespace study {
enum class Theme { System, Light, Dark };
enum class EnglishShortcut { ControlShiftEnter, AltEnter };

struct UiPreferences {
  bool learning = true;
  bool largeText = false;
  bool reduceMotion = false;
  Theme theme = Theme::System;
  EnglishShortcut shortcut = EnglishShortcut::ControlShiftEnter;
  bool operator==(const UiPreferences& other) const;
  bool operator!=(const UiPreferences& other) const { return !(*this == other); }
};
std::filesystem::path PreferencesPath();
UiPreferences LoadPreferences(const std::filesystem::path& path);
bool SavePreferences(const std::filesystem::path& path, const UiPreferences& preferences);
bool DarkAppearance(const UiPreferences& preferences);
bool ReducedMotion(const UiPreferences& preferences);
const wchar_t* ShortcutLabel(const UiPreferences& preferences);
// Modal native settings, called only outside a composition and any TSF lock.
bool EditPreferences(HWND owner, const std::filesystem::path& path, UiPreferences& preferences);
}
