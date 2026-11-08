#pragma once

#include <windows.h>
#include "../SessionActions.h"

namespace study {

constexpr UINT kInputEnglish = 1;
constexpr UINT kViewDefinition = 2, kOpenSettings = 3;
constexpr UINT kForgetWord = 4;
struct EnglishMenuOptions {
  bool details = false, learning = true, settings = false, composing = true;
  bool forget = false;
  const wchar_t* shortcut = L"Ctrl+Shift+Enter";
};
HMENU CreateEnglishMenu(const EnglishTarget& target, const EnglishMenuOptions& options = {});
UINT ShowEnglishMenu(HWND owner, POINT position, const EnglishTarget& target, const EnglishMenuOptions& options = {});

}  // namespace study
