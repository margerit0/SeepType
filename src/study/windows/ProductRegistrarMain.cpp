#include <windows.h>
#include <ProductIdentity.h>
#include "ProductRuntime.h"
#include <iostream>
#include <string>

int wmain(int argc, wchar_t** argv) {
  if (argc == 1 || (argc == 2 && std::wstring(argv[1]) == L"--plan")) {
    std::cout << study::kProductIdentityJson << std::endl;
    return 0;
  }
  const std::wstring action = argc > 1 ? argv[1] : L"";
  if (action != L"--inspect" && action != L"--register" && action != L"--unregister") return 2;
  const bool inspect = action == L"--inspect";
  if ((inspect && argc != 2) || (!inspect && (argc != 3 || std::wstring(argv[2]) != L"--apply"))) {
    std::cerr << "Registration requires an explicit --apply; default --plan does not change the system.\n";
    return 2;
  }
  try {
    const auto file = study::ProductRoot() / L"bin/StudyIME.TSF.x64.dll";
    HMODULE module = LoadLibraryExW(file.c_str(), nullptr,
        LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_SYSTEM32);
    if (!module) { std::cerr << "Cannot load the packaged TSF module.\n"; return 3; }
    using Identity = const char* (WINAPI*)();
    const auto identity = reinterpret_cast<Identity>(GetProcAddress(module, "StudyProductIdentity"));
    if (!identity || std::string(identity()) != study::kProductIdentityJson) {
      FreeLibrary(module); return 4;
    }
    if (inspect) {
      using Factory = HRESULT (WINAPI*)(REFCLSID, REFIID, void**);
      const auto factory = reinterpret_cast<Factory>(GetProcAddress(module, "DllGetClassObject"));
      IClassFactory* object = nullptr;
      HRESULT accepted = factory ? factory(study::kTextServiceGuid, IID_IClassFactory,
          reinterpret_cast<void**>(&object)) : E_FAIL;
      if (object) object->Release();
      object = nullptr;
      HRESULT rejected = factory ? factory(CLSID_NULL, IID_IClassFactory,
          reinterpret_cast<void**>(&object)) : E_FAIL;
      if (object) object->Release();
      const bool ok = SUCCEEDED(accepted) && rejected == CLASS_E_CLASSNOTAVAILABLE &&
          GetProcAddress(module, "DllRegisterServer") && GetProcAddress(module, "DllUnregisterServer");
      std::cout << "{\"identity_matches\":true,\"factory_guid_isolated\":" << (ok ? "true" : "false")
          << ",\"registration_executed\":false}" << std::endl;
      FreeLibrary(module);
      return ok ? 0 : 5;
    }
    using Register = HRESULT (WINAPI*)();
    const auto operation = reinterpret_cast<Register>(GetProcAddress(module,
        action == L"--register" ? "DllRegisterServer" : "DllUnregisterServer"));
    const HRESULT result = operation ? operation() : E_NOINTERFACE;
    FreeLibrary(module);
    if (FAILED(result)) {
      std::cerr << "StudyIME registration operation failed: 0x" << std::hex << result << std::endl;
      return 6;
    }
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << std::endl;
    return 2;
  }
}
