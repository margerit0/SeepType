#include "StudyProtocol.h"
#include <array>
#include <limits>
#include <vector>

namespace study {
namespace {

std::vector<std::wstring_view> Split(std::wstring_view value, wchar_t separator) {
  std::vector<std::wstring_view> parts;
  std::size_t start = 0;
  while (true) {
    const auto end = value.find(separator, start);
    if (end == value.npos) { parts.push_back(value.substr(start)); break; }
    parts.push_back(value.substr(start, end - start));
    start = end + 1;
  }
  return parts;
}

bool Number(std::wstring_view value, std::uint64_t& number) {
  number = 0;
  if (value.empty() || value.size() > 20) return false;
  for (auto c : value) {
    if (c < L'0' || c > L'9') return false;
    const auto digit = static_cast<unsigned>(c - L'0');
    if (number > (std::numeric_limits<std::uint64_t>::max() - digit) / 10)
      return false;
    number = number * 10 + digit;
  }
  return true;
}

std::string Hex(std::string_view value) {
  constexpr char digits[] = "0123456789abcdef";
  std::string result;
  for (unsigned char c : value) {
    result += digits[c >> 4]; result += digits[c & 15];
  }
  return result;
}

bool Unhex(std::wstring_view value, std::string& result) {
  if (value.size() % 2 || value.size() > 2 * kMaxDefinitionBytes) return false;
  auto digit = [](wchar_t c) -> int {
    if (c >= L'0' && c <= L'9') return c - L'0';
    if (c >= L'a' && c <= L'f') return c - L'a' + 10;
    return -1;
  };
  result.clear();
  for (std::size_t i = 0; i < value.size(); i += 2) {
    const int a = digit(value[i]), b = digit(value[i + 1]);
    if (a < 0 || b < 0) return false;
    const char c = static_cast<char>(a * 16 + b);
    if (static_cast<unsigned char>(c) < 32 || c == 127) return false;
    result += c;
  }
  return true;
}

bool Reason(std::wstring_view value, std::string& result) {
  static constexpr std::wstring_view allowed[] = {
    L"ready", L"disabled", L"no-candidate", L"no-definition",
    L"partial-composition", L"unavailable", L"stale-candidate",
    L"inactive-session", L"invalid-request", L"english-committed",
    L"learning-changed", L"snapshot"
  };
  for (const auto reason : allowed) {
    if (value == reason) { result.assign(value.begin(), value.end()); return true; }
  }
  return false;
}

bool Stamp(const std::vector<std::wstring_view>& fields, std::size_t start,
           ActionStamp& stamp) {
  return Number(fields[start], stamp.service) && stamp.service &&
      Number(fields[start + 1], stamp.version.session) && stamp.version.session &&
      Number(fields[start + 2], stamp.version.revision) && stamp.version.revision;
}

}  // namespace

std::wstring EncodeRequest(const ActionRequest& request) {
  const auto action = request.action == Action::Inspect ? L"inspect" :
      request.action == Action::CommitEnglish ? L"commit" : L"learning";
  return std::wstring(L"study.v1=") + action + L"," +
      std::to_wstring(request.stamp.service) + L"," +
      std::to_wstring(request.stamp.version.session) + L"," +
      std::to_wstring(request.stamp.version.revision) + L"," +
      std::to_wstring(request.index) + L"," + (request.enabled ? L"1" : L"0") +
      L"\n.\n";
}

bool DecodeRequest(std::wstring_view text, ActionRequest& request) {
  request = {};
  if (text.size() > kMaxRequestChars || text.size() < 12 ||
      text.substr(0, 9) != L"study.v1=" ||
      text.substr(text.size() - 3) != L"\n.\n") return false;
  const auto fields = Split(text.substr(9, text.size() - 12), L',');
  if (fields.size() != 6) return false;
  ActionRequest parsed;
  if (fields[0] == L"inspect") parsed.action = Action::Inspect;
  else if (fields[0] == L"commit") parsed.action = Action::CommitEnglish;
  else if (fields[0] == L"learning") parsed.action = Action::SetLearning;
  else return false;
  std::uint64_t index, enabled;
  if (!Stamp(fields, 1, parsed.stamp) || !Number(fields[4], index) ||
      index > 255 || !Number(fields[5], enabled) || enabled > 1 ||
      (parsed.action != Action::SetLearning && enabled != 0) ||
      (parsed.action == Action::SetLearning && index != 0)) return false;
  parsed.index = static_cast<std::uint32_t>(index);
  parsed.enabled = enabled != 0;
  request = parsed;
  return true;
}

std::string EncodeState(const ActionState& state) {
  if (state.chinese.size() > kMaxDefinitionBytes ||
      state.english.size() > kMaxDefinitionBytes) return {};
  return "study.v1=" + std::to_string(state.stamp.service) + "," +
      std::to_string(state.stamp.version.session) + "," +
      std::to_string(state.stamp.version.revision) + "," +
      (state.learning ? "1" : "0") + "," + std::to_string(state.index) + "," +
      state.reason + "," + Hex(state.chinese) + "," + Hex(state.english) + "\n";
}

bool DecodeState(std::wstring_view response, ActionState& state) {
  state = {};
  if (response.size() > 32768) return false;
  bool found = false, complete = false;
  ActionState parsed;
  for (auto line : Split(response, L'\n')) {
    if (line == L".") { complete = true; break; }
    if (line.substr(0, 9) != L"study.v1=") continue;
    if (found) return false;
    found = true;
    const auto fields = Split(line.substr(9), L',');
    std::uint64_t learning, index;
    if (fields.size() != 8 || !Stamp(fields, 0, parsed.stamp) ||
        !Number(fields[3], learning) || learning > 1 ||
        !Number(fields[4], index) || index > 255 ||
        !Reason(fields[5], parsed.reason) ||
        !Unhex(fields[6], parsed.chinese) || !Unhex(fields[7], parsed.english))
      return false;
    parsed.learning = learning != 0;
    parsed.index = static_cast<std::uint32_t>(index);
    if (parsed.reason == "ready" &&
        (!parsed.learning || parsed.english.empty() || parsed.chinese.empty()))
      return false;
  }
  if (!found || !complete) return false;
  state = std::move(parsed);
  return true;
}

}  // namespace study
