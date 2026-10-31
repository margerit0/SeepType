// Headless host for the real Weasel IPC server and RimeWithWeasel handler.
// No TSF registration, input injection, tray application or candidate windows.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <atlbase.h>
#include <wtl/atlapp.h>
#include <WeaselIPC.h>
#include <WeaselUI.h>
#include <iostream>

CAppModule _Module;
weasel::RequestHandler* CreateIsolatedRimeHandler(weasel::UI* ui);

int wmain() {
  try {
    // Validate isolation before creating any server or engine object.
    weasel::GetPipeName();
    _Module.Init(nullptr, GetModuleHandleW(nullptr));
    int result;
    {
      weasel::UI ui;
      std::unique_ptr<weasel::RequestHandler> handler(CreateIsolatedRimeHandler(&ui));
      handler->Initialize();
      weasel::Server server;
      server.SetRequestHandler(handler.get());
      if (!server.Start()) return 3;
      std::cout << "ready" << std::endl;
      result = server.Run();
      handler->Finalize();
    }
    _Module.Term();
    return result;
  } catch (const std::exception& error) {
    std::cerr << error.what() << std::endl;
    return 2;
  }
}
