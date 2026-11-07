#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <atlbase.h>
#include <WeaselIPC.h>
#include <WeaselUI.h>
#include <ProductIdentity.h>
#include "ProductRuntime.h"
#include <iostream>
#include <thread>

CComModule _Module;
weasel::RequestHandler* CreateProductRimeHandler(weasel::UI* ui);

int wmain(int argc, wchar_t** argv) {
  try {
    const std::wstring action = argc == 2 ? argv[1] : L"";
    if (action == L"--identity") {
      std::cout << study::kProductIdentityJson << std::endl;
      return 0;
    }
    if (action == L"--ensure-running") return study::EnsureProductService() ? 0 : 3;
    if (action == L"--stop") {
      const auto name = study::ProductStopEvent();
      HANDLE event = OpenEventW(EVENT_MODIFY_STATE, FALSE, name.c_str());
      if (!event) return GetLastError() == ERROR_FILE_NOT_FOUND ? 0 : 2;
      const BOOL ok = SetEvent(event);
      CloseHandle(event);
      if (!ok) return 2;
      HANDLE mutex = OpenMutexW(SYNCHRONIZE | MUTEX_MODIFY_STATE, FALSE, study::ProductMutexName().c_str());
      if (!mutex) return 0;
      const DWORD stopped = WaitForSingleObject(mutex, 10000);
      if (stopped == WAIT_OBJECT_0 || stopped == WAIT_ABANDONED) ReleaseMutex(mutex);
      CloseHandle(mutex);
      return stopped == WAIT_OBJECT_0 || stopped == WAIT_ABANDONED ? 0 : 4;
    }
    if (action != L"--run" && action != L"--prepare-data") {
      std::cerr << "Usage: StudyIME.Service.exe --identity | --prepare-data | --run | --stop\n";
      return 2;
    }
    const auto mutexName = study::ProductMutexName();
    HANDLE mutex = CreateMutexW(nullptr, TRUE, mutexName.c_str());
    if (!mutex) return 2;
    if (GetLastError() == ERROR_ALREADY_EXISTS) { CloseHandle(mutex); return 0; }
    study::PrepareProductUserData();
    _Module.Init(nullptr, GetModuleHandleW(nullptr));
    int result = 0;
    {
      weasel::UI ui;
      std::unique_ptr<weasel::RequestHandler> handler(CreateProductRimeHandler(&ui));
      handler->Initialize();
      if (action == L"--run") {
        const auto eventName = study::ProductStopEvent();
        HANDLE stop = CreateEventW(nullptr, TRUE, FALSE, eventName.c_str());
        if (!stop) throw std::runtime_error("Cannot create StudyIME shutdown event");
        const DWORD thread = GetCurrentThreadId();
        MSG message{};
        PeekMessageW(&message, nullptr, 0, 0, PM_NOREMOVE);
        weasel::Server server;
        server.SetRequestHandler(handler.get());
        if (!server.Start()) { CloseHandle(stop); return 3; }
        std::thread monitor([stop, thread] {
          WaitForSingleObject(stop, INFINITE);
          PostThreadMessageW(thread, WM_QUIT, 0, 0);
        });
        std::cout << "ready" << std::endl;
        result = server.Run();
        SetEvent(stop);
        monitor.join();
        CloseHandle(stop);
      }
      handler->Finalize();
    }
    _Module.Term();
    ReleaseMutex(mutex);
    CloseHandle(mutex);
    return result;
  } catch (const std::exception& error) {
    std::cerr << error.what() << std::endl;
    return 2;
  }
}
