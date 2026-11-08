#include "UiPreferences.h"
#include <shlobj.h>
#include <fstream>
#include <map>
#ifdef WEASEL_STUDY_PRODUCT
#include "ProductRuntime.h"
#include <ProductIdentity.h>
#endif

namespace study {
bool UiPreferences::operator==(const UiPreferences& p) const {
  return learning == p.learning && userLearning == p.userLearning &&
      largeText == p.largeText && reduceMotion == p.reduceMotion &&
      theme == p.theme && shortcut == p.shortcut && inputScheme == p.inputScheme;
}
std::filesystem::path PreferencesPath() {
#ifdef WEASEL_STUDY_PRODUCT
  return ProductUserRoot() / L"settings.ini";
#else
  wchar_t path[32768]{};
  const DWORD count = GetEnvironmentVariableW(L"STUDY_SETTINGS_PATH", path, 32768);
  if (count && count < 32768) return path;
#ifdef WEASEL_STUDY_ISOLATED
  return {};  // Isolated hosts must opt in to an explicit local settings file.
#else
  PWSTR local = nullptr;
  if (FAILED(SHGetKnownFolderPath(FOLDERID_LocalAppData, 0, nullptr, &local))) return {};
  auto result = std::filesystem::path(local) / L"StudyIme" / L"settings.ini";
  CoTaskMemFree(local);
  return result;
#endif
#endif
}
UiPreferences LoadPreferences(const std::filesystem::path& path) {
  UiPreferences result;
  if (path.empty()) return result;
  std::ifstream file(path, std::ios::binary);
  std::string text(2049, '\0');
  file.read(text.data(), static_cast<std::streamsize>(text.size()));
  text.resize(static_cast<size_t>(file.gcount()));
  if (text.size() > 2048) return result;
  std::map<std::string, std::string> values;
  size_t start = 0;
  while (start < text.size()) {
    auto end = text.find('\n', start);
    if (end == std::string::npos) end = text.size();
    auto line = text.substr(start, end - start);
    if (!line.empty() && line.back() == '\r') line.pop_back();
    auto split = line.find('=');
    if (split != std::string::npos) {
      auto key = line.substr(0, split);
      if (values.count(key)) return UiPreferences{};
      values.emplace(key, line.substr(split + 1));
    }
    start = end + 1;
  }
  if (values["version"] != "1") return result;
  if (values["learning"] == "0") result.learning = false;
  if (values["user_learning"] == "0") result.userLearning = false;
  result.largeText = values["large_text"] == "1";
  result.reduceMotion = values["reduce_motion"] == "1";
  if (values["theme"] == "light") result.theme = Theme::Light;
  if (values["theme"] == "dark") result.theme = Theme::Dark;
  if (values["shortcut"] == "alt_enter") result.shortcut = EnglishShortcut::AltEnter;
  result.inputScheme = ParseInputScheme(values["input_scheme"]);
  return result;
}
bool SavePreferences(const std::filesystem::path& path, const UiPreferences& p) {
  if (path.empty()) return false;
  std::error_code error;
  if (!path.parent_path().empty()) std::filesystem::create_directories(path.parent_path(), error);
  if (error) return false;
  auto pending = path;
  pending += L"." + std::to_wstring(GetCurrentProcessId()) + L"." +
      std::to_wstring(GetCurrentThreadId()) + L".tmp";
  std::ofstream file(pending, std::ios::binary | std::ios::trunc);
  file << "version=1\nlearning=" << p.learning << "\nuser_learning=" << p.userLearning
       << "\nlarge_text=" << p.largeText
       << "\nreduce_motion=" << p.reduceMotion << "\ntheme="
       << (p.theme == Theme::Light ? "light" : p.theme == Theme::Dark ? "dark" : "system")
       << "\nshortcut=" << (p.shortcut == EnglishShortcut::AltEnter ? "alt_enter" : "ctrl_shift_enter")
       << "\ninput_scheme=" << InputSchemaId(p.inputScheme) << '\n';
  file.flush();
  const bool written = file.good();
  file.close();
  if (written && MoveFileExW(pending.c_str(), path.c_str(), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) return true;
  std::filesystem::remove(pending, error);
  return false;
}
bool DarkAppearance(const UiPreferences& p) {
  if (p.theme != Theme::System) return p.theme == Theme::Dark;
  DWORD light = 1, size = sizeof(light);
  RegGetValueW(HKEY_CURRENT_USER, L"Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize",
      L"AppsUseLightTheme", RRF_RT_REG_DWORD, nullptr, &light, &size);
  return !light;
}
bool ReducedMotion(const UiPreferences& p) {
  BOOL enabled = TRUE;
  SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION, 0, &enabled, 0);
  return p.reduceMotion || !enabled;
}
const wchar_t* ShortcutLabel(const UiPreferences& p) {
  return p.shortcut == EnglishShortcut::AltEnter ? L"Alt+Enter" : L"Ctrl+Shift+Enter";
}
namespace {
struct SettingsDialog {
  HWND window = nullptr;
  HFONT font = nullptr;
  bool done = false, saved = false;
  UiPreferences value;
  std::filesystem::path path;
  int scale = 96;
  int Px(int dip) const { return MulDiv(dip, scale, 96); }
  HWND Control(const wchar_t* kind, const wchar_t* text, int id, int x, int y, int width, int height, DWORD extra = 0) {
    HWND child = CreateWindowExW(0, kind, text, WS_CHILD | WS_VISIBLE | extra, Px(x), Px(y), Px(width), Px(height),
        window, reinterpret_cast<HMENU>(static_cast<INT_PTR>(id)), GetModuleHandleW(nullptr), nullptr);
    SendMessageW(child, WM_SETFONT, reinterpret_cast<WPARAM>(font), TRUE);
    return child;
  }
  void Create() {
    scale = static_cast<int>(GetDpiForWindow(window));
    font = CreateFontW(-Px(14), 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE, DEFAULT_CHARSET,
        0, 0, CLEARTYPE_QUALITY, 0, L"Microsoft YaHei UI");
    Control(L"STATIC", L"基本设置", 0, 24, 20, 450, 26);
    int offset = 0;
#ifdef WEASEL_STUDY_PRODUCT
    Control(L"STATIC", L"输入方案", 0, 24, 54, 140, 25);
    auto scheme = Control(L"COMBOBOX", L"", 108, 186, 50, 268, 150, CBS_DROPDOWNLIST | WS_TABSTOP);
    for (const auto* item : {L"全拼", L"自然码双拼", L"小鹤双拼"})
      SendMessageW(scheme, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(item));
    SendMessageW(scheme, CB_SETCURSEL, static_cast<int>(value.inputScheme), 0);
    Control(L"STATIC", L"切换后从下一次输入生效，三种方案共享选词习惯。", 0, 24, 88, 440, 26);
    offset = 72;
#endif
    auto learning = Control(L"BUTTON", L"英语学习：显示英文释义", 101, 24, 54 + offset, 430, 28, BS_AUTOCHECKBOX | WS_TABSTOP);
    SendMessageW(learning, BM_SETCHECK, value.learning ? BST_CHECKED : BST_UNCHECKED, 0);
    auto userLearning = Control(L"BUTTON", L"记住中文选词习惯", 107, 24, 88 + offset, 430, 28, BS_AUTOCHECKBOX | WS_TABSTOP);
    SendMessageW(userLearning, BM_SETCHECK, value.userLearning ? BST_CHECKED : BST_UNCHECKED, 0);
    Control(L"STATIC", L"关闭后停止学习，已有记录仍参与排序。\r\n右键候选可忘记该词当前读音的学习记录。", 0, 24, 122 + offset, 440, 42);
    Control(L"STATIC", L"中文字号", 0, 24, 184 + offset, 140, 25);
    auto size = Control(L"COMBOBOX", L"", 102, 186, 180 + offset, 268, 120, CBS_DROPDOWNLIST | WS_TABSTOP);
    SendMessageW(size, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(L"常规 · 18px"));
    SendMessageW(size, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(L"较大 · 20px"));
    SendMessageW(size, CB_SETCURSEL, value.largeText ? 1 : 0, 0);
    Control(L"STATIC", L"外观", 0, 24, 226 + offset, 140, 25);
    auto theme = Control(L"COMBOBOX", L"", 103, 186, 222 + offset, 268, 160, CBS_DROPDOWNLIST | WS_TABSTOP);
    for (const auto* item : {L"跟随系统", L"浅色", L"深色"}) SendMessageW(theme, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(item));
    SendMessageW(theme, CB_SETCURSEL, static_cast<int>(value.theme), 0);
    Control(L"STATIC", L"输入英文", 0, 24, 268 + offset, 140, 25);
    auto shortcut = Control(L"COMBOBOX", L"", 104, 186, 264 + offset, 268, 130, CBS_DROPDOWNLIST | WS_TABSTOP);
    for (const auto* item : {L"Ctrl+Shift+Enter", L"Alt+Enter"}) SendMessageW(shortcut, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(item));
    SendMessageW(shortcut, CB_SETCURSEL, static_cast<int>(value.shortcut), 0);
    Control(L"STATIC", L"仅明确操作输入英文；空格、数字和普通点击仍输入中文。\r\n快捷键如与应用冲突，可更换预设。F2 查看完整释义。", 0, 24, 310 + offset, 440, 48);
    auto motion = Control(L"BUTTON", L"减少动态效果", 105, 24, 370 + offset, 430, 26, BS_AUTOCHECKBOX | WS_TABSTOP);
    SendMessageW(motion, BM_SETCHECK, value.reduceMotion ? BST_CHECKED : BST_UNCHECKED, 0);
#ifdef WEASEL_STUDY_PRODUCT
    Control(L"STATIC", L"词库：日常 200 条 · 审核预览，词义待人工审核。\r\n软件与词库许可见随附的许可与来源说明。\r\n中文选词、造词记录与偏好仅存本机，不上传。", 0, 24, 414 + offset, 450, 72);
#else
    Control(L"STATIC", L"词库：study-fixtures v0.1 · 21 条测试词对\r\n测试数据尚未人工验收，不作为正式词库分发。\r\n选词学习仅在启用用户词典的产品方案中生效。", 0, 24, 414, 450, 72);
#endif
    Control(L"STATIC", L"", 106, 24, 500 + offset, 238, 44);
    Control(L"BUTTON", L"取消", IDCANCEL, 278, 500 + offset, 80, 32, WS_TABSTOP);
    Control(L"BUTTON", L"保存", IDOK, 374, 500 + offset, 80, 32, BS_DEFPUSHBUTTON | WS_TABSTOP);
    RECT bounds{0, 0, Px(482), Px(550 + offset)};
    AdjustWindowRectExForDpi(&bounds, WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU, FALSE, WS_EX_DLGMODALFRAME, scale);
    SetWindowPos(window, nullptr, 0, 0, bounds.right - bounds.left, bounds.bottom - bounds.top, SWP_NOMOVE | SWP_NOZORDER);
  }
  void Save() {
#ifdef WEASEL_STUDY_PRODUCT
    const auto scheme = SendDlgItemMessageW(window, 108, CB_GETCURSEL, 0, 0);
    if (scheme < 0 || scheme > static_cast<int>(InputScheme::Flypy)) return;
    value.inputScheme = static_cast<InputScheme>(scheme);
#endif
    value.learning = SendDlgItemMessageW(window, 101, BM_GETCHECK, 0, 0) == BST_CHECKED;
    value.userLearning = SendDlgItemMessageW(window, 107, BM_GETCHECK, 0, 0) == BST_CHECKED;
    value.largeText = SendDlgItemMessageW(window, 102, CB_GETCURSEL, 0, 0) == 1;
    value.theme = static_cast<Theme>(SendDlgItemMessageW(window, 103, CB_GETCURSEL, 0, 0));
    value.shortcut = static_cast<EnglishShortcut>(SendDlgItemMessageW(window, 104, CB_GETCURSEL, 0, 0));
    value.reduceMotion = SendDlgItemMessageW(window, 105, BM_GETCHECK, 0, 0) == BST_CHECKED;
    if (!SavePreferences(path, value)) { SetDlgItemTextW(window, 106, L"无法保存设置，请检查文件位置。" ); return; }
    saved = true;
    DestroyWindow(window);
  }
  static LRESULT CALLBACK Proc(HWND window, UINT message, WPARAM wp, LPARAM lp) {
    auto* self = reinterpret_cast<SettingsDialog*>(GetWindowLongPtrW(window, GWLP_USERDATA));
    if (message == WM_NCCREATE) {
      self = static_cast<SettingsDialog*>(reinterpret_cast<CREATESTRUCTW*>(lp)->lpCreateParams);
      self->window = window;
      SetWindowLongPtrW(window, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(self));
    }
    if (self) {
      if (message == WM_CREATE) { self->Create(); return 0; }
      if (message == WM_COMMAND && LOWORD(wp) == IDOK) { self->Save(); return 0; }
      if (message == WM_COMMAND && LOWORD(wp) == IDCANCEL) { DestroyWindow(window); return 0; }
      if (message == WM_DESTROY) { self->done = true; return 0; }
    }
    return DefWindowProcW(window, message, wp, lp);
  }
};
}
bool EditPreferences(HWND owner, const std::filesystem::path& path, UiPreferences& preferences) {
  SettingsDialog dialog;
  dialog.value = preferences; dialog.path = path;
  WNDCLASSW cls{}; cls.hInstance = GetModuleHandleW(nullptr); cls.lpszClassName = L"StudyImeSettings";
  cls.lpfnWndProc = SettingsDialog::Proc; cls.hCursor = LoadCursor(nullptr, IDC_ARROW);
  cls.hbrBackground = reinterpret_cast<HBRUSH>(COLOR_WINDOW + 1);
  const ATOM atom = RegisterClassW(&cls);
  if (!atom && GetLastError() != ERROR_CLASS_ALREADY_EXISTS) return false;
#ifdef WEASEL_STUDY_PRODUCT
  const auto title = std::wstring(kProductName) + L" · 设置";
#else
  const std::wstring title = L"英语学习输入法 · 设置";
#endif
  HWND window = CreateWindowExW(WS_EX_DLGMODALFRAME, cls.lpszClassName, title.c_str(),
      WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU, CW_USEDEFAULT, CW_USEDEFAULT, 500, 550, owner, nullptr, cls.hInstance, &dialog);
  if (!window) return false;
  ShowWindow(window, SW_SHOW);
  SetFocus(GetDlgItem(window, GetDlgItem(window, 108) ? 108 : 101));
  MSG msg{};
  while (!dialog.done && GetMessageW(&msg, nullptr, 0, 0) > 0) {
    if (!IsDialogMessageW(window, &msg)) { TranslateMessage(&msg); DispatchMessageW(&msg); }
  }
  if (IsWindow(window)) DestroyWindow(window);
  if (dialog.font) DeleteObject(dialog.font);
  if (msg.message == WM_QUIT) PostQuitMessage(static_cast<int>(msg.wParam));
  if (dialog.saved) preferences = dialog.value;
  if (atom) UnregisterClassW(cls.lpszClassName, cls.hInstance);
  return dialog.saved;
}
}
