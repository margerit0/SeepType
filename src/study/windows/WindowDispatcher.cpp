#include "WindowDispatcher.h"
#include <cassert>

namespace study {

void WindowDispatcher::Job::Complete(bool success, DWORD value) {
  {
    std::lock_guard<std::mutex> lock(mutex);
    succeeded = success;
    result = value;
    done = true;
  }
  ready.notify_one();
}

void WindowDispatcher::Open(HWND window) {
  std::lock_guard<std::mutex> lock(mutex_);
  assert(!window_ && queue_.empty());
  owner_ = GetWindowThreadProcessId(window, nullptr);
  assert(owner_ == GetCurrentThreadId());
  window_ = window;
  wake_pending_ = false;
}

bool WindowDispatcher::Invoke(std::function<DWORD()> work, DWORD& result) {
  auto job = std::make_shared<Job>();
  job->work = std::move(work);
  {
    std::lock_guard<std::mutex> lock(mutex_);
    // Calling synchronously from the owner would block its message pump.
    if (!window_ || owner_ == GetCurrentThreadId() || queue_.size() >= 64)
      return false;
    queue_.push_back(job);
    if (!wake_pending_) {
      if (!PostMessageW(window_, kMessage, 0, 0)) {
        queue_.pop_back();
        return false;
      }
      wake_pending_ = true;
    }
  }
  std::unique_lock<std::mutex> lock(job->mutex);
  job->ready.wait(lock, [&] { return job->done; });
  result = job->result;
  return job->succeeded;
}

void WindowDispatcher::DispatchOne() {
  assert(owner_ == GetCurrentThreadId());
  std::shared_ptr<Job> job;
  {
    std::lock_guard<std::mutex> lock(mutex_);
    wake_pending_ = false;
    if (executing_) return;
    if (!window_ || queue_.empty()) return;
    job = queue_.front();
    queue_.pop_front();
  }
  executing_ = true;
  try {
    job->Complete(true, job->work());
  } catch (...) {
    job->Complete(false, 0);
  }
  executing_ = false;
  // A nested message loop may have consumed the next wake-up. Repost without
  // carrying a borrowed address, and cancel pending jobs if posting fails.
  bool failed = false;
  {
    std::lock_guard<std::mutex> lock(mutex_);
    if (window_ && !queue_.empty() && !wake_pending_) {
      wake_pending_ = !!PostMessageW(window_, kMessage, 0, 0);
      failed = !wake_pending_;
    }
  }
  if (failed) Close();
}

void WindowDispatcher::Close() {
  std::deque<std::shared_ptr<Job>> pending;
  {
    std::lock_guard<std::mutex> lock(mutex_);
    window_ = nullptr;
    wake_pending_ = false;
    pending.swap(queue_);
  }
  for (auto& job : pending) job->Complete(false, 0);
}

}  // namespace study
