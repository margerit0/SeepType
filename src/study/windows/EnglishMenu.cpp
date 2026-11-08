#include "EnglishMenu.h"

namespace study {
namespace {
std::wstring wide(const std::string& value) {
  if (value.empty()) return {};
  const int size = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, value.data(),
                                      static_cast<int>(value.size()), nullptr, 0);
  if (size <= 0) return {};
  std::wstring result(size, L'\0');
  MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, value.data(),
                      static_cast<int>(value.size()), result.data(), size);
  return result;
}

std::wstring escaped(const std::wstring& value) {
  std::wstring result;
  for (wchar_t ch : value) {
    if (ch == L'&') result += L'&';
    result += ch;
  }
  return result;
}

const wchar_t* reasonText(const std::string& reason) {
  if (reason == "disabled") return L"学习模式已关闭";
  if (reason == "no-candidate") return L"当前没有候选词";
  if (reason == "no-definition") return L"此候选暂无英文释义";
  if (reason == "partial-composition") return L"请先完成整段拼音";
  if (reason == "stale-candidate") return L"候选已变化，请重新打开菜单";
  return L"英文功能暂不可用";
}
}

HMENU CreateEnglishMenu(const EnglishTarget& target, const EnglishMenuOptions& options) {
  HMENU menu = CreatePopupMenu();
  if (!menu) return nullptr;
  const auto chinese = wide(target.chinese);
  const auto english = wide(target.english);
  const bool enabled = target.Available() && !english.empty();
  std::wstring label = chinese.empty() ? L"英文释义" : chinese;
  if (!english.empty()) label += L" · " + english;
  label = escaped(label);
  AppendMenuW(menu, MF_STRING | MF_GRAYED, 0, label.c_str());
  if (!enabled)
    AppendMenuW(menu, MF_STRING | MF_GRAYED, 0, reasonText(target.reason));
  AppendMenuW(menu, MF_SEPARATOR, 0, nullptr);
  const std::wstring command = std::wstring(L"输入英文\t") + options.shortcut;
  AppendMenuW(menu, MF_STRING | (enabled && options.learning ? 0 : MF_GRAYED), kInputEnglish, command.c_str());
  if (options.details)
    AppendMenuW(menu, MF_STRING | (options.learning ? 0 : MF_GRAYED), kViewDefinition, L"查看完整释义\tF2");
  if (options.forget) {
    AppendMenuW(menu, MF_SEPARATOR, 0, nullptr);
    AppendMenuW(menu, MF_STRING | (options.composing && !chinese.empty() ? 0 : MF_GRAYED),
        kForgetWord, L"忘记此词的学习记录");
  }
  if (options.settings) {
    AppendMenuW(menu, MF_SEPARATOR, 0, nullptr);
    AppendMenuW(menu, MF_STRING | (options.composing ? MF_GRAYED : 0), kOpenSettings,
        options.composing ? L"设置（完成输入后 Ctrl+Shift+F12）" : L"设置\tCtrl+Shift+F12");
  }
  return menu;
}

UINT ShowEnglishMenu(HWND owner, POINT position, const EnglishTarget& target, const EnglishMenuOptions& options) {
  HMENU menu = CreateEnglishMenu(target, options);
  if (!menu) return 0;
  const UINT chosen = TrackPopupMenuEx(menu,
      TPM_RETURNCMD | TPM_NONOTIFY | TPM_LEFTALIGN | TPM_TOPALIGN | TPM_RIGHTBUTTON,
      position.x, position.y, owner, nullptr);
  DestroyMenu(menu);
  PostMessageW(owner, WM_NULL, 0, 0);
  return chosen;
}

}  // namespace study
