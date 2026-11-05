#pragma once

#include <windows.h>
#include <condition_variable>
#include <deque>
#include <functional>
#include <memory>
#include <mutex>

namespace study {

// The owner pumps DispatchOne from a private window message. Messages carry no
// pointers. Workers retain their job until completion/cancellation; no queue
// lock is held while executing Rime, touching a window, or waiting for a reply.
class WindowDispatcher {
 public:
  static constexpr UINT kMessage = WM_APP + 0x347;
  void Open(HWND window);
  bool Invoke(std::function<DWORD()> work, DWORD& result);
  void DispatchOne();
  void Close();

 private:
  struct Job {
    std::function<DWORD()> work;
    std::mutex mutex;
    std::condition_variable ready;
    bool done = false;
    bool succeeded = false;
    DWORD result = 0;
    void Complete(bool success, DWORD value);
  };
  std::mutex mutex_;
  std::deque<std::shared_ptr<Job>> queue_;
  HWND window_ = nullptr;
  DWORD owner_ = 0;
  bool wake_pending_ = false;
  bool executing_ = false; // owner thread only; prevents nested message loops
};

}  // namespace study
