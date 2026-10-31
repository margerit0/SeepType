// Behavioral checks against the real isolated Rime/Lua session, not a mock.
#include "StudyEngine.h"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

int wmain(int argc, wchar_t** argv) {
  if (argc != 2) return 2;
  const auto root = std::filesystem::absolute(argv[1]);
  study::Engine engine;
  if (!engine.Open(root)) return 3;
  std::filesystem::create_directories(root / L"experiments/phase4/results");
  std::ofstream report(root / L"experiments/phase4/results/session-actions.json");
  report << "{\"scope\":\"Actual isolated Rime/Lua sessions with candidate-version and frontend-action guards; no TSF or OS input injection\",\"checks\":[";
  bool all = true, first = true;
  auto check = [&](const char* name, bool passed) {
    all = all && passed;
    if (!first) report << ',';
    first = false;
    report << "{\"name\":\"" << name << "\",\"passed\":" << (passed ? "true" : "false") << '}';
    report.flush();
    std::cout << (passed ? "PASS " : "FAIL ") << name << std::endl;
  };
  auto fresh = [&](const char* input) {
    if (!engine.ResetSession()) throw std::runtime_error("Cannot reset isolated session");
    engine.Type(input);
  };
  auto unchanged = [&](const std::string& input) {
    const auto result = engine.Read();
    return result.input == input && result.commit.empty();
  };

  fresh("pingguo");
  const auto before = engine.Read();
  auto target = engine.PrepareEnglish(0);
  const auto inspected = engine.Read();
  check("Lua inspection exposes exact full definition without input or commit changes",
    target.Available() && target.chinese == "苹果" && target.english == "apple" &&
    inspected.input == before.input && inspected.commit.empty() &&
    inspected.version.revision == before.version.revision);
  const bool accepted = engine.CommitEnglish(target);
  const auto menuCommit = engine.Read();
  fresh("pingguo"); engine.Key(65293, 5);
  const auto keyboardCommit = engine.Read();
  check("frontend and keyboard actions use the same Lua English commit",
    accepted && menuCommit.commit == "apple" && menuCommit.input.empty() &&
    keyboardCommit.commit == menuCommit.commit && keyboardCommit.input.empty());

  fresh("pingguo"); target = engine.PrepareEnglish(0);
  engine.CommitEnglish(target); engine.Read();
  const bool repeated = engine.CommitEnglish(target);
  check("consumed action cannot duplicate English", !repeated && unchanged(""));

  fresh("pingguo"); target = engine.PrepareEnglish(0);
  engine.Key(65288);
  const bool afterTyping = engine.CommitEnglish(target);
  check("editing pinyin invalidates an open menu target", !afterTyping && unchanged("pinggu"));

  fresh("shishi"); target = engine.PrepareEnglish(0);
  engine.Key(65366);
  const auto pageTwo = engine.PrepareEnglish(0);
  const bool oldPage = engine.CommitEnglish(target);
  check("old page target is rejected while current page has its own full definition",
    !oldPage && pageTwo.page == 1 && pageTwo.chinese == "适时" &&
    pageTwo.english == "at the right time" && unchanged("shishi"));
  engine.Key(65365);
  const bool restoredPage = engine.CommitEnglish(target);
  check("paging back to identical candidates does not revive a stale target",
    !restoredPage && unchanged("shishi"));

  fresh("shishi"); target = engine.PrepareEnglish(0); engine.Highlight(2);
  const bool oldSelection = engine.CommitEnglish(target);
  const auto selected = engine.PrepareEnglish(2);
  const bool selectedAccepted = engine.CommitEnglish(selected);
  const auto selectedCommit = engine.Read();
  check("candidate selection invalidates old actions and commits the selected word",
    !oldSelection && selected.chinese == "试试" && selectedAccepted &&
    selectedCommit.commit == "give it a try");

  fresh("pingguo"); target = engine.PrepareEnglish(0); engine.Key(65477);
  const auto disabled = engine.PrepareEnglish(0);
  const bool disabledAccepted = engine.CommitEnglish(disabled);
  check("learning off hides the definition and blocks English without losing composition",
    !disabled.Available() && disabled.reason == "disabled" && disabled.english.empty() &&
    !disabledAccepted && unchanged("pingguo"));
  engine.Key(65477);
  const bool toggledBack = engine.CommitEnglish(target);
  check("turning learning back on does not revive an old action",
    !toggledBack && unchanged("pingguo"));

  fresh("pingguoyinhang");
  const auto partialPage = engine.Read();
  size_t partialIndex = partialPage.candidates.size();
  for (size_t i = 0; i < partialPage.candidates.size(); ++i)
    if (partialPage.candidates[i].text == "苹果") partialIndex = i;
  const auto partial = engine.PrepareEnglish(partialIndex);
  const bool partialAccepted = engine.CommitEnglish(partial);
  check("partial candidate retains its definition but cannot drop remaining pinyin",
    partial.reason == "partial-composition" && partial.english == "apple" &&
    !partialAccepted && unchanged("pingguoyinhang"));
  engine.Key(32); engine.Key(32);
  check("Chinese segmented input still completes after a rejected menu action",
    engine.Read().commit == "苹果银行");

  fresh("pingguo"); target = engine.PrepareEnglish(0); engine.Key(65361);
  const bool movedCaret = engine.CommitEnglish(target);
  const auto caretTarget = engine.PrepareEnglish(0);
  check("caret movement invalidates the action and prevents partial English",
    !movedCaret && caretTarget.reason == "partial-composition" && unchanged("pingguo"));

  fresh("zhangxiaoming"); const auto missing = engine.PrepareEnglish(0);
  const bool missingAccepted = engine.CommitEnglish(missing);
  check("missing definition remains unavailable without changing Chinese input",
    missing.reason == "no-definition" && missing.english.empty() &&
    !missingAccepted && unchanged("zhangxiaoming"));

  fresh("pingguo"); target = engine.PrepareEnglish(0); engine.InvalidateActions();
  const bool lostFocus = engine.CommitEnglish(target);
  check("focus invalidation rejects the old menu without committing elsewhere",
    !lostFocus && unchanged("pingguo"));

  fresh("pingguo"); target = engine.PrepareEnglish(0); fresh("pingguo");
  const bool previousSession = engine.CommitEnglish(target);
  check("new real Rime session rejects an identical previous-session target",
    !previousSession && unchanged("pingguo"));

  fresh("pingguo"); target = engine.PrepareEnglish(0); target.english = "stale display text";
  const bool forgedText = engine.CommitEnglish(target);
  check("cached or edited display text cannot become committed English",
    !forgedText && unchanged("pingguo"));

  fresh("pingguo"); const auto invalid = engine.PrepareEnglish(9999);
  const bool invalidAccepted = engine.CommitEnglish(invalid);
  check("out-of-range candidate target is harmless", !invalidAccepted && unchanged("pingguo"));

  fresh("pingguo"); engine.Key(32); engine.PrepareEnglish(0);
  const auto pending = engine.Read();
  check("opening an empty menu does not consume pending Chinese commit",
    pending.commit == "苹果" && pending.input.empty());

  fresh("zhishichanquan"); target = engine.PrepareEnglish(0);
  const bool longAccepted = engine.CommitEnglish(target);
  const auto longCommit = engine.Read();
  check("menu action commits the complete long definition",
    target.english == "intellectual property rights" && longAccepted &&
    longCommit.commit == target.english && longCommit.input.empty());

  fresh("pingguo"); engine.Key(0);
  check("zero key without a private request cannot submit English", unchanged("pingguo"));

  report << "],\"passed\":" << (all ? "true" : "false") << "}\n";
  return all ? 0 : 1;
}
