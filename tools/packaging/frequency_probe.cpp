// Real product IPC regression. Runs only with an explicit developer data root.
#include "stdafx.h"
#include <study/windows/ProductRuntime.h>
#include <study/windows/UiPreferences.h>
#include <study/windows/EnglishMenu.h>
#include <study/windows/WeaselResponse.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>

#include "ipc_probe.h"

int wmain(int argc, wchar_t** argv) {
  if (argc != 3) return 2;
  Checks checks{argv[1]};
  try {
    using namespace study;
    checks.Check("frequency probe requires isolated product data", ProductPipeName().find(L"-dev-") != std::wstring::npos);
    const std::wstring mode = argv[2];
    const auto settings = PreferencesPath();
    auto prefs = LoadPreferences(settings);
    Connection c;
    if (mode == L"restart") {
      checks.Check("paused learning survives service restart", !prefs.userLearning);
      checks.Check("learned candidate survives service restart", c.Find("shijian", L"实践").first == 1);
      checks.Check("forgotten candidate stays at its base rank after restart", c.Find("shishi", L"事实").first == 2);
      const auto found = c.Find("tongyi", L"同意");
      c.Choose(found.second);
      checks.Check("restarted service applies paused learning to new sessions", c.Find("tongyi", L"同意").first == found.first);
      c.client.ClearComposition();
      return 0;
    }
    if (mode == L"upgrade") {
      checks.Check("upgrade keeps an existing learned rank", c.Find("shijian", L"实践").first == 1);
      checks.Check("upgrade retains legacy display preferences", !prefs.learning && prefs.largeText && prefs.theme == Theme::Dark);
      checks.Check("legacy preferences default to enabled word learning", prefs.userLearning);
      const auto found = c.Find("shishi", L"事实");
      c.Choose(found.second);
      checks.Check("upgraded schema enables learning without a custom override", c.Find("shishi", L"事实").first == 1);
      c.client.ClearComposition();
      return 0;
    }
    if (mode != L"exercise") return 2;

    prefs = {};
    checks.Check("default word learning is independent of English display", prefs.userLearning && prefs.learning);
    checks.Check("word learning preference is saved", SavePreferences(settings, prefs));
    auto found = c.Find("shishi", L"事实");
    const auto baseRank = found.first;
    checks.Check("fixture starts with a nonleading homophone", baseRank == 2);

    // The normal mouse route must preserve the original Rime candidate.
    c.Choose(found.second);
    checks.Check("mouse selection commits the intended Chinese word", c.response->commit == L"事实");
    checks.Check("mouse selection learns through annotation shadows", c.Find("shishi", L"事实").first == 1);

    auto forget = [&] {
      const auto target = c.Find("shishi", L"事实");
      if (!c.Action(Action::Inspect, target.second)) throw std::runtime_error("Inspect failed");
      const auto before = c.response->context.preedit.str;
      const ActionRequest ticket{Action::ForgetWord, c.response->action.stamp, target.second, false};
      const bool forgotten = c.client.StudyAction(ticket);
      c.Read();
      checks.Check("forgetting preserves composition and does not commit text", forgotten &&
          c.response->action.reason == "word-forgotten" && c.response->status.composing &&
          c.response->commit.empty() && c.response->context.preedit.str == before);
      const bool repeated = c.client.StudyAction(ticket);
      c.Read();
      checks.Check("a repeated forget ticket is rejected without a commit", !repeated && c.response->commit.empty());
      checks.Check("forgetting restores the built-in dictionary rank", c.Find("shishi", L"事实").first == baseRank);
    };
    forget();

    found = c.Find("shishi", L"事实");
    c.Key('1' + found.second);
    checks.Check("number key selects and learns the word", c.response->commit == L"事实" && c.Find("shishi", L"事实").first == 1);
    forget();
    found = c.Find("shishi", L"事实");
    c.client.HighlightCandidateOnCurrentPage(found.second); c.Read();
    c.Key(' ');
    checks.Check("space selects and learns the highlighted word", c.response->commit == L"事实" && c.Find("shishi", L"事实").first == 1);

    // Change the file while a composition already exists: the service itself
    // must honor it even when the frontend submits a mouse selection next.
    const auto pending = c.Find("shijian", L"实践");
    prefs.userLearning = false;
    checks.Check("pausing learning round-trips without changing English", SavePreferences(settings, prefs) && LoadPreferences(settings).learning && !LoadPreferences(settings).userLearning);
    c.Choose(pending.second);
    checks.Check("pause saved during composition applies to the next mouse click", c.response->commit == L"实践" && c.Find("shijian", L"实践").first == pending.first);
    checks.Check("pausing keeps previously learned ranking", c.Find("shishi", L"事实").first == 1);
    forget();
    found = c.Find("shishi", L"事实"); c.Choose(found.second);
    checks.Check("paused mouse selection commits without relearning", c.response->commit == L"事实" && c.Find("shishi", L"事实").first == baseRank);
    found = c.Find("shishi", L"事实"); c.Key('1' + found.second);
    checks.Check("paused number selection does not relearn", c.Find("shishi", L"事实").first == baseRank);
    found = c.Find("shishi", L"事实");
    c.client.HighlightCandidateOnCurrentPage(found.second); c.Read(); c.Key(' ');
    checks.Check("paused space selection does not relearn", c.Find("shishi", L"事实").first == baseRank);
    found = c.Find("shishi", L"事实");
    c.client.HighlightCandidateOnCurrentPage(found.second); c.Read();
    c.client.CommitComposition(); c.Key(0);
    checks.Check("paused explicit composition commit does not relearn", c.response->commit == L"事实" && c.Find("shishi", L"事实").first == baseRank);

    // Annotation/English learning is a separate switch and must not train the
    // Chinese candidate that merely supplied an English meaning.
    prefs.userLearning = true; SavePreferences(settings, prefs);
    found = c.Find("tongyi", L"同意");
    const auto englishBase = found.first;
    checks.Check("English-only fixture is not already first", englishBase > 1);
    c.Action(Action::Inspect, found.second);
    const auto english = c.response->action.english;
    checks.Check("English inspection has a complete dictionary value", !english.empty());
    const bool englishCommitted = c.Action(Action::CommitEnglish, found.second);
    checks.Check("English action submits a translation without learning Chinese", englishCommitted &&
        !c.response->commit.empty() && c.response->commit != L"同意" && c.Find("tongyi", L"同意").first == englishBase);
    c.Action(Action::SetLearning, 0, false);
    found = c.Find("shijian", L"实践");
    c.Choose(found.second);
    checks.Check("Chinese learning works with English mode disabled", c.Find("shijian", L"实践").first == 1 && !c.response->action.learning);
    checks.Check("English-off learned candidates have no annotation", std::all_of(
        c.response->context.cinfo.comments.begin(), c.response->context.cinfo.comments.end(),
        [](const weasel::Text& text) { return text.str.empty(); }));

    // An old candidate ticket must not affect the next word/menu.
    c.Action(Action::Inspect, 0);
    const ActionRequest stale{Action::ForgetWord, c.response->action.stamp, 0, false};
    c.Type("nihao");
    const bool staleAccepted = c.client.StudyAction(stale); c.Read();
    checks.Check("changed composition rejects a stale forget target", !staleAccepted && c.response->commit.empty());
    checks.Check("stale forget leaves the learned word intact", c.Find("shijian", L"实践").first == 1);

    // A second IPC session shares the user's dictionary but owns its own
    // candidate tickets. A forget operation cannot consume a pending commit.
    Connection other;
    checks.Check("concurrent sessions share learned ranking", other.Find("shijian", L"实践").first == 1);
    other.Type("nihao");
    other.client.CommitComposition();
    const ActionRequest noTarget{Action::ForgetWord, other.response->action.stamp, 0, false};
    const bool noTargetAccepted = other.client.StudyAction(noTarget); other.Read();
    checks.Check("forget without inspection is rejected without consuming a pending commit", !noTargetAccepted && other.response->commit.empty());
    other.Key(0);
    checks.Check("the application still receives its pending Chinese commit", other.response->commit == L"你好");

    EnglishTarget target; target.chinese = "事实"; target.reason = "no-definition";
    EnglishMenuOptions options; options.forget = true; options.learning = false;
    HMENU menu = CreateEnglishMenu(target, options);
    checks.Check("forget menu remains available without English", menu &&
        !(GetMenuState(menu, kForgetWord, MF_BYCOMMAND) & MF_GRAYED) &&
        (GetMenuState(menu, kInputEnglish, MF_BYCOMMAND) & MF_GRAYED));
    DestroyMenu(menu);
    target.chinese.clear(); menu = CreateEnglishMenu(target, options);
    checks.Check("forget menu is disabled without a candidate", (GetMenuState(menu, kForgetWord, MF_BYCOMMAND) & MF_GRAYED) != 0);
    DestroyMenu(menu);

    prefs.userLearning = false;
    checks.Check("final pause is persisted for restart verification", SavePreferences(settings, prefs));
    c.client.ClearComposition();
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << std::endl;
    return 1;
  }
}
