using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Text.Json;

namespace Overlay.App;

// A second mode of this same executable, not a machine-specific script or service.
internal static class DesktopRecovery
{
    private static EventWaitHandle? stop;
    private static readonly SemaphoreSlim configuration = new(1, 1);
    private static int supervisor;
    private static long supervisorTicks;
    private static readonly CancellationTokenSource watchingCancellation = new();
    private static string Sid => WindowsIdentity.GetCurrent().User!.Value;
    internal static string StopName(int pid, long ticks) => $"Local\\FeishuMessageOverlay-RecoveryStop-{Sid}-{pid}-{ticks}";
    private static string ReadyName(int pid, long ticks) => StopName(pid, ticks) + "-ready";
    internal static string State { get; private set; } = "disabled";
    private static string Executable => Environment.ProcessPath ?? throw new IOException("Executable unavailable");

    internal static void Adopt(string[] args)
    {
        if(args.Length == 3 && args[0] == "--recovered-by" && int.TryParse(args[1], out var pid) && long.TryParse(args[2], out var ticks))
        {
            using var process = VerifiedProcess(pid, ticks);
            if(process is not null) { supervisor = pid; supervisorTicks = ticks; }
        }
    }

    internal static async Task<bool> ConfigureAsync(bool enabled)
    {
        if(App.SmokeMode) return true;
        await configuration.WaitAsync();
        try
        {
            using var self = Process.GetCurrentProcess();
            var ticks = self.StartTime.ToUniversalTime().Ticks;
            stop ??= new EventWaitHandle(false, EventResetMode.ManualReset, StopName(self.Id, ticks));
            if(!enabled) { stop.Set(); State = "disabled"; return true; }
            if(stop.WaitOne(0))
            {
                // Let a previously disabled supervisor finish before resetting its stop event.
                for(var i = 0; i < 40 && IsReady(self.Id, ticks); i++) await Task.Delay(100);
                if(IsReady(self.Id, ticks)) { State = "unavailable"; return false; }
                supervisor = 0; stop.Reset();
            }
            using var adopted = VerifiedProcess(supervisor, supervisorTicks);
            if(adopted is null && !IsReady(self.Id, ticks))
            {
                supervisor = await Task.Run(() => StartDetached(Executable, $"--desktop-watch {self.Id} {ticks}"));
                using var watcher = Process.GetProcessById(supervisor);
                supervisorTicks = watcher.StartTime.ToUniversalTime().Ticks;
            }
            for(var i = 0; i < 50 && !IsReady(self.Id, ticks); i++) await Task.Delay(100);
            State = IsReady(self.Id, ticks) ? "watching" : "unavailable";
            return State == "watching";
        }
        catch { State = "unavailable"; return false; }
        finally { configuration.Release(); }
    }

    internal static void StopForIntentionalExit()
    {
        if(App.SmokeMode) return;
        stop?.Set();
    }
    internal static async Task StopAsync()
    {
        StopForIntentionalExit();
        if(App.SmokeMode)return;
        using var self=Process.GetCurrentProcess();var ticks=self.StartTime.ToUniversalTime().Ticks;
        for(var i=0;i<40 && IsReady(self.Id,ticks);i++)await Task.Delay(100);
    }
    internal static void CancelWatching() => watchingCancellation.Cancel();

    private static bool IsReady(int pid, long ticks)
    {
        try { using var signal = EventWaitHandle.OpenExisting(ReadyName(pid, ticks)); return signal.WaitOne(0); }
        catch(WaitHandleCannotBeOpenedException) { return false; }
    }

    private enum ProcessVerification { Ready, Starting, Rejected }

    private static ProcessVerification ProbeProcess(int pid, long ticks, out Process? verified, Func<Process,string?>? imagePath=null)
    {
        verified=null;
        if(pid <= 0 || ticks <= 0) return ProcessVerification.Rejected;
        Process? process = null;
        var result=ProcessVerification.Starting;
        try
        {
            process = Process.GetProcessById(pid);
            using var self = Process.GetCurrentProcess();
            if(process.HasExited || process.StartTime.ToUniversalTime().Ticks != ticks || process.SessionId != self.SessionId)
                result=ProcessVerification.Rejected;
            else
            {
                // WMI may return before the Windows loader exposes MainModule.
                // Missing/temporarily unreadable image data is not an identity match.
                var path=imagePath is null?process.MainModule?.FileName:imagePath(process);
                if(!string.IsNullOrEmpty(path))
                {
                    result=ProcessVerification.Rejected;
                    if(string.Equals(path,Executable,StringComparison.OrdinalIgnoreCase) && !process.HasExited)
                    {verified=process;return ProcessVerification.Ready;}
                }
            }
        }
        catch(ArgumentException) { result=ProcessVerification.Rejected; }
        catch(InvalidOperationException) { }
        catch(System.ComponentModel.Win32Exception) { }
        process?.Dispose(); return result;
    }

    private static Process? VerifiedProcess(int pid,long ticks)
    {
        _=ProbeProcess(pid,ticks,out var process);return process;
    }

    private static async Task<Process?> WaitForVerifiedProcessAsync(int pid,long ticks,Func<Process,string?>? imagePath=null)
    {
        // Retry only the same PID/start-time/session/path assertion, bounded to
        // two seconds. An observed identity mismatch is rejected immediately.
        for(var attempt=0;attempt<40;attempt++)
        {
            if(watchingCancellation.IsCancellationRequested)return null;
            var result=ProbeProcess(pid,ticks,out var process,imagePath);
            if(result==ProcessVerification.Ready)return process;
            if(result==ProcessVerification.Rejected)return null;
            try{await Task.Delay(50,watchingCancellation.Token);}
            catch(OperationCanceledException){return null;}
        }
        return null;
    }

    // WMI creates a local process independently of the launching terminal's lifetime.
    // No shell, elevated privileges, scheduled task, or change to system policy.
    internal static int StartDetached(string executable, string arguments)
    {
        if(!Path.IsPathFullyQualified(executable) || executable.Contains('"')) throw new ArgumentException("Invalid executable");
        var objects = new List<object>();
        object Keep(object item) { objects.Add(item); return item; }
        try
        {
            dynamic locator = Keep(Activator.CreateInstance(Type.GetTypeFromProgID("WbemScripting.SWbemLocator", true)!)!);
            dynamic services = Keep(locator.ConnectServer(".", "root\\cimv2"));
            dynamic processClass = Keep(services.Get("Win32_Process"));
            dynamic method = Keep(processClass.Methods_.Item("Create"));
            dynamic input = Keep(method.InParameters.SpawnInstance_());
            input.Properties_.Item("CommandLine").Value = '"' + executable + "\" " + arguments;
            input.Properties_.Item("CurrentDirectory").Value = Path.GetDirectoryName(executable);
            dynamic output = Keep(services.ExecMethod("Win32_Process", "Create", input));
            if(Convert.ToUInt32(output.Properties_.Item("ReturnValue").Value) != 0) throw new IOException("Independent launch failed");
            return Convert.ToInt32(output.Properties_.Item("ProcessId").Value);
        }
        finally { foreach(var item in objects.AsEnumerable().Reverse()) if(Marshal.IsComObject(item)) Marshal.FinalReleaseComObject(item); }
    }

    private static bool AnotherAppRunning()
    {
        if(!Mutex.TryOpenExisting("Local\\FeishuMessageOverlay-" + Sid, out var instance)) return false;
        instance.Dispose(); return true;
    }

    internal static bool RetryAllowed(IEnumerable<DateTimeOffset> attempts, DateTimeOffset now) =>
        attempts.Count(time => time > now.AddMinutes(-10)) < 3;

    internal static async Task<int> WatchAsync(int pid, long ticks, string? fixtureDirectory = null)
    {
        var attempts = new List<DateTimeOffset>();
        var logPath = Path.Combine(fixtureDirectory ?? LocalStorage.DirectoryPath, "recovery.jsonl");
        void Log(string kind, int target)
        {
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(logPath)!);
                if(File.Exists(logPath) && new FileInfo(logPath).Length > 16384) File.Move(logPath, logPath + ".previous", true);
                File.AppendAllText(logPath, JsonSerializer.Serialize(new { at = DateTimeOffset.Now, kind, pid = target }) + Environment.NewLine);
            }
            catch(IOException) { }
            catch(UnauthorizedAccessException) { }
        }
        try
        {
            while(true)
            {
                if(watchingCancellation.IsCancellationRequested)return 0;
                using var watched = await WaitForVerifiedProcessAsync(pid, ticks);
                if(watchingCancellation.IsCancellationRequested)return 0;
                if(watched is null) { Log("target_unavailable", pid); return 1; }
                using var exitSignal = new EventWaitHandle(false, EventResetMode.ManualReset, StopName(pid, ticks));
                using(var ready = new EventWaitHandle(false, EventResetMode.ManualReset, ReadyName(pid, ticks), out var created))
                {
                    if(!created) return 0;
                    ready.Set(); Log("watching", pid);
                    while(!watched.HasExited)
                    {
                        if(exitSignal.WaitOne(0) || watchingCancellation.IsCancellationRequested) { Log("intentional_stop", pid); return 0; }
                        await Task.Delay(250);
                    }
                    // Allow shutdown/update to finish signalling before classifying the exit.
                    await Task.Delay(fixtureDirectory is null ? 2000 : 150);
                    if(exitSignal.WaitOne(0) || watchingCancellation.IsCancellationRequested) { Log("intentional_stop", pid); return 0; }
                }
                if(fixtureDirectory is null && AnotherAppRunning()) { Log("manual_reopen_detected", pid); return 0; }
                var now = DateTimeOffset.UtcNow;
                if(!RetryAllowed(attempts, now)) { Log("retry_limit", pid); return 0; }
                attempts.Add(now); Log("abnormal_exit", pid);
                using var self = Process.GetCurrentProcess();
                var arguments = fixtureDirectory is null
                    ? $"--recovered-by {self.Id} {self.StartTime.ToUniversalTime().Ticks}"
                    : "--recovery-fixture \"" + fixtureDirectory + "\"";
                pid = StartDetached(Executable, arguments);
                using var next = Process.GetProcessById(pid);
                ticks = next.StartTime.ToUniversalTime().Ticks;
                Log("restarted", pid);
            }
        }
        catch { Log("watcher_error", pid); return 1; }
    }

    internal static async Task FixtureAsync(string directory)
    {
        using var self = Process.GetCurrentProcess();
        using var exit = new EventWaitHandle(false, EventResetMode.ManualReset, StopName(self.Id, self.StartTime.ToUniversalTime().Ticks));
        Directory.CreateDirectory(directory);
        await File.WriteAllTextAsync(Path.Combine(directory, "fixture.json"), JsonSerializer.Serialize(new { pid = self.Id, ticks = self.StartTime.ToUniversalTime().Ticks, inJob = ProcessLifecycle.InJob }));
        var deadline = DateTime.UtcNow.AddSeconds(90);
        while(DateTime.UtcNow < deadline)
        {
            if(File.Exists(Path.Combine(directory, "exit-" + self.Id))) { exit.Set(); return; }
            if(File.Exists(Path.Combine(directory,"crash-after-ready")) && IsReady(self.Id,self.StartTime.ToUniversalTime().Ticks))
            {await Task.Delay(200);Environment.Exit(42);}
            await Task.Delay(50);
        }
        exit.Set();
    }

    internal static async Task ContractAsync(string directory)
    {
        Directory.CreateDirectory(directory);
        using(var self=Process.GetCurrentProcess())
        {
            var ticks=self.StartTime.ToUniversalTime().Ticks;var probes=0;
            using var retried=await WaitForVerifiedProcessAsync(self.Id,ticks,process=>
            {
                probes++;
                if(probes==1)throw new System.ComponentModel.Win32Exception(299);
                if(probes==2)return null;
                return process.MainModule?.FileName;
            });
            if(retried?.Id!=self.Id || probes!=3)throw new InvalidOperationException("Transient process image lookup was not retried safely");
            var identityImageReads=0;
            using var changedIdentity=await WaitForVerifiedProcessAsync(self.Id,ticks+1,process=>{identityImageReads++;return process.MainModule?.FileName;});
            if(changedIdentity is not null || identityImageReads!=0)throw new InvalidOperationException("Mismatched process start time was accepted or retried");
            probes=0;
            using var wrongImage=await WaitForVerifiedProcessAsync(self.Id,ticks,_=>{probes++;return Executable+".other";});
            if(wrongImage is not null || probes!=1)throw new InvalidOperationException("Mismatched process image was retried or accepted");
            probes=0;
            using var unavailable=await WaitForVerifiedProcessAsync(self.Id,ticks,_=>{probes++;return null;});
            if(unavailable is not null || probes!=40)throw new InvalidOperationException("Unavailable process image retry was not bounded");
        }
        var now = DateTimeOffset.UtcNow;
        if(!RetryAllowed([], now) || RetryAllowed([now, now, now], now) || !RetryAllowed([now.AddMinutes(-11), now, now], now))
            throw new InvalidOperationException("Retry policy failed");
        const string testPath=@"C:\Portable App\FeishuMessageOverlay.exe";
        if(!StartupRegistration.IsOwned('"'+testPath+"\" --background",testPath) ||
            !StartupRegistration.IsOwned(StartupRegistration.CommandFor(testPath),testPath) ||
            StartupRegistration.IsOwned(StartupRegistration.CommandFor(@"C:\Other\FeishuMessageOverlay.exe"),testPath) ||
            StartupRegistration.CommandFor(testPath).Contains("--background")) throw new InvalidOperationException("Visible startup ownership failed");
        foreach(var graceful in new[] { false, true })
        {
            var root = Path.Combine(directory, graceful ? "graceful" : "crash"); Directory.CreateDirectory(root);
            var initialPid = StartDetached(Executable, "--recovery-fixture \"" + root + "\"");
            using var initial = Process.GetProcessById(initialPid);
            var ticks = initial.StartTime.ToUniversalTime().Ticks;
            var watcher = WatchAsync(initialPid, ticks, root);
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(30));
            try
            {
                while(!IsReady(initialPid, ticks) || !File.Exists(Path.Combine(root, "fixture.json"))) { timeout.Token.ThrowIfCancellationRequested(); await Task.Delay(50); }
                if(graceful) await File.WriteAllTextAsync(Path.Combine(root, "exit-" + initialPid), "exit");
                else initial.Kill();
                await initial.WaitForExitAsync(timeout.Token);
                if(!graceful)
                {
                    int childPid; long childTicks;
                    while(true)
                    {
                        timeout.Token.ThrowIfCancellationRequested();
                        try
                        {
                            using var report = JsonDocument.Parse(await File.ReadAllTextAsync(Path.Combine(root, "fixture.json")));
                            childPid = report.RootElement.GetProperty("pid").GetInt32();
                            childTicks = report.RootElement.GetProperty("ticks").GetInt64();
                            if(childPid != initialPid && IsReady(childPid, childTicks)) break;
                        }
                        catch(IOException) { }
                        catch(JsonException) { }
                        await Task.Delay(50);
                    }
                    using var child = Process.GetProcessById(childPid);
                    await File.WriteAllTextAsync(Path.Combine(root, "exit-" + childPid), "exit");
                    await child.WaitForExitAsync(timeout.Token);
                }
                if(await watcher.WaitAsync(timeout.Token) != 0) throw new InvalidOperationException("Watcher failed");
                var lines = File.ReadAllLines(Path.Combine(root, "recovery.jsonl"));
                if(lines.Count(line => line.Contains("\"kind\":\"restarted\"")) != (graceful ? 0 : 1)) throw new InvalidOperationException("Restart count failed");
            }
            finally
            {
                // The fixture times out by itself; signal only this isolated test's process.
                using var signal = new EventWaitHandle(false, EventResetMode.ManualReset, StopName(initialPid, ticks)); signal.Set();
                if(!initial.HasExited) { initial.Kill(); await initial.WaitForExitAsync(); }
            }
        }
        var disabledRoot=Path.Combine(directory,"disabled");Directory.CreateDirectory(disabledRoot);
        var disabledPid=StartDetached(Executable,"--recovery-fixture \""+disabledRoot+"\"");
        using(var disabledProcess=Process.GetProcessById(disabledPid))
        {
            var disabledTicks=disabledProcess.StartTime.ToUniversalTime().Ticks;
            var disabledWatcher=WatchAsync(disabledPid,disabledTicks,disabledRoot);
            using var disabledSignal=new EventWaitHandle(false,EventResetMode.ManualReset,StopName(disabledPid,disabledTicks));
            try
            {
                disabledSignal.Set();
                if(await disabledWatcher.WaitAsync(TimeSpan.FromSeconds(10))!=0 || disabledProcess.HasExited)
                    throw new InvalidOperationException("Disabling recovery must leave app running");
            }
            finally
            {
                disabledSignal.Set();
                if(!disabledProcess.HasExited){disabledProcess.Kill();await disabledProcess.WaitForExitAsync();}
            }
        }
        var loopRoot=Path.Combine(directory,"crash-loop");Directory.CreateDirectory(loopRoot);
        await File.WriteAllTextAsync(Path.Combine(loopRoot,"crash-after-ready"),"synthetic");
        var loopPid=StartDetached(Executable,"--recovery-fixture \""+loopRoot+"\"");
        using(var loop=Process.GetProcessById(loopPid))
        {
            if(await WatchAsync(loopPid,loop.StartTime.ToUniversalTime().Ticks,loopRoot).WaitAsync(TimeSpan.FromSeconds(30))!=0)
                throw new InvalidOperationException("Crash loop watcher failed");
        }
        var loopLog=File.ReadAllLines(Path.Combine(loopRoot,"recovery.jsonl"));
        if(loopLog.Count(line=>line.Contains("\"kind\":\"restarted\""))!=3 || !loopLog.Any(line=>line.Contains("\"kind\":\"retry_limit\"")))
            throw new InvalidOperationException("Actual crash loop cap failed");
        await File.WriteAllTextAsync(Path.Combine(directory, "recovery-contract.json"), JsonSerializer.Serialize(new { passed = true, startupImageRetryVerified=true, mismatchedIdentityRejected=true, startupImageRetryBounded=true, abnormalExitRestarts = true, manualExitStaysClosed = true, disablingLeavesAppRunning=true,boundedRetries = true, realCrashLoopCappedAt=3,visibleStartup=true,legacyStartupRecognized=true,otherInstallPreserved=true,realAppInterrupted = false }));
    }
}
