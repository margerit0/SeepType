// Actual Windows message queues and patched Weasel transport; no TSF install.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <atlbase.h>
#include <wtl/atlapp.h>
#include <WeaselIPC.h>
#include <PipeChannel.h>
#include <study/windows/WindowDispatcher.h>
#include <atomic>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <thread>
#include <vector>

CAppModule _Module;
using Channel = weasel::PipeChannel<weasel::PipeMessage>;

struct Report {
  std::vector<std::pair<std::string, bool>> checks;
  void Check(const char* name, bool ok) {
    checks.emplace_back(name, ok);
    std::cout << (ok ? "PASS " : "FAIL ") << name << std::endl;
  }
  bool Save(const wchar_t* path) {
    bool passed = true;
    std::ofstream out{std::filesystem::path(path)};
    out << "{\"checks\":[";
    for (size_t i = 0; i < checks.size(); ++i) {
      if (i) out << ',';
      out << "{\"name\":\"" << checks[i].first << "\",\"passed\":"
          << (checks[i].second ? "true" : "false") << '}';
      passed &= checks[i].second;
    }
    out << "],\"passed\":" << (passed ? "true" : "false") << "}\n";
    return passed;
  }
};

static void Pump() {
  MSG message;
  while (PeekMessageW(&message, nullptr, 0, 0, PM_REMOVE)) {
    TranslateMessage(&message);
    DispatchMessageW(&message);
  }
}

static void UnitChecks(Report& report) {
  WNDCLASSW cls{};
  cls.hInstance = GetModuleHandleW(nullptr);
  cls.lpszClassName = L"StudyDispatcherTest";
  cls.lpfnWndProc = [](HWND window, UINT message, WPARAM wp, LPARAM lp) -> LRESULT {
    if (message == study::WindowDispatcher::kMessage) {
      auto dispatcher = reinterpret_cast<study::WindowDispatcher*>(GetWindowLongPtrW(window, GWLP_USERDATA));
      if (dispatcher) dispatcher->DispatchOne();
      return 0;
    }
    return DefWindowProcW(window, message, wp, lp);
  };
  RegisterClassW(&cls);
  HWND window = CreateWindowW(cls.lpszClassName, L"", 0, 0, 0, 0, 0, HWND_MESSAGE, nullptr, cls.hInstance, nullptr);
  study::WindowDispatcher dispatcher;
  SetWindowLongPtrW(window, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(&dispatcher));
  dispatcher.Open(window);
  DWORD result = 0;
  report.Check("owner cannot synchronously wait on its own dispatcher",
               !dispatcher.Invoke([] { return 1; }, result));

  std::atomic<int> done{0};
  bool first = false, second = false, nested = false;
  bool inFirst = false;
  std::thread worker2;
  std::thread worker([&] {
    DWORD value = 0;
    first = dispatcher.Invoke([&] {
      inFirst = true;
      worker2 = std::thread([&] {
        DWORD value = 0;
        second = dispatcher.Invoke([&] { nested = inFirst; return 43; }, value) && value == 43;
        ++done;
      });
      MSG queued;
      while (!PeekMessageW(&queued, window, study::WindowDispatcher::kMessage,
                            study::WindowDispatcher::kMessage, PM_NOREMOVE)) Sleep(1);
      // Dispatch the private message recursively. It must not execute the
      // second job until the current Rime-equivalent operation has returned.
      SendMessageW(window, study::WindowDispatcher::kMessage, 0, 0);
      Pump();
      inFirst = false;
      return 42;
    }, value) && value == 42;
    ++done;
  });
  MSG message;
  while (done != 2) { Pump(); Sleep(1); }
  worker.join(); worker2.join();
  report.Check("queued work completes on owner without nested dispatch", first && second && !nested);

  done = 0;
  bool caught = false;
  std::thread throwing([&] {
    DWORD value;
    caught = !dispatcher.Invoke([]() -> DWORD { throw 7; }, value);
    ++done;
  });
  while (!done) { Pump(); Sleep(1); }
  throwing.join();
  report.Check("handler exception releases the waiting transport worker", caught);

  Pump();
  std::atomic<int> cancelled{0}, ran{0};
  std::vector<std::thread> pending;
  for (int i = 0; i < 8; ++i) pending.emplace_back([&] {
    DWORD value;
    if (!dispatcher.Invoke([&] { ++ran; return 1; }, value)) ++cancelled;
  });
  while (!PeekMessageW(&message, window, study::WindowDispatcher::kMessage,
                        study::WindowDispatcher::kMessage, PM_NOREMOVE)) Sleep(1);
  dispatcher.Close();
  for (auto& thread : pending) thread.join();
  Pump(); // queued messages contain no pointers into cancelled jobs
  report.Check("close cancels queued requests without replay from old messages", cancelled == 8 && ran == 0);
  DestroyWindow(window);
}

struct Handler : weasel::RequestHandler {
  DWORD owner = GetCurrentThreadId();
  HWND window = nullptr;
  std::atomic<int> wrongThread{0}, requests{0}, finalized{0};
  DWORD next = 10;
  void Touch() {
    if (GetCurrentThreadId() != owner) ++wrongThread;
    ++requests;
    // This window call is synchronous by design, reproducing the dependency
    // which must be safe once handler and service window share their owner.
    SendMessageW(window, WM_NULL, 0, 0);
  }
  DWORD AddSession(LPWSTR, EatLine eat) override {
    Touch();
    std::wstring wire = L"session=" + std::to_wstring(++next) + L"\n.\n";
    eat(wire);
    return next;
  }
  DWORD FindSession(DWORD id) override { Touch(); return id; }
  void Finalize() override { ++finalized; }
  BOOL ProcessKeyEvent(weasel::KeyEvent key, DWORD id, EatLine eat) override {
    Touch();
    std::wstring wire = std::to_wstring(id) + L":" + std::to_wstring(key.keycode) + L"\n.\n";
    eat(wire);
    return TRUE;
  }
};

static bool Connect(Channel& channel) {
  for (int i = 0; i < 300; ++i) {
    if (channel.Connect()) return true;
    Sleep(5);
  }
  return false;
}

static DWORD Request(Channel& channel, UINT command, DWORD wp = 0, DWORD lp = 0) {
  weasel::PipeMessage message{static_cast<WEASEL_IPC_COMMAND>(command), wp, lp};
  return channel.Transact(message);
}

static HANDLE RawConnect() {
  for (int i = 0; i < 300; ++i) {
    HANDLE pipe = CreateFileW(weasel::GetPipeName().c_str(), GENERIC_READ | GENERIC_WRITE,
                             0, nullptr, OPEN_EXISTING, 0, nullptr);
    if (pipe != INVALID_HANDLE_VALUE) return pipe;
    Sleep(5);
  }
  throw 1;
}

int wmain(int argc, wchar_t** argv) {
  if (argc != 2) return 2;
  Report report;
  _Module.Init(nullptr, GetModuleHandleW(nullptr));
  UnitChecks(report);
  {
    Handler handler;
    weasel::Server server;
    server.SetRequestHandler(&handler);
    if (!server.Start()) return 3;
    handler.window = server.GetHWnd();
    PostMessageW(handler.window, WM_ENDSESSION, FALSE, 0);
    std::atomic<int> windowCommands{0};
    server.AddMenuHandler(321, [&] { handler.Touch(); ++windowCommands; return true; });
    bool clientsOK[2] = {true, true};
    std::atomic<bool> returned{false};
    std::thread controller([&] {
      std::vector<HANDLE> held;
      try {
        // Idle reader + writer whose second full response cannot fit until
        // read. Both remain connected while the server shuts down.
        held.push_back(RawConnect());
        held.push_back(RawConnect());
        weasel::PipeMessage start{WEASEL_IPC_START_SESSION, 0, 0};
        DWORD written;
        for (int i = 0; i < 4; ++i)
          if (!WriteFile(held.back(), &start, sizeof(start), &written, nullptr)) throw 2;
        DWORD available = 0;
        // Confirm the unread response occupies a complete pipe buffer and a
        // second response was generated before starting the healthy clients.
        for (int i = 0; i < 1000; ++i) {
          if (!PeekNamedPipe(held.back(), nullptr, 0, nullptr, &available, nullptr)) throw 6;
          if (available >= 65536 && handler.requests >= 2) break;
          Sleep(1);
        }
        if (available < 65536 || handler.requests < 2) throw 7;
        auto run = [&](int index) {
          try {
            Channel channel(weasel::GetPipeName());
            if (!Connect(channel)) throw 3;
            const DWORD id = Request(channel, WEASEL_IPC_START_SESSION);
            for (int n = 0; n < 100; ++n) {
              const DWORD key = index * 1000 + n;
              if (!Request(channel, WEASEL_IPC_PROCESS_KEY_EVENT, key, id)) throw 4;
              const std::wstring expected = std::to_wstring(id) + L":" + std::to_wstring(key) + L"\n.\n";
              channel.HandleResponseData(std::function<bool(LPWSTR, DWORD)>([&](LPWSTR data, DWORD) {
                clientsOK[index] &= expected == data;
                return true;
              }));
              PostMessageW(handler.window, WM_COMMAND, 321, 0);
            }
          } catch (...) { clientsOK[index] = false; }
        };
        std::thread a(run, 0), b(run, 1);
        a.join(); b.join();
        Channel channel(weasel::GetPipeName());
        if (!Connect(channel)) throw 5;
        Request(channel, WEASEL_IPC_SHUTDOWN_SERVER);
      } catch (...) {
        clientsOK[0] = false;
        PostMessageW(handler.window, WM_CLOSE, 0, 0);
      }
      // Keep hostile/idle clients open until Stop has returned. They cannot
      // make shutdown pass merely by closing their own end of the pipe.
      while (!returned) Sleep(1);
      for (HANDLE pipe : held) CloseHandle(pipe);
    });
    server.Run();
    returned = true;
    controller.join();
    report.Check("200 concurrent requests retain per-connection responses", clientsOK[0] && clientsOK[1]);
    report.Check("cancelled Windows end-session leaves the handler running", handler.finalized == 0 && clientsOK[0] && clientsOK[1]);
    report.Check("Rime-equivalent and window operations share the window owner", handler.requests >= 200 && handler.wrongThread == 0);
    report.Check("window commands progress alongside pipe work and slow readers", windowCommands > 0 && clientsOK[0] && clientsOK[1]);
    report.Check("shutdown joins blocked reader writer and listener threads", returned && clientsOK[0] && clientsOK[1]);
  }
  _Module.Term();
  return report.Save(argv[1]) ? 0 : 1;
}
