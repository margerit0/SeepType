// Included by the generated WeaselServerImpl.cpp inside namespace weasel.
// Transport only: all RequestHandler work is dispatched by ServerImpl.
class PipeServer : public PipeChannel<DWORD, PipeMessage> {
 public:
  using Respond = std::function<void(Msg)>;
  using ServerHandler = std::function<void(PipeMessage, PipeServer&, Respond)>;
  PipeServer(std::wstring&& name, SECURITY_ATTRIBUTES* security)
      : PipeChannel(std::move(name), security) {}
  ~PipeServer() { Stop(); }

  void Start(ServerHandler handler) {
    stopping_ = false;
    listener_ = std::thread([this, handler] {
      while (!stopping_) {
        HANDLE pipe = INVALID_HANDLE_VALUE;
        try {
          pipe = _ConnectServerPipe(pname);
          if (stopping_) { _FinalizePipe(pipe); break; }
          // Reap completed connections; at most 64 live workers are retained.
          for (auto it = workers_.begin(); it != workers_.end();) {
            if (WaitForSingleObject(it->native_handle(), 0) == WAIT_OBJECT_0) {
              it->join();
              it = workers_.erase(it);
            } else ++it;
          }
          if (workers_.size() >= 64) { _FinalizePipe(pipe); continue; }
          workers_.emplace_back([this, pipe, handler]() mutable {
            PipeServer connection(std::wstring(), nullptr);
            try {
              while (!stopping_) {
                Res message{};
                connection._Receive(pipe, &message, sizeof(message));
                if (stopping_) break;
                handler(message, connection, [&](Msg reply) {
                  connection.SendResponse(pipe, reply);
                });
              }
            } catch (...) { /* Disconnect or cancelled request. */ }
            _FinalizePipe(pipe);
          });
        } catch (...) {
          _FinalizePipe(pipe);
          if (!stopping_) Sleep(10);
        }
      }
    });
  }

  void Stop() {
    stopping_ = true;
    CancelAndJoin(listener_);
    // The dispatcher must be closed before Stop: workers awaiting an owner
    // job must be released before the owner joins them here.
    for (auto& worker : workers_) CancelAndJoin(worker);
    workers_.clear();
  }

 private:
  static void CancelAndJoin(std::thread& thread) {
    if (!thread.joinable()) return;
    // Cancellation can race with entry into the next synchronous ReadFile or
    // ConnectNamedPipe. Retry until exit; never terminate a worker forcibly.
    while (WaitForSingleObject(thread.native_handle(), 0) == WAIT_TIMEOUT) {
      CancelSynchronousIo(thread.native_handle());
      WaitForSingleObject(thread.native_handle(), 10);
    }
    thread.join();
  }

  void SendResponse(HANDLE pipe, Msg reply) {
    *reinterpret_cast<Msg*>(buffer.get()) = reply;
    const DWORD size = static_cast<DWORD>(has_body ? buff_size : sizeof(reply));
    DWORD written = 0;
    // Do not FlushFileBuffers: waiting for a client to consume a reply is not
    // needed for message-pipe ordering and would impede shutdown.
    if (!WriteFile(pipe, buffer.get(), size, &written, nullptr) || written != size)
      throw static_cast<DWORD>(ERROR_BROKEN_PIPE);
    ClearBufferStream();
  }
  std::atomic<bool> stopping_{false};
  std::thread listener_;
  std::vector<std::thread> workers_; // listener owns until joined by Stop
};
