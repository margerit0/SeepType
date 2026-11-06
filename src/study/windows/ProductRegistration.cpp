#include "ProductRegistration.h"
#include "ProductRegistrationFlow.h"
#include <ProductIdentity.h>
#include <msctf.h>
#include <string>

namespace study {
namespace {
const GUID* const categories[] = {&GUID_TFCAT_TIP_KEYBOARD,
    &GUID_TFCAT_DISPLAYATTRIBUTEPROVIDER, &GUID_TFCAT_TIPCAP_UIELEMENTENABLED,
    &GUID_TFCAT_TIPCAP_INPUTMODECOMPARTMENT};
std::wstring ClassKey() {
  return std::wstring(L"Software\\Classes\\CLSID\\") + kTextServiceGuidText;
}
std::wstring ModulePath(HMODULE module) {
  wchar_t path[32768]{};
  const DWORD length = GetModuleFileNameW(module, path, 32768);
  return length && length < 32768 ? std::wstring(path, length) : std::wstring();
}
HRESULT SetString(HKEY key, const wchar_t* name, const std::wstring& value) {
  return HRESULT_FROM_WIN32(RegSetValueExW(key, name, 0, REG_SZ,
      reinterpret_cast<const BYTE*>(value.c_str()), static_cast<DWORD>((value.size() + 1) * sizeof(wchar_t))));
}
HRESULT CheckOwner(const std::wstring& module, bool& exists) {
  exists = false;
  wchar_t product[128]{};
  DWORD productBytes = sizeof(product);
  const LSTATUS marker = RegGetValueW(HKEY_LOCAL_MACHINE, ClassKey().c_str(), L"StudyIMEProductId",
      RRF_RT_REG_SZ | RRF_SUBKEY_WOW6464KEY, nullptr, product, &productBytes);
  const auto key = ClassKey() + L"\\InprocServer32";
  wchar_t path[32768]{};
  DWORD bytes = sizeof(path);
  const LSTATUS result = RegGetValueW(HKEY_LOCAL_MACHINE, key.c_str(), nullptr,
      RRF_RT_REG_SZ | RRF_SUBKEY_WOW6464KEY, nullptr, path, &bytes);
  if (result == ERROR_FILE_NOT_FOUND || result == ERROR_PATH_NOT_FOUND) {
    if (marker == ERROR_SUCCESS) {
      if (std::wstring(product) != kProductId) return HRESULT_FROM_WIN32(ERROR_ALREADY_EXISTS);
      exists = true;
    } else if (marker != ERROR_FILE_NOT_FOUND && marker != ERROR_PATH_NOT_FOUND) {
      return HRESULT_FROM_WIN32(marker);
    }
    return S_OK;
  }
  if (result != ERROR_SUCCESS) return HRESULT_FROM_WIN32(result);
  exists = true;
  return marker == ERROR_SUCCESS && std::wstring(product) == kProductId && _wcsicmp(module.c_str(), path) == 0
      ? S_OK : HRESULT_FROM_WIN32(ERROR_ALREADY_EXISTS);
}
HRESULT DeleteClassKey() {
  HKEY classes = nullptr;
  LSTATUS result = RegOpenKeyExW(HKEY_LOCAL_MACHINE, L"Software\\Classes", 0,
      KEY_READ | KEY_WRITE | DELETE | KEY_WOW64_64KEY, &classes);
  if (result != ERROR_SUCCESS) return HRESULT_FROM_WIN32(result);
  const auto relative = std::wstring(L"CLSID\\") + kTextServiceGuidText;
  result = RegDeleteTreeW(classes, relative.c_str());
  RegCloseKey(classes);
  return result == ERROR_FILE_NOT_FOUND ? S_OK : HRESULT_FROM_WIN32(result);
}
struct Apartment {
  HRESULT result = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
  ~Apartment() { if (SUCCEEDED(result)) CoUninitialize(); }
  bool ok() const { return SUCCEEDED(result) || result == RPC_E_CHANGED_MODE; }
};
template<typename T> struct Com {
  T* value = nullptr;
  ~Com() { if (value) value->Release(); }
  T* operator->() const { return value; }
};
struct WindowsRegistration {
  const std::wstring& path;
  ITfInputProcessorProfileMgr* profiles;
  ITfCategoryMgr* category;
  std::size_t CategoryCount() const { return sizeof(categories) / sizeof(categories[0]); }
  HRESULT CreateClass(bool& created) {
    created = false;
    HKEY key = nullptr, server = nullptr;
    DWORD disposition = 0;
    HRESULT result = HRESULT_FROM_WIN32(RegCreateKeyExW(HKEY_LOCAL_MACHINE, ClassKey().c_str(),
        0, nullptr, 0, KEY_WRITE | KEY_WOW64_64KEY, nullptr, &key, &disposition));
    if (FAILED(result)) return result;
    if (disposition != REG_CREATED_NEW_KEY) {
      RegCloseKey(key);
      return HRESULT_FROM_WIN32(ERROR_ALREADY_EXISTS);
    }
    created = true;
    result = SetString(key, L"StudyIMEProductId", kProductId);
    if (SUCCEEDED(result)) result = SetString(key, nullptr, kProductName);
    if (SUCCEEDED(result)) result = HRESULT_FROM_WIN32(RegCreateKeyExW(key, L"InprocServer32",
        0, nullptr, 0, KEY_WRITE | KEY_WOW64_64KEY, nullptr, &server, nullptr));
    if (SUCCEEDED(result)) result = SetString(server, nullptr, path);
    if (SUCCEEDED(result)) result = SetString(server, L"ThreadingModel", L"Apartment");
    if (server) RegCloseKey(server);
    RegCloseKey(key);
    return result;
  }
  HRESULT AddProfile() {
    // Description/path lengths are WCHAR counts. Never activate this profile
    // or change the user's default input method.
    return profiles->RegisterProfile(kTextServiceGuid, kProductLanguageId, kProfileGuid,
        kProductName, static_cast<ULONG>(wcslen(kProductName)), path.c_str(),
        static_cast<ULONG>(path.size()), 0, nullptr, 0, TRUE, 0);
  }
  HRESULT AddCategory(std::size_t index) {
    return category->RegisterCategory(kTextServiceGuid, *categories[index], kTextServiceGuid);
  }
  HRESULT RemoveProfile() {
    Com<IEnumTfInputProcessorProfiles> items;
    HRESULT result = profiles->EnumProfiles(kProductLanguageId, &items.value);
    if (FAILED(result)) return result;
    if (!items.value) return E_UNEXPECTED;
    TF_INPUTPROCESSORPROFILE item{};
    ULONG fetched = 0;
    while ((result = items->Next(1, &item, &fetched)) == S_OK) {
      if (fetched != 1) return E_UNEXPECTED;
      if (item.dwProfileType == TF_PROFILETYPE_INPUTPROCESSOR &&
          IsEqualGUID(item.clsid, kTextServiceGuid) && IsEqualGUID(item.guidProfile, kProfileGuid))
        return profiles->UnregisterProfile(kTextServiceGuid, kProductLanguageId, kProfileGuid, 0);
    }
    return result == S_FALSE ? S_OK : result;
  }
  HRESULT RemoveCategory(std::size_t index) {
    Com<IEnumGUID> items;
    HRESULT result = category->EnumItemsInCategory(*categories[index], &items.value);
    if (FAILED(result)) return result;
    if (!items.value) return E_UNEXPECTED;
    GUID item{};
    ULONG fetched = 0;
    while ((result = items->Next(1, &item, &fetched)) == S_OK) {
      if (fetched != 1) return E_UNEXPECTED;
      if (IsEqualGUID(item, kTextServiceGuid))
        return category->UnregisterCategory(kTextServiceGuid, *categories[index], kTextServiceGuid);
    }
    return result == S_FALSE ? S_OK : result;
  }
  HRESULT DeleteClass() { return DeleteClassKey(); }
};
}
HRESULT RegisterProductModule(HMODULE module) {
  const auto path = ModulePath(module);
  if (path.empty()) return E_FAIL;
  bool exists = false;
  HRESULT result = CheckOwner(path, exists);
  if (FAILED(result)) return result;
  if (exists) return HRESULT_FROM_WIN32(ERROR_ALREADY_EXISTS);
  Apartment apartment;
  if (!apartment.ok()) return apartment.result;
  Com<ITfInputProcessorProfileMgr> profiles;
  Com<ITfCategoryMgr> category;
  result = CoCreateInstance(CLSID_TF_InputProcessorProfiles, nullptr, CLSCTX_INPROC_SERVER,
      IID_ITfInputProcessorProfileMgr, reinterpret_cast<void**>(&profiles.value));
  if (FAILED(result)) return result;
  result = CoCreateInstance(CLSID_TF_CategoryMgr, nullptr, CLSCTX_INPROC_SERVER,
      IID_ITfCategoryMgr, reinterpret_cast<void**>(&category.value));
  if (FAILED(result)) return result;
  WindowsRegistration operations{path, profiles.value, category.value};
  return AddOwnedRegistration(operations);
}
HRESULT UnregisterProductModule(HMODULE module) {
  const auto path = ModulePath(module);
  if (path.empty()) return E_FAIL;
  bool exists = false;
  HRESULT result = CheckOwner(path, exists);
  if (FAILED(result) || !exists) return FAILED(result) ? result : S_FALSE;
  Apartment apartment;
  if (!apartment.ok()) return apartment.result;
  Com<ITfInputProcessorProfileMgr> profiles;
  Com<ITfCategoryMgr> category;
  result = CoCreateInstance(CLSID_TF_InputProcessorProfiles, nullptr, CLSCTX_INPROC_SERVER,
      IID_ITfInputProcessorProfileMgr, reinterpret_cast<void**>(&profiles.value));
  if (FAILED(result)) return result;
  result = CoCreateInstance(CLSID_TF_CategoryMgr, nullptr, CLSCTX_INPROC_SERVER,
      IID_ITfCategoryMgr, reinterpret_cast<void**>(&category.value));
  if (FAILED(result)) return result;
  WindowsRegistration operations{path, profiles.value, category.value};
  return RemoveOwnedRegistration(operations);
}
}
