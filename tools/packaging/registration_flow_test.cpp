#include <study/windows/ProductRegistrationFlow.h>
#include <algorithm>
#include <array>
#include <iostream>
#include <string>
#include <vector>

struct MemoryRegistration {
  bool ownedClass = false, profile = false;
  std::array<bool, 4> categories{};
  std::string failAdd, failRemove;
  bool failAfterChange = true;
  std::vector<std::string> calls;
  std::size_t CategoryCount() const { return categories.size(); }
  HRESULT Write(const std::string& name, bool& value, bool next, const std::string& failure) {
    calls.push_back(name);
    if (name != failure || failAfterChange) value = next;
    return name == failure ? E_ACCESSDENIED : S_OK;
  }
  HRESULT CreateClass(bool& created) {
    created = false;
    if (ownedClass) return HRESULT_FROM_WIN32(ERROR_ALREADY_EXISTS);
    const HRESULT result = Write("class", ownedClass, true, failAdd);
    created = ownedClass;
    return result;
  }
  HRESULT AddProfile() { return Write("profile", profile, true, failAdd); }
  HRESULT AddCategory(std::size_t i) { return Write("category" + std::to_string(i), categories[i], true, failAdd); }
  HRESULT RemoveCategory(std::size_t i) { return Remove("category" + std::to_string(i), categories[i]); }
  HRESULT RemoveProfile() { return Remove("profile", profile); }
  HRESULT DeleteClass() {
    if (profile || std::any_of(categories.begin(), categories.end(), [](bool item) { return item; }))
      return E_UNEXPECTED;
    return Remove("class", ownedClass);
  }
  HRESULT Remove(const std::string& name, bool& value) {
    calls.push_back("remove-" + name);
    if (name == failRemove) return E_ACCESSDENIED;
    value = false;
    return S_OK;
  }
  bool Empty() const {
    return !ownedClass && !profile && std::none_of(categories.begin(), categories.end(), [](bool item) { return item; });
  }
};

int main() {
  std::vector<std::pair<std::string, bool>> checks;
  auto check = [&](std::string name, bool passed) { checks.emplace_back(std::move(name), passed); };
  MemoryRegistration success;
  check("complete registration creates all owned records", SUCCEEDED(study::AddOwnedRegistration(success)) &&
      success.ownedClass && success.profile && std::all_of(success.categories.begin(), success.categories.end(), [](bool value) { return value; }));
  check("duplicate registration cannot claim success or erase the owner", FAILED(study::AddOwnedRegistration(success)) && success.ownedClass && success.profile);
  check("complete removal clears references before the owner", SUCCEEDED(study::RemoveOwnedRegistration(success)) && success.Empty() && success.calls.back() == "remove-class");
  check("removal tolerates already absent records", SUCCEEDED(study::RemoveOwnedRegistration(success)) && success.Empty());
  for (const auto& failure : {"class", "profile", "category0", "category1", "category2", "category3"}) {
    for (bool after : {false, true}) {
      MemoryRegistration state;
      state.failAdd = failure;
      state.failAfterChange = after;
      check(std::string("failed ") + failure + (after ? " after partial write rolls back" : " before write rolls back"),
          FAILED(study::AddOwnedRegistration(state)) && state.Empty());
    }
  }
  for (const auto& failure : {"profile", "category0", "category1", "category2", "category3", "class"}) {
    MemoryRegistration state;
    state.failAdd = "category3";
    state.failRemove = failure;
    const HRESULT result = study::AddOwnedRegistration(state);
    check(std::string("rollback failure at ") + failure + " retains its owner", FAILED(result) && state.ownedClass);
    state.failRemove.clear();
    check(std::string("retry after failed ") + failure + " completes cleanup", SUCCEEDED(study::RemoveOwnedRegistration(state)) && state.Empty());
  }
  const auto passed = std::count_if(checks.begin(), checks.end(), [](const auto& value) { return value.second; });
  std::cout << "{\"passed\":" << passed << ",\"total\":" << checks.size() << ",\"checks\":[";
  for (std::size_t i = 0; i < checks.size(); ++i) {
    if (i) std::cout << ',';
    std::cout << "{\"name\":\"" << checks[i].first << "\",\"passed\":" << (checks[i].second ? "true" : "false") << '}';
  }
  std::cout << "]}" << std::endl;
  return passed == checks.size() ? 0 : 1;
}
